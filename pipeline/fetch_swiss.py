"""스위스 관세청(BAZG) 공개 자료에서 금(관세번호 7108) 행만 골라 data-store/swiss/ 에 저장한다.

SwissImpex 대시보드와 같은 원자료이며, 전체 품목 파일(수 GB)을 내려받으면서 금 행만 걸러 낸다.
파일의 열 이름은 자동으로 인식하고, 인식 결과를 상태 기록(자료 현황 화면)에 남긴다.
인식이 틀리면 config/sources.json 의 swiss.column_overrides 에 열 이름을 직접 적는다.

저장 형식: data-store/swiss/<id>.csv.gz
  period(YYYY-MM), flow(M/X), tariff(8자리), key(통계키, 없으면 빈칸), partner(원문 국가 표기), chf, kg

실행: python pipeline/fetch_swiss.py [--force] [--local-file ID=경로]
"""
from __future__ import annotations

import argparse
import csv
import io
import os
import re
import sys
import tempfile
import zipfile

import requests

from common import (STORE, load_config, parse_period, read_json, to_number, today, update_status,
                    write_csv_gz, write_json)

DIR = STORE / "swiss"
STATE = DIR / "state.json"
FIELDS = ["period", "flow", "tariff", "key", "partner", "chf", "kg"]

# 열 이름 후보 (소문자, 기호 제거 후 비교). 앞에 있을수록 우선한다.
COLUMN_HINTS = {
    "period": [r"^period$", r"^periode$", r"yearmonth", r"monthyear", r"^date$", r"^datum$", r"period", r"zeitraum"],
    "year": [r"^year$", r"^jahr$", r"^annee$", r"year", r"jahr"],
    "month": [r"^month$", r"^monat$", r"^mois$", r"month", r"monat"],
    "tariff": [r"^tn8$", r"^tn$", r"tn8(?!.*(txt|text|desc|valid))", r"tariffnumber", r"tariffno", r"tarifnummer",
               r"^tariff", r"^hs8$", r"commoditycode"],
    "key": [r"controlcode(?!.*(txt|text|desc))", r"^cc$", r"statkey", r"statisticalkey", r"schluessel", r"^key$"],
    "country": [r"^countrycode$", r"^countryiso", r"^iso2$", r"^landcode$", r"countrycode", r"countryiso",
                r"^country$", r"^land$", r"^pays$", r"partnercode", r"^partner$", r"country(?!.*group)", r"land"],
    "country_name": [r"countryname", r"countrytxte", r"countrytxt", r"countrytext", r"landtxt", r"countrydesc"],
    "chf": [r"^chf$", r"valuechf", r"^value$", r"^wert$", r"chf", r"value", r"wert", r"valeur"],
    "kg": [r"^kg$", r"netmass", r"^mass$", r"^weight$", r"quantitykg", r"massekg", r"kg", r"mass", r"weight",
           r"menge", r"quantity"],
    "key_name": [r"controlcodetxt", r"controlcodetext", r"controlcodedesc"],
    "flow": [r"trafficdirection", r"direction", r"verkehrsrichtung", r"^flow$"],
}


