"""테스트용 가짜 원자료(WGC 엑셀 3종, 스위스 CSV/ZIP)를 만든다. 수치는 전부 임의 값이다."""
from __future__ import annotations

import csv
import datetime as dt
import io
import random
import zipfile
from pathlib import Path

from openpyxl import Workbook

HOLDERS = [("United States", 8133.5), ("Germany", 3351.5), ("IMF", 2814.0), ("Italy", 2451.8), ("France", 2437.0),
           ("Russian Federation", 2330.0), ("China, P.R.: Mainland", 2298.5), ("Switzerland", 1039.9),
           ("India", 880.0), ("Japan", 846.0), ("Türkiye", 630.0), ("Netherlands", 612.5), ("ECB", 506.5),
           ("Poland, Rep. of", 515.0), ("Taiwan Province of China", 423.6), ("Uzbekistan, Rep. of", 380.0),
           ("Kazakhstan, Rep. of", 300.0), ("Saudi Arabia", 323.1), ("United Kingdom", 310.3),
           ("Korea, Republic of", 104.4), ("Singapore", 220.0), ("Euro Area (incl. ECB)", 10760.0),
           ("Czech Rep.", 62.0), ("Narnia (not a country)", 1.0)]
BUYERS = {"China, P.R.: Mainland": 9, "India": 5, "Türkiye": 7, "Poland, Rep. of": 6, "Russian Federation": 4,
          "Uzbekistan, Rep. of": 2, "Kazakhstan, Rep. of": -1, "Czech Rep.": 1.5, "Singapore": 1}


def months(start=(2002, 1), end=(2026, 9)):
    y, m = start
    while (y, m) <= end:
        yield y, m
        m += 1
        if m == 13:
            y, m = y + 1, 1


