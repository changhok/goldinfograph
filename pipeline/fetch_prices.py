"""월평균 금 가격(달러/온스)을 받아 data-store/prices/monthly.csv 로 저장한다.

출처: 공개 데이터셋 datasets/gold-prices (1960년 이후는 세계은행 원자재 가격 'Pink Sheet' 월평균).
주소는 config/sources.json 의 prices.url 에서 바꿀 수 있다.

실행: python pipeline/fetch_prices.py
"""
from __future__ import annotations

import csv
import io
import sys

import requests

from common import STORE, load_config, parse_period, to_number, update_status

OUT = STORE / "prices" / "monthly.csv"


def main() -> int:
    cfg = load_config().get("prices", {})
    url = cfg.get("url")
    if not url:
        return 0
    try:
        r = requests.get(url, timeout=60, headers={"User-Agent": "goldinfograph (github actions)"})
        r.raise_for_status()
        rows = []
        for row in csv.reader(io.StringIO(r.text)):
            if len(row) < 2:
                continue
            p, v = parse_period(row[0]), to_number(row[1])
            if p and p[0] == "M" and v is not None and v > 0:
                rows.append((p[1], v))
        if len(rows) < 100:
            raise ValueError(f"읽은 행이 너무 적습니다({len(rows)}행). 파일 형식을 확인하세요.")
        rows.sort()
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text("month,usd_per_oz\n" + "".join(f"{m},{v:g}\n" for m, v in rows), encoding="utf-8")
        update_status("prices", True, f"월평균 금 가격 {rows[0][0]} ~ {rows[-1][0]} ({len(rows)}개월)")
    except Exception as e:
        update_status("prices", False, f"{type(e).__name__}: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
