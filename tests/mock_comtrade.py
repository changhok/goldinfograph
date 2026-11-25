"""UN Comtrade API 를 흉내 내는 테스트용 서버. 실제 응답과 같은 필드 이름으로 가짜 수치를 돌려준다.
(가짜 수치는 테스트 폴더 밖으로 나가지 않는다.)"""
from __future__ import annotations

import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

# 코드: (수입 규모, 수출 규모) — 대략적인 허브 구조만 흉내
REPORTERS = {757: (180, 150), 826: (90, 110), 784: (70, 60), 344: (60, 40), 156: (110, 2), 699: (65, 1),
             842: (30, 45), 702: (20, 18), 792: (25, 5), 410: (4, 3), 36: (3, 25), 710: (1, 12), 124: (5, 15),
             276: (10, 8), 643: (0, 20), 392: (2, 6)}
CMDS = ["7108", "710811", "710812", "710813", "710820"]
STATS = {"calls": 0, "preview_calls": 0}


def rnd(*parts) -> float:
    h = hashlib.md5("|".join(str(p) for p in parts).encode()).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def records(period: str, reporters: list[int], flows: list[str], cmds: list[str]) -> list[dict]:
    out = []
    year, month = int(period[:4]), int(period[4:6])
    price = 300 + (year - 2000) * 95 + month * 2            # USD/온스 비슷한 추세
    for rep in reporters:
        if rep not in REPORTERS:
            continue
        if rep == 643 and year >= 2022:                      # 신고 중단을 흉내
            continue
        for flow in flows:
            scale = REPORTERS[rep][0 if flow == "M" else 1]
            total_kg = 0.0
            rows = []
            for par in REPORTERS:
                if par == rep:
                    continue
                w = REPORTERS[par][1 if flow == "M" else 0]
                r = rnd(period, rep, par, flow)
                if r < 0.25:
                    continue
                kg = round(scale * w * (0.3 + r) * 4.0, 1)
                total_kg += kg
                rows.append((par, kg))
            rows.append((0, round(total_kg, 1)))
            for par, kg in rows:
                for cmd in cmds:
                    if cmd not in CMDS:
                        continue
                    share = {"7108": 1.0, "710811": 0.02, "710812": 0.80, "710813": 0.13, "710820": 0.05}[cmd]
                    if cmd != "7108" and par != 0 and rnd(period, rep, par, cmd) < 0.5:
                        continue
                    k = kg * share
                    usd = k * 32.15 * price
                    out.append({
                        "typeCode": "C", "freqCode": "M", "refPeriodId": int(period + "01"), "refYear": year,
                        "refMonth": month, "period": period, "reporterCode": rep, "reporterISO": None,
                        "flowCode": flow, "partnerCode": par, "partner2Code": 0, "classificationCode": "H6",
                        "cmdCode": cmd, "customsCode": "C00", "mosCode": "0", "motCode": 0, "qtyUnitCode": 8,
                        "qty": k, "altQtyUnitCode": -1, "altQty": 0.0,
                        "netWgt": k if rnd(period, rep, par, "w") > 0.03 else None,
                        "grossWgt": 0.0, "cifvalue": usd if flow == "M" else None,
                        "fobvalue": usd if flow == "X" else None, "primaryValue": usd, "isAggregate": True,
                    })
    return out


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        preview = u.path.startswith("/public/v1/preview/")
        STATS["calls"] += 1
        if preview:
            STATS["preview_calls"] += 1
        elif not self.headers.get("Ocp-Apim-Subscription-Key"):
            self.send_response(401)
            self.end_headers()
            return
        if not q.get("reporterCode") and STATS.get("reject_all"):   # '전체 신고국' 요청을 거절하는 상황 흉내
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"bad request")
            return
        reporters = [int(x) for x in q["reporterCode"].split(",")] if q.get("reporterCode") else list(REPORTERS)
        cap = 500 if preview else 100000
        data = records(q["period"], reporters, q.get("flowCode", "M,X").split(","), q.get("cmdCode", "7108").split(","))
        body = json.dumps({"elapsedTime": "0.1 secs", "count": min(len(data), cap), "data": data[:cap], "error": ""}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)


def start(port: int = 0):
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv
