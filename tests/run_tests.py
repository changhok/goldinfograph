"""수집·변환 전 과정을 가짜 자료로 돌려 보고 결과를 점검한다.

  python tests/run_tests.py

실제 자료(data-store/, site/data/)는 건드리지 않고 tests/_out/ 안에서만 작업한다.
끝나면 tests/_out/site/ 를 정적 서버로 띄워 화면을 확인할 수 있다:
  python -m http.server 8765 --directory tests/_out/site
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
OUT = HERE / "_out"
sys.path.insert(0, str(HERE))

import make_fixtures  # noqa: E402
import mock_comtrade  # noqa: E402


def run(script: str, *args: str, env: dict) -> str:
    r = subprocess.run([sys.executable, str(REPO / "pipeline" / script), *args], env=env, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout, r.stderr)
        raise SystemExit(f"{script} 실패")
    return r.stdout


def check(cond: bool, what: str) -> None:
    print(("  통과  " if cond else "  실패  ") + what)
    if not cond:
        check.failed += 1
check.failed = 0


def main() -> int:
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "config").mkdir(parents=True)
    cfg = json.loads((REPO / "config" / "sources.json").read_text(encoding="utf-8"))
    cfg["start_year"] = 2019
    cfg["comtrade"]["request_pause_seconds"] = 0
    (OUT / "config" / "sources.json").write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    shutil.copytree(REPO / "site", OUT / "site", ignore=shutil.ignore_patterns("data"))
    make_fixtures.make_wgc(OUT / "raw" / "wgc")
    swiss = make_fixtures.make_swiss(OUT / "fixtures_swiss")

    srv = mock_comtrade.start()
    env = {**os.environ, "GOLDINFOGRAPH_ROOT": str(OUT), "COMTRADE_BASE_URL": f"http://127.0.0.1:{srv.server_port}"}
    env.pop("COMTRADE_API_KEY", None)

    print("1) UN Comtrade — 키 없이(미리보기) 수집, 호출 한도에서 멈췄다가 이어받기")
    run("fetch_comtrade.py", "--max-calls", "100", env=env)
    st = json.loads((OUT / "data-store/comtrade/state.json").read_text())
    partial = [p for p, v in st["months"].items() if v["mode"] == "preview-partial"]
    full = [p for p, v in st["months"].items() if v["mode"] == "preview"]
    check(len(full) >= 2 and len(partial) <= 1, f"한도 100회 안에서 {len(full)}개월 완료, 미완료 {len(partial)}개월은 표시됨")
    run("fetch_comtrade.py", env=env)
    st = json.loads((OUT / "data-store/comtrade/state.json").read_text())
    check(sum(1 for v in st["months"].values() if v["mode"] == "preview") == 24, "두 번째 실행으로 최근 24개월 완료")

    print("2) UN Comtrade — 키 등록 후 전체 기간으로 자동 확장")
    env_key = {**env, "COMTRADE_API_KEY": "test-key"}
    before = mock_comtrade.STATS["calls"]
    run("fetch_comtrade.py", env=env_key)
    st = json.loads((OUT / "data-store/comtrade/state.json").read_text())
    n_key = sum(1 for v in st["months"].values() if v["mode"] == "key")
    check(n_key >= 90 and all(v["mode"] == "key" for v in st["months"].values()), f"키 방식으로 {n_key}개월 수집(미리보기분 교체)")
    check(mock_comtrade.STATS["calls"] - before == n_key, "한 달에 한 번 호출")
    before = mock_comtrade.STATS["calls"]
    run("fetch_comtrade.py", env=env_key)
    check(mock_comtrade.STATS["calls"] == before, "바로 다시 실행하면 추가 호출 없음")

    print("2-1) UN Comtrade — '전체 신고국' 요청이 거절되면 신고국을 나누어 받기")
    alt = OUT / "alt"
    (alt / "config").mkdir(parents=True)
    shutil.copy(OUT / "config" / "sources.json", alt / "config" / "sources.json")
    mock_comtrade.STATS["reject_all"] = True
    run("fetch_comtrade.py", "--max-calls", "60", env={**env_key, "GOLDINFOGRAPH_ROOT": str(alt)})
    mock_comtrade.STATS["reject_all"] = False
    st2 = json.loads((alt / "data-store/comtrade/state.json").read_text())
    got = [p for p, v in st2["months"].items() if v.get("rows")]
    check(st2.get("explicit_reporters") is True and len(got) >= 5, f"나누어 받기로 전환, {len(got)}개월 수집")

    print("3) 스위스 — 열 이름이 다른 CSV/ZIP 에서 금 행만 추출")
    out = run("fetch_swiss.py", *[x for k, p in swiss.items() for x in ("--local-file", f"{k}={p}")], env=env)
    sw_state = json.loads((OUT / "data-store/swiss/state.json").read_text())
    for fid in ("imports", "exports", "gold_import_keys"):
        cols = sw_state["report"][fid]["columns_used"]
        check({"tariff", "chf", "kg"} <= cols.keys() and ("period" in cols or "year" in cols), f"{fid}: 열 인식 {cols}")
    import gzip, csv as _csv
    with gzip.open(OUT / "data-store/swiss/imports.csv.gz", "rt") as f:
        rows = list(_csv.DictReader(f))
    check(all(r["tariff"].startswith("7108") for r in rows) and len(rows) > 1000, f"수입 {len(rows)}행 모두 7108")

    print("4) WGC — 배치가 다른 엑셀 3종 읽기")
    run("import_wgc.py", env=env)
    t = json.loads((OUT / "data-store/wgc/tables.json").read_text())
    rep = {(r["file"][:8], r["sheet"]): r for r in t["report"]}
    check(rep[("Changes_", "Monthly")]["result"].startswith("사용: 증감 (월간)"), "증감 파일 Monthly → 월간 증감")
    check(rep[("Changes_", "Annual")]["result"].startswith("사용: 증감 (연간)"), "증감 파일 Annual → 연간 증감")
    check(rep[("Quarterl", "Gold tonnes")]["result"].startswith("사용: 보유량 (분기)"), "분기 파일 톤 시트 → 분기 보유량")
    check(rep[("Quarterl", "Gold US$m")]["result"].startswith("건너뜀"), "분기 파일 US$ 시트 → 건너뜀")
    check(abs(t["snapshot"]["USA"]["tonnes"] - 8133.5) < 0.01 and t["snapshot"]["USA"].get("asof") == "2026-09", "현황표 미국 8,133.5t, 2026-09")
    check("Narnia (not a country)" in rep[("Quarterl", "Gold tonnes")]["unmatched_names"], "알 수 없는 이름은 보고서에 기록")

    print("5) 사이트 자료 만들기")
    print(run("build_site_data.py", env=env))
    d = OUT / "site" / "data"
    res = json.loads((d / "reserves.json").read_text())
    i = res["months"].index("2026-09")
    check(abs(res["level"]["CHN"][i] - 2298.5) < 0.01, "중국 2026-09 보유량 = 현황표 값")
    j = res["months"].index("2026-08")
    check(res["level"]["CHN"][j] is not None and abs(res["level"]["CHN"][i] - res["level"]["CHN"][j] - res["change"]["CHN"][i]) < 0.02,
          "분기 사이 달은 증감으로 채워지고 서로 맞음")
    check("_EA" in res["aggregates"], "유로 지역은 합계 행으로 표시")
    k = res["months"].index("2015-02")
    check(res["level"]["USA"][k] == 8133.5 and res["change"]["USA"][k] == 0, "증감표에 값이 없는 달은 변동 없음으로 채움")
    summ = json.loads((d / "trade/summary.json").read_text())
    check("CHE" in summ["reporters"] and summ["months"][0] == "2019-01", "교역 요약: 스위스 포함, 2019-01 시작")
    fl = json.loads((d / "trade/flows/2025.json").read_text())
    check(len(fl["2025-06"]["M"]) > 20 and all(len(x) == 4 for x in fl["2025-06"]["M"]), "2025-06 흐름 목록")
    rus = json.loads((d / "trade/country/RUS.json").read_text())
    check(len(rus["mirror"]) > 3, "러시아: 신고 중단 이후에도 거울 자료 존재")
    sw = json.loads((d / "swiss.json").read_text())
    check(set(sw["by_key"]) == {"911", "912", "913", "914"} and "GBR" in sw["partners"], "스위스: 통계키 4종, 상대국 코드 변환")
    check("?QQ" in sw["unknown_partners"], "스위스: 모르는 국가 코드는 따로 표시")
    meta1 = (d / "meta.json").read_text()
    run("build_site_data.py", env=env)
    check((d / "meta.json").read_text() == meta1, "자료가 그대로면 다시 만들어도 파일이 바뀌지 않음")

    srv.shutdown()
    print("\n모든 점검 통과" if not check.failed else f"\n실패 {check.failed}건")
    return 1 if check.failed else 0


if __name__ == "__main__":
    sys.exit(main())