def _norm_col(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def detect_columns(header: list[str], overrides: dict | None) -> dict[str, int]:
    """열 이름으로 역할을 찾는다. 반환: {'period': 0, 'tariff': 3, ...}"""
    normed = [_norm_col(h) for h in header]
    found: dict[str, int] = {}
    for role, col in (overrides or {}).items():
        if role.startswith("_"):
            continue
        if col in header:
            found[role] = header.index(col)
        elif _norm_col(col) in normed:
            found[role] = normed.index(_norm_col(col))
        else:
            raise ValueError(f"설정에 적힌 열 '{col}'({role}) 이 파일에 없습니다. 실제 열: {header}")
    for role, patterns in COLUMN_HINTS.items():
        if role in found:
            continue
        for pat in patterns:
            hit = [i for i, n in enumerate(normed) if re.search(pat, n) and i not in found.values()]
            if hit:
                found[role] = hit[0]
                break
    return found


def sniff_delimiter(line: str) -> str:
    counts = {d: line.count(d) for d in (";", ",", "\t", "|")}
    return max(counts, key=counts.get)


class GoldFilter:
    """파일을 한 줄씩 읽으며 금 행만 모은다. 같은 (기간·품목·키·국가) 는 합산한다."""

    def __init__(self, spec: dict, prefixes: list[str], overrides: dict | None):
        self.spec = spec
        self.prefixes = prefixes
        self.needles = [p.encode() for p in prefixes]
        self.overrides = overrides
        self.cols: dict[str, int] | None = None
        self.delim = ";"
        self.header: list[str] = []
        self.samples: list[list[str]] = []
        self.totals: dict[tuple, list] = {}
        self.lines = 0
        self.kept = 0
        self.bad_period = 0
        self.key_labels: dict[str, str] = {}

    def feed_header(self, raw: bytes) -> None:
        line = raw.decode("utf-8-sig", errors="replace").rstrip("\r\n")
        self.delim = sniff_delimiter(line)
        self.header = next(csv.reader([line], delimiter=self.delim))
        self.cols = detect_columns(self.header, self.overrides)
        need = {"tariff", "country", "chf"}
        if not ({"period"} <= self.cols.keys() or {"year", "month"} <= self.cols.keys()):
            need.add("period")
        missing = sorted(need - self.cols.keys())
        if "country" in missing and "country_name" in self.cols:
            missing.remove("country")
        if missing:
            raise ValueError(f"필요한 열을 찾지 못했습니다: {missing}. 파일의 열: {self.header}. "
                             "config/sources.json 의 swiss.column_overrides 에 열 이름을 적어 주세요.")

    def feed(self, raw: bytes) -> None:
        self.lines += 1
        if not any(n in raw for n in self.needles):   # 대부분의 줄은 여기서 바로 버린다
            return
        line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
        row = next(csv.reader([line], delimiter=self.delim))
        c = self.cols
        if len(row) <= max(c.values()):
            return
        tariff = re.sub(r"\D", "", row[c["tariff"]])
        if not any(tariff.startswith(p) for p in self.prefixes):
            return
        tariff = tariff[:8]
        key = ""
        if "key" in c:
            key = re.sub(r"\D", "", row[c["key"]])
        elif len(re.sub(r"\D", "", row[c["tariff"]])) > 8:   # 7108.1200 911 처럼 붙어 있는 경우
            key = re.sub(r"\D", "", row[c["tariff"]])[8:11]
        if key and "key_name" in c and key not in self.key_labels:
            self.key_labels[key] = row[c["key_name"]].strip()
        if "period" in c:
            p = parse_period(row[c["period"]])
        else:
            p = parse_period(f"{row[c['year']].strip()}-{row[c['month']].strip()}")
        if not p or p[0] != "M":
            self.bad_period += 1
            return
        flow = self.spec["flow"]
        if "flow" in c:
            v = row[c["flow"]].strip().lower()
            if v in ("i", "m") or v.startswith(("imp", "ein", "1")):      # I / import / einfuhr
                flow = "M"
            elif v in ("e", "x", "a") or v.startswith(("exp", "aus", "2")):    # E / export / ausfuhr
                flow = "X"
        partner = row[c["country"]].strip() if "country" in c else row[c["country_name"]].strip()
        chf = to_number(row[c["chf"]]) or 0.0
        kg = to_number(row[c["kg"]]) if "kg" in c else None
        k = (p[1], flow, tariff, key, partner)
        t = self.totals.setdefault(k, [0.0, None])
        t[0] += chf
        if kg is not None:
            t[1] = (t[1] or 0.0) + kg
        self.kept += 1
        if len(self.samples) < 3:
            self.samples.append(row)

    def rows(self) -> list[list]:
        return [[*k, round(v[0]), "" if v[1] is None else f"{round(v[1], 3):g}"]
                for k, v in sorted(self.totals.items())]

    def describe(self) -> dict:
        return {
            "delimiter": self.delim,
            "header": self.header,
            "columns_used": {role: self.header[i] for role, i in (self.cols or {}).items()},
            "sample_rows": self.samples,
            "lines_read": self.lines,
            "gold_rows": self.kept,
            "rows_with_unreadable_period": self.bad_period,
            "key_labels": self.key_labels,
        }


def stream_lines(resp_or_file):
    """줄 단위 바이트를 낸다 (requests 응답 또는 파일 객체)."""
    if hasattr(resp_or_file, "iter_lines"):
        yield from resp_or_file.iter_lines(chunk_size=1 << 20)
    else:
        for line in resp_or_file:
            yield line.rstrip(b"\r\n")


def process_csv_stream(lines, flt: GoldFilter) -> None:
    it = iter(lines)
    flt.feed_header(next(it))
    for raw in it:
        if raw:
            flt.feed(raw)


def process_zip(path: str, flt: GoldFilter) -> None:
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist() if n.lower().endswith((".csv", ".txt"))]
        if not names:
            raise ValueError(f"압축 파일 안에 CSV 가 없습니다: {z.namelist()[:5]}")
        first = True
        for name in sorted(names):
            with z.open(name) as f:
                it = stream_lines(f)
                head = next(it)
                if first:
                    flt.feed_header(head)
                    first = False
                for raw in it:
                    if raw:
                        flt.feed(raw)


