"""raw/wgc/ 폴더의 World Gold Council 엑셀을 읽어 data-store/wgc/tables.json 으로 정리한다.

WGC 엑셀은 판마다 시트 이름과 배치가 조금씩 달라서, 고정된 위치를 읽지 않고 표의 모양을 보고 찾는다.
  1) 가로형  : 머리글 행에 기간(Jan-24, Q3 2024, 2024 …)이 나열되고 국가가 행으로 내려가는 표
  2) 세로형  : 첫 열에 기간이 내려가고 국가가 열로 나열되는 표
  3) 현황표  : 국가, Tonnes, % of reserves 열이 있는 최신 보유량 표
표마다 '보유량(level)'인지 '증감(change)'인지, 단위가 톤인지를 시트 이름·제목·값으로 판단한다.
판단 결과는 report 에 남아 사이트의 '자료 현황' 화면에 표시되므로, 잘못 읽힌 시트를 바로 알 수 있다.

실행: python pipeline/import_wgc.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from openpyxl import load_workbook

from common import ROOT, STORE, Countries, load_config, parse_period, to_number, update_status, write_json

OUT = STORE / "wgc" / "tables.json"
MAX_ROWS, MAX_COLS = 3000, 1200


def read_sheet(ws) -> list[list]:
    rows = []
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i >= MAX_ROWS:
            break
        rows.append(list(row[:MAX_COLS]))
    return rows


def classify(context: str, values: list[float]) -> tuple[str, str]:
    """(kind, unit) — kind: level/change, unit: tonnes/value/share/other"""
    t = context.lower()
    if re.search(r"%|share|percent|per cent", t):
        unit = "share"
    elif re.search(r"us\$|usd|\$ ?m|\$ ?bn|value|million|billion", t) and "tonne" not in t:
        unit = "value"
    elif re.search(r"\bfx\b|foreign exchange|total reserves|currency", t) and "tonne" not in t and "gold" not in t:
        unit = "other"
    elif "tonne" in t or re.search(r"\bt\b", t):
        unit = "tonnes"
    else:
        big = max((abs(v) for v in values), default=0)
        unit = "tonnes" if big <= 45000 else "value"
    if re.search(r"change|purchase|sales|sold|bought|net buy|net purchas|buying|selling|flow", t):
        kind = "change"
    elif re.search(r"holding|reserve|stock|level", t):
        kind = "level"
    else:
        kind = "change" if any(v < 0 for v in values) else "level"
    return kind, unit


def best_name_column(rows: list[list], start: int, max_col: int, countries: Countries) -> int | None:
    best, best_hits = None, 0
    for c in range(0, max(max_col, 1)):
        hits = 0
        for r in rows[start:start + 400]:
            if c < len(r) and isinstance(r[c], str) and countries.from_name(r[c], record=False):
                hits += 1
        if hits > best_hits:
            best, best_hits = c, hits
    return best if best_hits >= 3 else None


def extract_tables(rows: list[list], sheet_ctx: str, countries: Countries) -> list[dict]:
    """한 시트에서 찾을 수 있는 표를 모두 꺼낸다."""
    tables: list[dict] = []
    if not rows:
        return tables

    # ---------- 1) 가로형: 기간이 가장 많이 나열된 행을 머리글로 본다
    head_idx, head_hits = None, 0
    for i, r in enumerate(rows[:60]):
        hits = sum(1 for v in r if v is not None and parse_period(v))
        if hits > head_hits:
            head_idx, head_hits = i, hits
    if head_idx is not None and head_hits >= 4:
        header = rows[head_idx]
        period_cols = [(c, parse_period(v)) for c, v in enumerate(header) if v is not None and parse_period(v)]
        first_pc = min(c for c, _ in period_cols)
        name_col = best_name_column(rows, head_idx + 1, first_pc if first_pc > 0 else 1, countries)
        if name_col is not None:
            title = " ".join(str(v) for r in rows[:head_idx] for v in r if isinstance(v, str))[:400]
            # 머리글 바로 위 행에 구역 제목(Monthly / Annual 등)이 있을 수 있다
            for freq in ("M", "Q", "A"):
                cols = [(c, p[1]) for c, p in period_cols if p[0] == freq]
                if len(cols) < 3:
                    continue
                data: dict[str, dict[str, float]] = {}
                names: dict[str, str] = {}
                unmatched: list[str] = []
                vals: list[float] = []
                # 'Turkey*' 처럼 별표가 붙은 행은 다른 기준의 참고 계열이다. 별표 없는 행을 먼저 읽어 우선시킨다.
                body = [r for r in rows[head_idx + 1:] if name_col < len(r) and isinstance(r[name_col], str)]
                body.sort(key=lambda r: "*" in r[name_col])
                for r in body:
                    if name_col >= len(r) or not isinstance(r[name_col], str) or not r[name_col].strip():
                        continue
                    nums = {ym: to_number(r[c]) for c, ym in cols if c < len(r)}
                    nums = {k: v for k, v in nums.items() if v is not None}
                    if not nums:
                        continue
                    code = countries.from_name(r[name_col])
                    if not code:
                        unmatched.append(r[name_col].strip())
                        continue
                    if code in data:        # 같은 국가가 두 번 나오면 먼저 나온 행을 쓴다
                        continue
                    data[code] = nums
                    names[code] = r[name_col].strip()
                    vals.extend(nums.values())
                if len(data) >= 3:
                    kind, unit = classify(sheet_ctx + " " + title, vals)
                    tables.append({"layout": "가로형", "freq": freq, "kind": kind, "unit": unit, "data": data,
                                   "names": names, "unmatched": unmatched[:40]})
            if tables:
                return tables

    # ---------- 2) 세로형: 앞쪽 열 중 기간이 많이 내려가는 열을 찾는다
    for c in range(0, 6):
        cells = [(i, parse_period(r[c])) for i, r in enumerate(rows) if c < len(r) and r[c] is not None]
        cells = [(i, p) for i, p in cells if p]
        if len(cells) < 8:
            continue
        first_row = cells[0][0]
        header = None
        for h in range(first_row - 1, max(first_row - 6, -1), -1):
            hits = sum(1 for v in rows[h] if isinstance(v, str) and countries.from_name(v, record=False))
            if hits >= 3:
                header = h
                break
        if header is None:
            continue
        title = " ".join(str(v) for r in rows[:header] for v in r if isinstance(v, str))[:400]
        col_codes = {}
        unmatched = []
        for cc, v in enumerate(rows[header]):
            if cc == c or not isinstance(v, str) or not v.strip():
                continue
            code = countries.from_name(v)
            if code:
                col_codes.setdefault(cc, (code, v.strip()))
            else:
                unmatched.append(v.strip())
        for freq in ("M", "Q", "A"):
            prow = [(i, p[1]) for i, p in cells if p[0] == freq]
            if len(prow) < 3:
                continue
            data, names, vals = {}, {}, []
            for cc, (code, nm) in col_codes.items():
                nums = {ym: to_number(rows[i][cc]) for i, ym in prow if cc < len(rows[i])}
                nums = {k: v for k, v in nums.items() if v is not None}
                if nums and code not in data:
                    data[code] = nums
                    names[code] = nm
                    vals.extend(nums.values())
            if len(data) >= 3:
                kind, unit = classify(sheet_ctx + " " + title, vals)
                tables.append({"layout": "세로형", "freq": freq, "kind": kind, "unit": unit, "data": data,
                               "names": names, "unmatched": unmatched[:40]})
        if tables:
            return tables

    # ---------- 3) 현황표: 'Tonnes' 머리글이 있는 최신 보유량 표
    for i, r in enumerate(rows[:60]):
        low = [str(v).strip().lower() if isinstance(v, str) else "" for v in r]
        ton_cols = [c for c, v in enumerate(low) if re.fullmatch(r"(gold )?(holdings? )?\(?tonnes?\)?.*", v) or v == "tonnes"]
        if not ton_cols:
            continue
        name_col = best_name_column(rows, i + 1, len(r), countries)
        if name_col is None:
            continue
        # 표가 좌우 두 벌로 나뉘어 있는 경우(순위 1~50 | 51~100)를 위해 톤 열마다 가장 가까운 왼쪽 이름 열을 쓴다
        snap, names, unmatched = {}, {}, []
        for tc in ton_cols:
            cands = [c for c in range(tc) if sum(
                1 for rr in rows[i + 1:i + 200] if c < len(rr) and isinstance(rr[c], str)
                and countries.from_name(rr[c], record=False)) >= 3]
            if not cands:
                continue
            nc = max(cands)
            share_col = next((c for c in range(tc + 1, min(tc + 4, len(low))) if "%" in low[c] or "share" in low[c]), None)
            asof_col = next((c for c in range(tc + 1, min(tc + 6, len(low))) if "as of" in low[c] or "date" in low[c]), None)
            for rr in rows[i + 1:]:
                if nc >= len(rr) or not isinstance(rr[nc], str) or tc >= len(rr):
                    continue
                t = to_number(rr[tc])
                if t is None:
                    continue
                code = countries.from_name(rr[nc])
                if not code:
                    unmatched.append(rr[nc].strip())
                    continue
                if code in snap:
                    continue
                entry = {"tonnes": round(t, 2)}
                if share_col is not None and share_col < len(rr):
                    s = to_number(str(rr[share_col]).replace("%", "")) if rr[share_col] is not None else None
                    if s is not None:
                        entry["share"] = round(s * 100, 2) if 0 < abs(s) <= 1 and not str(rr[share_col]).strip().endswith("%") else round(s, 2)
                if asof_col is not None and asof_col < len(rr) and rr[asof_col] is not None:
                    p = parse_period(rr[asof_col])
                    if p:
                        entry["asof"] = p[1]
                snap[code] = entry
                names[code] = rr[nc].strip()
        if len(snap) >= 5:
            tables.append({"layout": "현황표", "freq": "S", "kind": "level", "unit": "tonnes", "snapshot": snap,
                           "names": names, "unmatched": unmatched[:40]})
            return tables
    return tables


def main() -> int:
    cfg = load_config()["wgc"]
    folder = ROOT / cfg["folder"]
    files = sorted(p for p in folder.glob("*.xls*") if not p.name.startswith("~$")) if folder.exists() else []
    if not files:
        update_status("wgc", False, f"{cfg['folder']}/ 폴더에 엑셀 파일이 없습니다. gold.org 에서 내려받아 올려 주세요.",
                      files=[])
        return 0

    countries = Countries()
    merged = {"levels": {"M": {}, "Q": {}, "A": {}}, "changes": {"M": {}, "Q": {}, "A": {}},
              "snapshot": {}, "names": {}}
    report = []
    for path in files:
        try:
            wb = load_workbook(path, read_only=True, data_only=True)
        except Exception as e:
            report.append({"file": path.name, "sheet": "-", "result": f"열 수 없음: {type(e).__name__}: {e}"})
            continue
        for ws in wb.worksheets:
            try:
                rows = read_sheet(ws)
            except Exception as e:
                report.append({"file": path.name, "sheet": ws.title, "result": f"읽기 실패: {e}"})
                continue
            tables = extract_tables(rows, f"{path.stem} {ws.title}", countries)
            if not tables:
                report.append({"file": path.name, "sheet": ws.title, "result": "표를 찾지 못함 (설명·주석 시트로 판단)"})
                continue
            for t in tables:
                entry = {"file": path.name, "sheet": ws.title, "layout": t["layout"], "kind": t["kind"],
                         "unit": t["unit"], "freq": t["freq"], "unmatched_names": t["unmatched"]}
                if t["freq"] == "S":
                    for code, v in t["snapshot"].items():
                        merged["snapshot"][code] = v
                    entry.update(result="사용: 최신 보유량 현황", countries=len(t["snapshot"]))
                elif t["unit"] != "tonnes":
                    entry.update(result="건너뜀: 톤 단위가 아님", countries=len(t["data"]))
                else:
                    bucket = merged["levels" if t["kind"] == "level" else "changes"][t["freq"]]
                    for code, series in t["data"].items():
                        bucket.setdefault(code, {}).update({k: round(v, 3) for k, v in series.items()})
                    periods = sorted({k for s in t["data"].values() for k in s})
                    entry.update(result="사용: " + ("보유량" if t["kind"] == "level" else "증감")
                                 + {"M": " (월간)", "Q": " (분기)", "A": " (연간)"}[t["freq"]],
                                 countries=len(t["data"]), periods=[periods[0], periods[-1]])
                merged["names"].update(t["names"])
                report.append(entry)
        wb.close()

    merged["files"] = [p.name for p in files]
    merged["report"] = report
    write_json(OUT, merged)
    used = [r for r in report if str(r.get("result", "")).startswith("사용")]
    n_lv = len(merged["levels"]["M"]) or len(merged["levels"]["Q"])
    n_ch = len(merged["changes"]["M"])
    ok = bool(used)
    update_status("wgc", ok,
                  f"엑셀 {len(files)}개에서 표 {len(used)}개 사용 — 보유량 {n_lv}개국, 월간 증감 {n_ch}개국, "
                  f"현황표 {len(merged['snapshot'])}개국" if ok else "엑셀에서 읽을 수 있는 표를 찾지 못했습니다.",
                  files=merged["files"], report=report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
