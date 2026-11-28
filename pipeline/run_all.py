"""수집 → 변환을 순서대로 실행한다. 한 출처가 실패해도 나머지는 계속 진행한다.

실행 예
  python pipeline/run_all.py                      # 전부
  python pipeline/run_all.py --only wgc           # WGC 엑셀만 다시 읽고 사이트 자료 갱신
  python pipeline/run_all.py --only comtrade,swiss
  python pipeline/run_all.py --only build         # 수집 없이 사이트 자료만 다시 만들기
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
STEPS = {
    "wgc": ["import_wgc.py"],
    "comtrade": ["fetch_comtrade.py"],
    "swiss": ["fetch_swiss.py"],
    "prices": ["fetch_prices.py"],
    "production": ["import_production.py"],
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", default="wgc,production,prices,comtrade,swiss", help="쉼표로 구분한 출처 (wgc, production, prices, comtrade, swiss, build)")
    ap.add_argument("--full-refresh", action="store_true", help="이미 받은 자료도 처음부터 다시 받는다")
    args = ap.parse_args()
    wanted = [s.strip() for s in args.only.split(",") if s.strip()]
    failed = []
    for name in wanted:
        if name == "build":
            continue
        if name not in STEPS:
            print(f"알 수 없는 출처: {name}")
            return 2
        cmd = [sys.executable, str(HERE / STEPS[name][0])]
        if args.full_refresh and name == "comtrade":
            cmd.append("--full-refresh")
        if args.full_refresh and name == "swiss":
            cmd.append("--force")
        print(f"\n===== {name} =====", flush=True)
        if subprocess.run(cmd, cwd=HERE).returncode != 0:
            failed.append(name)
    print("\n===== build =====", flush=True)
    rc = subprocess.run([sys.executable, str(HERE / "build_site_data.py")], cwd=HERE).returncode
    if failed:
        print(f"\n실패한 단계: {', '.join(failed)} — 나머지 자료는 정상 반영되었습니다.")
    return rc


if __name__ == "__main__":
    sys.exit(main())
