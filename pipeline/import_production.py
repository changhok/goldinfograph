"""raw/production/ 의 WGC 엑셀에서 금 광산 생산량을 읽어 data-store/wgc/production.json 으로 정리한다.

두 종류의 표를 찾는다.
  1) 국가별 연간 생산량: 국가가 행, 연도가 열인 표 (import_wgc 의 표 찾기를 그대로 쓴다)
  2) 세계 합계: 'Mine production' 이라는 이름의 행 하나 (Gold Demand Trends 공급 표). 분기·연간 열을 모두 읽는다.

실행: python pipeline/import_production.py
"""
from __future__ import annotations

import re
import sys

from openpyxl import load_workbook

from common import ROOT, STORE, Countries, parse_period, to_number, update_status, write_json
from import_wgc import extract_tables, read_sheet

FOLDER = ROOT / "raw" / "production"
OUT = STORE / "wgc" / "production.json"


def find_world_row(rows: list[list]) -> dict[str, dict[str, float]] | None:
    """'Mine production' 행을 찾아 {'Q': {기간: 톤}, 'A': {...}} 로 돌려준다."""
    head_idx, hits = None, 0
    for i, r in enumerate(rows[:60]):
        n = sum(1 for v in r if v is not None and parse_period(v))
        if n > hits:
            head_idx, hits = i, n
    if head_idx is None or hits < 4:
        return None
    cols = [(c, parse_period(v)) for c, v in enumerate(rows[head_idx]) if v is not None and parse_period(v)]
    for r in rows[head_idx + 1:]:
        label = next((str(v).strip().lower() for v in r[:5] if isinstance(v, str) and v.strip()), "")
        if re.fullmatch(r"(total )?mine production.*", label) or label in ("mine supply", "mined production"):
            out: dict[str, dict[str, float]] = {"Q": {}, "A": {}, "M": {}}
            for c, (freq, ym) in cols:
                v = to_number(r[c]) if c < len(r) else None
                if v is not None and v > 0:
                    out[freq][ym] = round(v, 1)
            if out["Q"] or out["A"] or out["M"]:
                return out
    return None


def main() -> int:
    files = sorted(p for p in FOLDER.glob("*.xls*") if not p.name.startswith("~$")) if FOLDER.exists() else []
    if not files:
        update_status("production", False, "raw/production/ 폴더에 엑셀 파일이 없습니다.", files=[])
        return 0
    countries = Countries()
    by_country: dict[str, dict[str, float]] = {}
    names: dict[str, str] = {}
    world: dict[str, dict[str, float]] = {"Q": {}, "A": {}, "M": {}}
    report = []
    for path in files:
        try:
            wb = load_workbook(path, read_only=True, data_only=True)
        except Exception as e:
            report.append({"file": path.name, "sheet": "-", "result": f"열 수 없음: {e}"})
            continue
        for ws in wb.worksheets:
            rows = read_sheet(ws)
            used = []
            w = find_world_row(rows)
            if w:
                for k in world:
                    world[k].update(w[k])
                used.append(f"세계 합계(분기 {len(w['Q'])}, 연간 {len(w['A'])})")
            for t in extract_tables(rows, f"{path.stem} {ws.title}", countries):
                if t.get("freq") != "A" or t.get("unit") not in ("tonnes",) or len(t["data"]) < 8:
                    continue
                for code, series in t["data"].items():
                    by_country.setdefault(code, {}).update({k[:4]: round(v, 2) for k, v in series.items() if v >= 0})
                names.update(t["names"])
                used.append(f"국가별 연간({len(t['data'])}곳)")
                report.append({"file": path.name, "sheet": ws.title, "result": "사용: " + ", ".join(used),
                               "unmatched_names": t["unmatched"]})
                used = None
                break
            if used:
                report.append({"file": path.name, "sheet": ws.title, "result": "사용: " + ", ".join(used)})
            elif used is not None:
                report.append({"file": path.name, "sheet": ws.title, "result": "채굴량 표를 찾지 못함"})
        wb.close()
    write_json(OUT, {"countries": by_country, "names": names, "world": world, "files": [p.name for p in files]})
    ok = bool(by_country or world["Q"] or world["A"])
    update_status("production", ok,
                  f"국가별 연간 {len(by_country)}곳, 세계 합계 분기 {len(world['Q'])}개·연간 {len(world['A'])}개" if ok
                  else "엑셀에서 채굴량 표를 찾지 못했습니다.", files=[p.name for p in files], report=report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
