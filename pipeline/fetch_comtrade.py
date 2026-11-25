"""UN Comtrade 에서 금(HS 7108) 월간 교역 자료를 받아 data-store/comtrade/ 에 쌓는다.

두 가지 방식으로 동작한다.
  - 키 방식     : 환경변수 COMTRADE_API_KEY 가 있으면 전 세계 모든 신고국을 한 달에 한 번 호출로 받는다.
                  무료 키는 하루 500회 제한이라, 2000년부터의 과거 자료는 며칠에 걸쳐 나누어 채운다.
  - 미리보기 방식: 키가 없으면 가입 없이 쓸 수 있는 공개 미리보기(호출당 500건)로
                  설정 파일의 주요국·최근 기간만 받는다. 키를 등록하면 자동으로 전체 수집으로 넘어간다.

저장 형식: data-store/comtrade/YYYY.csv.gz
  period(YYYYMM), reporter(코드), partner(코드), flow(M 수입/X 수출), cmd(HS 코드), usd, kg
진행 상태: data-store/comtrade/state.json (달별 수집 날짜·방식)

실행: python pipeline/fetch_comtrade.py [--full-refresh] [--max-calls N]
"""
from __future__ import annotations

import argparse
import os
import sys
import time

import requests

from common import (STORE, Countries, add_months, load_config, read_csv_gz, read_json, today,
                    update_status, write_csv_gz, write_json)

DIR = STORE / "comtrade"
STATE = DIR / "state.json"
FIELDS = ["period", "reporter", "partner", "flow", "cmd", "usd", "kg"]


class BudgetExhausted(Exception):
    pass


class Client:
    def __init__(self, cfg: dict, key: str | None, max_calls: int):
        self.cfg = cfg
        self.key = key
        self.calls_left = max_calls
        self.calls_made = 0
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "goldinfograph (github actions; monthly gold trade dashboard)"
        self.pause = float(cfg.get("request_pause_seconds", 1.3))
        if not key:
            self.pause = float(cfg["preview_mode"].get("request_pause_seconds", self.pause))
        self.throttled = None
        self.cap = cfg["key_mode" if key else "preview_mode"]["records_per_call_cap"]

    def get(self, period: str, reporters: list[int] | None, flows: list[str], cmds: list[str]) -> list[dict]:
        """한 번 호출. 결과가 상한에 걸리면 호출자가 더 잘게 나눠 다시 부른다."""
        if self.calls_left <= 0:
            raise BudgetExhausted()
        path = "/data/v1/get/C/M/HS" if self.key else "/public/v1/preview/C/M/HS"
        params = {
            "period": period, "cmdCode": ",".join(cmds), "flowCode": ",".join(flows),
            "partner2Code": "0", "motCode": "0", "customsCode": "C00",
            "includeDesc": "false", "maxRecords": str(self.cap),
        }
        if reporters:
            params["reporterCode"] = ",".join(str(r) for r in reporters)
        headers = {"Ocp-Apim-Subscription-Key": self.key} if self.key else {}
        for attempt in range(4):
            self.calls_left -= 1
            self.calls_made += 1
            try:
                r = self.session.get((os.environ.get("COMTRADE_BASE_URL") or self.cfg["base_url"]) + path, params=params, headers=headers, timeout=120)
            except requests.RequestException as e:
                if attempt == 3:
                    raise RuntimeError(f"연결 실패: {e}") from e
                time.sleep(5 * (attempt + 1))
                continue
            if r.status_code == 429:
                wait = min(int(r.headers.get("Retry-After", "20") or 20), 90) + 2
                if attempt == 3 or self.calls_left <= 0:
                    raise BudgetExhausted()
                print(f"  호출 제한(429) — {wait}초 대기")
                time.sleep(wait)
                continue
            if r.status_code == 403 and not self.key:
                # 키 없는 미리보기는 일정량을 쓰면 서버가 403 으로 막는다. 오류가 아니라 '오늘은 여기까지'로 본다.
                self.throttled = f"HTTP 403: {r.text[:160].strip()}"
                raise BudgetExhausted()
            if r.status_code in (401, 403):
                raise PermissionError(
                    f"UN Comtrade 가 요청을 거절했습니다(HTTP {r.status_code}). "
                    "COMTRADE_API_KEY 값과 'comtrade - v1' 구독 상태를 확인하세요.")
            if r.status_code >= 500:
                if attempt == 3:
                    raise RuntimeError(f"UN Comtrade 서버 오류 HTTP {r.status_code}")
                time.sleep(10 * (attempt + 1))
                continue
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
            time.sleep(self.pause)
            body = r.json()
            if body.get("error"):
                raise RuntimeError(f"UN Comtrade 오류 응답: {str(body['error'])[:200]}")
            return body.get("data") or []
        return []

    def get_split(self, period: str, reporters: list[int] | None, flows: list[str], cmds: list[str]) -> list[dict]:
        """상한에 걸리면 흐름 → 품목 → 신고국 순으로 쪼개서 빠짐없이 받는다."""
        data = self.get(period, reporters, flows, cmds)
        if len(data) < self.cap:
            return data
        if len(flows) > 1:
            return [x for f in flows for x in self.get_split(period, reporters, [f], cmds)]
        if len(cmds) > 1:
            return [x for c in cmds for x in self.get_split(period, reporters, flows, [c])]
        if reporters and len(reporters) > 1:
            half = len(reporters) // 2
            return (self.get_split(period, reporters[:half], flows, cmds)
                    + self.get_split(period, reporters[half:], flows, cmds))
        print(f"  경고: {period} 자료가 호출 상한({self.cap}건)에 걸려 일부가 빠졌을 수 있습니다.")
        return data


def normalize(records: list[dict]) -> dict[tuple, tuple]:
    """응답에서 필요한 값만 추려 (기간, 신고국, 상대국, 흐름, 품목) → (달러, kg) 로 만든다."""
    out: dict[tuple, tuple] = {}
    for d in records:
        if d.get("partner2Code") not in (0, None) or d.get("motCode") not in (0, None):
            continue
        if d.get("customsCode") not in ("C00", None):
            continue
        flow = d.get("flowCode")
        if flow not in ("M", "X"):
            continue
        usd = d.get("primaryValue")
        if usd is None:
            usd = d.get("cifvalue") if flow == "M" else d.get("fobvalue")
        kg = d.get("netWgt")
        if not kg:
            if d.get("qtyUnitCode") == 8 and d.get("qty"):
                kg = d.get("qty")
            elif d.get("altQtyUnitCode") == 8 and d.get("altQty"):
                kg = d.get("altQty")
        key = (str(d.get("period")), int(d["reporterCode"]), int(d["partnerCode"]), flow, str(d.get("cmdCode")))
        out[key] = (round(float(usd)) if usd is not None else None,
                    round(float(kg), 3) if kg else None)
    return out


class Store:
    """연도별 파일을 읽고 고쳐 쓴다. 한 달을 다시 받으면 그 달의 기존 행을 통째로 바꾼다."""

    def __init__(self) -> None:
        self.years: dict[str, dict[tuple, tuple]] = {}
        self.dirty: set[str] = set()

    def _load(self, year: str) -> dict[tuple, tuple]:
        if year not in self.years:
            rows = read_csv_gz(DIR / f"{year}.csv.gz")
            self.years[year] = {
                (r["period"], int(r["reporter"]), int(r["partner"]), r["flow"], r["cmd"]):
                (int(r["usd"]) if r["usd"] else None, float(r["kg"]) if r["kg"] else None)
                for r in rows}
        return self.years[year]

    def replace(self, period: str, new: dict[tuple, tuple], reporters: set[int] | None = None) -> None:
        data = self._load(period[:4])
        for k in [k for k in data if k[0] == period and (reporters is None or k[1] in reporters)]:
            del data[k]
        data.update(new)
        self.dirty.add(period[:4])

    def save(self) -> None:
        for year in sorted(self.dirty):
            data = self.years[year]
            rows = [[*k, "" if v[0] is None else v[0], "" if v[1] is None else f"{v[1]:g}"]
                    for k, v in sorted(data.items())]
            write_csv_gz(DIR / f"{year}.csv.gz", FIELDS, rows)
        self.dirty.clear()


def plan_months(cfg: dict, state: dict, key: bool, start_year: int, full_refresh: bool) -> list[str]:
    """이번 실행에서 받을 달의 순서: 한 번도 못 받은 달(최신부터) → 최근 달 갱신 → 오래된 달 재확인."""
    t = today()
    latest = add_months(f"{t.year:04d}-{t.month:02d}", -1)
    months = state.get("months", {})
    if key:
        km = cfg["key_mode"]
        first = f"{start_year:04d}-01"
    else:
        km = {"refresh_recent_months": cfg["preview_mode"]["recent_months"], "refresh_after_days": 25,
              "refresh_old_after_days": 10 ** 6}
        first = add_months(latest, -(cfg["preview_mode"]["recent_months"] - 1))
    all_months = []
    m = latest
    while m >= first:
        all_months.append(m)
        m = add_months(m, -1)
    recent_edge = add_months(latest, -(km["refresh_recent_months"] - 1))

    def age(mm: str) -> int:
        f = months.get(mm.replace("-", ""), {}).get("fetched")
        return 10 ** 6 if not f else (t - type(t).fromisoformat(f)).days

    def needs_upgrade(mm: str) -> bool:
        m_mode = months.get(mm.replace("-", ""), {}).get("mode")
        return m_mode == "preview-partial" or (key and m_mode == "preview")

    if full_refresh:
        return all_months
    missing = [m for m in all_months if m.replace("-", "") not in months or needs_upgrade(m)]
    recent = [m for m in all_months if m not in missing and m >= recent_edge and age(m) >= km["refresh_after_days"]]
    old = [m for m in all_months if m not in missing and m < recent_edge and age(m) >= km["refresh_old_after_days"]]
    return missing + recent + old


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--full-refresh", action="store_true", help="이미 받은 달도 처음부터 다시 받는다")
    ap.add_argument("--max-calls", type=int, default=None, help="이번 실행의 최대 호출 수")
    args = ap.parse_args()

    conf = load_config()
    cfg = conf["comtrade"]
    key = (os.environ.get("COMTRADE_API_KEY") or "").strip() or None
    mode = "key" if key else "preview"
    mcfg = cfg["key_mode" if key else "preview_mode"]
    client = Client(cfg, key, args.max_calls or mcfg["calls_per_run"])
    countries = Countries()
    state = read_json(STATE, {"months": {}}) or {"months": {}}
    state.setdefault("months", {})
    store = Store()

    cmds = cfg["commodity_codes"] if key else mcfg["commodity_codes"]
    reporters = None
    if not key:
        reporters = [countries.m49_for(i) for i in mcfg["reporters_iso3"]]
        reporters = [r for r in reporters if r is not None]

    all_reporters = sorted({countries.m49_for(c["iso3"]) for c in countries.list} - {None})
    old_edge = add_months(f"{today().year:04d}-{today().month:02d}", -13)
    todo = plan_months(cfg, state, bool(key), conf["start_year"], args.full_refresh)
    print(f"UN Comtrade 수집 시작 — 방식: {'키(전체)' if key else '미리보기(주요국·최근)'}, "
          f"대상 {len(todo)}개월, 호출 한도 {client.calls_left}회")
    done, error = 0, None
    try:
        for month in todo:
            period = month.replace("-", "")
            if key:
                rows = {}
                if not state.get("explicit_reporters"):
                    rejected = False
                    try:
                        rows = normalize(client.get_split(period, None, cfg["flows"], cmds))
                    except RuntimeError as e:
                        if "HTTP 400" not in str(e):
                            raise
                        rejected = True
                    # 신고국을 비워 '전체'를 요청했는데 거절되거나 1년 넘은 달이 통째로 비면,
                    # 신고국 코드를 직접 나열하는 방식으로 바꾼다 (이후 실행에서도 유지)
                    if rejected or (not rows and month <= old_edge):
                        state["explicit_reporters"] = True
                        print("  '전체 신고국' 요청이 통하지 않아 신고국을 나누어 요청합니다.")
                if state.get("explicit_reporters"):
                    rows = {}
                    for i in range(0, len(all_reporters), 50):
                        rows.update(normalize(client.get_split(period, all_reporters[i:i + 50], cfg["flows"], cmds)))
                store.replace(period, rows)
            else:
                prev = state["months"].get(period, {})
                # 지난 실행이 호출 한도로 중간에 멈췄다면 받은 신고국은 건너뛰고 이어서 받는다
                already = set(prev.get("reporters_done", [])) if prev.get("mode") == "preview-partial" else set()
                pending = [r for r in reporters if r not in already]
                size = int(mcfg.get("reporters_per_call", 4))
                for i in range(0, len(pending), size):
                    group = pending[i:i + size]      # 500건 상한에 걸리면 get_split 이 알아서 더 잘게 나눈다
                    rows = normalize(client.get_split(period, group, cfg["flows"], cmds))
                    store.replace(period, rows, reporters=set(group))
                    already.update(group)
                    state["months"][period] = {"fetched": str(today()), "mode": "preview-partial",
                                               "reporters_done": sorted(already)}
                rows = {k: 1 for k in store._load(period[:4]) if k[0] == period}
            state["months"][period] = {"fetched": str(today()), "mode": mode, "rows": len(rows)}
            done += 1
            if done % 12 == 0:
                store.save()
                write_json(STATE, state, pretty=True)
                print(f"  {done}개월 완료 (최근 처리: {month}, 남은 호출 {client.calls_left})")
    except BudgetExhausted:
        print("  이번 실행의 호출 한도를 다 썼습니다. 다음 실행에서 이어서 받습니다.")
    except PermissionError as e:
        error = str(e)
    except Exception as e:  # 한 출처의 실패가 전체 갱신을 막지 않도록 기록만 하고 끝낸다
        error = f"{type(e).__name__}: {e}"

    store.save()
    state["mode"] = mode
    write_json(STATE, state, pretty=True)

    remaining = len(plan_months(cfg, state, bool(key), conf["start_year"], False))
    have = sorted(p for p, v in state["months"].items() if v.get("rows"))
    # 상태 문구는 '이번 실행'이 아니라 '지금 가진 자료'를 설명한다 (바뀐 것이 없으면 문구도 그대로)
    msg = (f"보유 기간 {have[0][:4]}-{have[0][4:]} ~ {have[-1][:4]}-{have[-1][4:]} ({len(have)}개월)"
           if have else "아직 받은 자료가 없습니다")
    print(f"  이번 실행: {done}개월 수집, 호출 {client.calls_made}회")
    if remaining:
        msg += f", 남은 작업 {remaining}개월(다음 실행에서 계속)"
    if client.throttled and not error:
        msg += " · 무료 미리보기 호출 한도에 걸려 멈췄습니다. 다음 실행에서 이어 받습니다(키를 등록하면 한도가 크게 늘어납니다)"
        print(f"  서버 응답: {client.throttled}")
    if error:
        update_status("comtrade", False, f"{error} / {msg}", mode=mode, remaining_months=remaining)
        return 0
    update_status("comtrade", True, msg, mode=mode, remaining_months=remaining)
    return 0


if __name__ == "__main__":
    sys.exit(main())