def fetch_one(spec: dict, prefixes: list[str], overrides: dict | None, local: str | None) -> tuple[GoldFilter, str]:
    flt = GoldFilter(spec, prefixes, overrides)
    if local:
        if local.lower().endswith(".zip"):
            process_zip(local, flt)
        else:
            with open(local, "rb") as f:
                process_csv_stream(stream_lines(f), flt)
        return flt, local
    errors = []
    for url in spec["urls"]:
        try:
            with requests.get(url, stream=True, timeout=(30, 300),
                              headers={"User-Agent": "goldinfograph (github actions)"}) as r:
                if r.status_code != 200:
                    errors.append(f"{url} → HTTP {r.status_code}")
                    continue
                size = int(r.headers.get("Content-Length") or 0)
                print(f"  내려받는 중: {url} ({size / 1e9:.1f} GB)" if size else f"  내려받는 중: {url}")
                if url.lower().endswith(".zip"):
                    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
                        for chunk in r.iter_content(chunk_size=1 << 22):
                            tmp.write(chunk)
                        tmp_path = tmp.name
                    try:
                        process_zip(tmp_path, flt)
                    finally:
                        os.unlink(tmp_path)
                else:
                    process_csv_stream(stream_lines(r), flt)
                return flt, url
        except ValueError:
            raise
        except Exception as e:
            errors.append(f"{url} → {type(e).__name__}: {e}")
            flt = GoldFilter(spec, prefixes, overrides)
    raise RuntimeError("모든 주소에서 내려받기에 실패했습니다: " + " | ".join(errors))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force", action="store_true", help="최근에 받았더라도 다시 받는다")
    ap.add_argument("--local-file", action="append", default=[], metavar="ID=경로",
                    help="내려받는 대신 이미 가진 파일을 쓴다 (예: imports=/tmp/TN8_IMP_en.csv)")
    args = ap.parse_args()
    local = dict(x.split("=", 1) for x in args.local_file)

    cfg = load_config()["swiss"]
    state = read_json(STATE, {}) or {}
    last = state.get("last_success")
    if last and not args.force and not local:
        days = (today() - type(today()).fromisoformat(last)).days
        if days < cfg.get("min_days_between_runs", 6):
            print(f"스위스 자료는 {days}일 전에 받았습니다. 건너뜁니다 (--force 로 강제 실행).")
            return 0

    overrides_all = cfg.get("column_overrides", {})
    report, problems, got = {}, [], 0
    for spec in cfg["files"]:
        fid = spec["id"]
        if local and fid not in local:
            continue
        print(f"스위스 자료 '{spec['label']}' 처리 시작")
        try:
            flt, src = fetch_one(spec, cfg["tariff_prefixes"], overrides_all.get(fid), local.get(fid))
            rows = flt.rows()
            info = flt.describe()
            info["source"] = src
            report[fid] = info
            if not rows:
                problems.append(f"{fid}: 금 행을 하나도 찾지 못함 (열 인식 결과를 확인하세요)")
                continue
            write_csv_gz(DIR / f"{fid}.csv.gz", FIELDS, rows)
            periods = sorted({r[0] for r in rows})
            info["periods"] = [periods[0], periods[-1]]
            got += 1
            print(f"  금 행 {len(rows):,}개 저장 ({periods[0]} ~ {periods[-1]}), 사용한 열: {info['columns_used']}")
        except Exception as e:
            problems.append(f"{fid}: {type(e).__name__}: {e}")
            print(f"  실패: {e}")

    state["report"] = {**state.get("report", {}), **report}
    if got and not problems:
        state["last_success"] = str(today())
    write_json(STATE, state, pretty=True)
    if problems:
        update_status("swiss", False, f"{got}개 파일 성공, 문제: " + " / ".join(problems), report=state["report"])
    else:
        spans = ", ".join(f"{k} {v['periods'][0]}~{v['periods'][1]}" for k, v in report.items() if v.get("periods"))
        update_status("swiss", True, f"{got}개 파일 갱신 ({spans})", report=state["report"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