def make_wgc(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    rng = random.Random(7)
    ms = list(months())
    # 월간 증감 (뒤에서부터 보유량을 맞추기 위해 먼저 만든다)
    change = {n: [0.0] * len(ms) for n, _ in HOLDERS}
    for n, drift in BUYERS.items():
        for i, (y, _) in enumerate(ms):
            if y >= 2009 and rng.random() < 0.55:
                change[n][i] = round(drift * rng.uniform(-0.3, 1.6), 1)
    level = {}
    for n, last in HOLDERS:
        series, v = [0.0] * len(ms), last
        for i in range(len(ms) - 1, -1, -1):
            series[i] = round(v, 2)
            v -= change[n][i]
        level[n] = series

    # 1) 증감 파일: 가로형, 월간 + 연간 시트
    wb = Workbook()
    ws = wb.active
    ws.title = "Monthly"
    ws.append(["Changes in world official gold reserves, tonnes"])
    ws.append([])
    ws.append(["", "Country"] + [dt.datetime(y, m, 28) for y, m in ms])
    for n, _ in HOLDERS:
        ws.append([None, n] + [c if c else None for c in change[n]])
    ws.append([None, "Source: IMF IFS, World Gold Council"])
    wa = wb.create_sheet("Annual")
    years = sorted({y for y, _ in ms})
    wa.append(["Annual changes, tonnes"])
    wa.append(["Country"] + years)
    for n, _ in HOLDERS:
        wa.append([n] + [round(sum(c for (y, _), c in zip(ms, change[n]) if y == yy), 1) for yy in years])
    wn = wb.create_sheet("Notes")
    wn.append(["Notes"])
    wn.append(["Data are compiled from IMF IFS."])
    wb.save(folder / "Changes_latest_as_of_Nov2026_IFS.xlsx")

    # 2) 분기 파일: 세로형(기간이 행), 톤 시트와 US$ 시트
    wb = Workbook()
    ws = wb.active
    ws.title = "Gold tonnes"
    ws.append(["Quarterly official gold holdings, tonnes"])
    ws.append([""] + [n for n, _ in HOLDERS])
    for i, (y, m) in enumerate(ms):
        if m % 3 == 0:
            ws.append([f"Q{m // 3} {y}"] + [level[n][i] for n, _ in HOLDERS])
    wv = wb.create_sheet("Gold US$m")
    wv.append(["Quarterly official gold holdings, US$ millions"])
    wv.append([""] + [n for n, _ in HOLDERS])
    for i, (y, m) in enumerate(ms):
        if m % 3 == 0:
            wv.append([f"Q{m // 3} {y}"] + [round(level[n][i] * 32150 * 2.6 / 1000) for n, _ in HOLDERS])
    wb.save(folder / "Quarterly_gold_and_FX_Reserves_Q3_2026.xlsx")

    # 3) 현황표
    wb = Workbook()
    ws = wb.active
    ws.title = "Holdings"
    ws.append(["World Official Gold Holdings"])
    ws.append(["International Financial Statistics, November 2026"])
    ws.append([])
    ws.append([None, None, "Tonnes", "% of reserves", "Holdings as of"])
    for rank, (n, last) in enumerate(HOLDERS, 1):
        ws.append([rank, n, last, round(rng.uniform(0.02, 0.8), 3), "Sep 2026"])
    wb.save(folder / "World_official_gold_holdings_as_of_Nov2026_IFS.xlsx")


SW_PARTNERS = [("GB", 40), ("US", 25), ("AE", 30), ("HK", 22), ("CN", 35), ("IN", 28), ("DE", 10), ("IT", 8),
               ("TR", 12), ("SG", 9), ("TH", 7), ("ZA", 6), ("PE", 5), ("GH", 5), ("UZ", 6), ("KR", 2), ("QQ", 1)]


def make_swiss(folder: Path) -> dict[str, Path]:
    folder.mkdir(parents=True, exist_ok=True)
    rng = random.Random(11)
    ms = list(months((2012, 1), (2026, 9)))
    price = lambda y: 45000 + (y - 2012) * 4500     # CHF/kg 비슷한 추세

    def rows(flow: str):
        for y, m in ms:
            # 금이 아닌 품목도 섞어서 걸러 내는지 확인한다
            yield [f"{y}-{m:02d}", "0901.2100", "BR", "Brazil", 1234567, 250000]
            yield [f"{y}-{m:02d}", "7106.9100", "GB", "United Kingdom", 7108000, 99000]   # 값에 7108 이 들어간 함정
            for iso, w in SW_PARTNERS:
                for tn, share in (("7108.1200", 0.86), ("7108.1300", 0.1), ("7108.2000", 0.03), ("7108.1100", 0.01)):
                    if rng.random() < (0.2 if tn == "7108.1200" else 0.6):
                        continue
                    kg = round(w * share * rng.uniform(200, 1800) * (1.1 if flow == "X" else 1.0), 3)
                    yield [f"{y}-{m:02d}", tn, iso, "", round(kg * price(y)), kg]

    out = {}
    # 수입: 세미콜론 CSV
    p = folder / "TN8_IMP_en.csv"
    with open(p, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["period", "tn8", "country_code", "country_txt_e", "chf", "kg"])
        w.writerows(rows("M"))
    out["imports"] = p
    # 수출: 다른 열 이름·연/월 분리·쉼표 CSV 를 ZIP 으로
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Year", "Month", "Tariff number", "Country", "Value (CHF)", "Net mass (kg)"])
    for r in rows("X"):
        w.writerow([r[0][:4], r[0][5:], r[1].replace(".", ""), r[2], r[4], r[5]])
    p = folder / "TN8_EXP_en.zip"
    with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("TN8_EXP_en.csv", buf.getvalue())
    out["exports"] = p
    # 통계키 파일 (2021년 이후)
    p = folder / "TN8_controlCode_Gold_IMP_en_v1.csv"
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["period", "tn8", "controlcode", "controlcode_txt_e", "country_code", "chf", "kg"])
        for y, m in ms:
            if y < 2021:
                continue
            for iso, wt in SW_PARTNERS:
                for key, share in (("911", 0.35 if iso in ("PE", "GH", "ZA", "UZ") else 0.02), ("912", 0.6),
                                   ("913", 0.1), ("914", 0.05)):
                    if rng.random() < 0.3:
                        continue
                    kg = round(wt * share * rng.uniform(200, 1500), 3)
                    w.writerow([f"{y}{m:02d}", "71081200", key, "x", iso, round(kg * price(y)), kg])
    out["gold_import_keys"] = p
    return out
