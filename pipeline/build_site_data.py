"""data-store/ 에 쌓인 자료를 사이트가 읽는 JSON(site/data/)으로 바꾼다.

만드는 파일
  meta.json               출처별 갱신 상태와 보유 기간 (자료 현황 화면)
  countries.json          국가 코드 → 한국어 이름·좌표
  reserves.json           국가별 월간 금 보유량(톤)·월간 증감            ← WGC
  trade/summary.json      신고국별 월간 수입·수출 합계                    ← UN Comtrade
  trade/flows/YYYY.json   달마다 규모가 큰 양국 간 흐름 (지도용)          ← UN Comtrade
  trade/country/XXX.json  신고국별 상대국 내역 + 상대국이 신고한 거울 자료 ← UN Comtrade
  swiss.json              스위스 품목·상대국·통계키별 월간 수출입          ← 스위스 관세청

단위: 중량은 톤(t), 금액은 백만(USD 또는 CHF).
실행: python pipeline/build_site_data.py
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from collections import defaultdict

from common import (SITE_DATA, STATUS, STORE, Countries, add_months, fmt_num, load_config, month_range,
                    now_iso, read_csv_gz, read_json, write_json)


def series(months: list[str], values: dict[str, float], digits: int = 3) -> list:
    return [fmt_num(values.get(m), digits) for m in months]


# ================================================================ 보유량 (WGC)
def build_reserves(countries: Countries) -> dict:
    t = read_json(STORE / "wgc" / "tables.json")
    if not t:
        write_json(SITE_DATA / "reserves.json", {"months": [], "level": {}, "change": {}, "snapshot": {},
                                                 "aggregates": [], "names": {}})
        return {"available": False}

    lvM, lvQ, lvA = t["levels"]["M"], t["levels"]["Q"], t["levels"]["A"]
    chM = t["changes"]["M"]
    snap = t.get("snapshot", {})
    codes = sorted(set(lvM) | set(lvQ) | set(lvA) | set(chM) | set(snap))
    all_periods = {p for d in (lvM, lvQ, lvA, chM) for s in d.values() for p in s}
    all_periods |= {v["asof"] for v in snap.values() if v.get("asof")}
    if not all_periods:
        # 현황표만 있는 경우: 기간 없이 최신 보유량만 보여 준다
        write_json(SITE_DATA / "reserves.json", {"months": [], "level": {}, "change": {}, "snapshot": snap,
                                                 "aggregates": [c for c in codes if countries.special.get(c, {}).get("aggregate")],
                                                 "names": t.get("names", {})})
        return {"available": True, "months": None, "countries": len(codes), "snapshot_only": True}
    months = month_range(min(all_periods), max(all_periods))
    idx = {m: i for i, m in enumerate(months)}

    ch_periods = [p for sr in chM.values() for p in sr]
    g_first, g_last = (min(ch_periods), max(ch_periods)) if ch_periods else (None, None)
    level_out, change_out = {}, {}
    estimated = 0
    for code in codes:
        lv: dict[str, float] = {}
        # 1순위: 분기·연간 보유량을 기준점으로 깔고, 월간 보유량이 있으면 덮어쓴다
        lv.update(lvA.get(code, {}))
        lv.update(lvQ.get(code, {}))
        lv.update(lvM.get(code, {}))
        s = snap.get(code)
        if s and s.get("asof") and not lv:
            lv[s["asof"]] = s["tonnes"]      # 보유량 표에 없는 곳만 현황표 값을 쓴다 (표마다 집계 기준이 다를 수 있다)
        src_points = sorted(lv)
        ch = dict(chM.get(code, {}))
        if lv and g_first:
            # 2순위: 기준점(분기 말) 사이의 달은 WGC 월간 증감을 따라 채운다.
            # 증감의 합이 두 기준점의 차이와 다르면(집계 기준 차이·수정) 남는 차이를 달마다 고르게 나눠 다음 기준점에 정확히 닿게 한다.
            for a, b in zip(src_points, src_points[1:]):
                gap = month_range(add_months(a, 1), add_months(b, -1)) if add_months(a, 1) < b else []
                if not gap:
                    continue
                resid = (lv[b] - lv[a]) - sum(ch.get(m, 0.0) for m in gap + [b])
                cum = 0.0
                for k, m in enumerate(gap, 1):
                    cum += ch.get(m, 0.0)
                    lv[m] = lv[a] + cum + resid * k / (len(gap) + 1)
                    estimated += 1
            # 마지막 기준점 뒤: 증감이 실제로 보고된 달까지만 이어 간다
            m = src_points[-1]
            while add_months(m, 1) in ch:
                lv[add_months(m, 1)] = lv[m] + ch[add_months(m, 1)]
                m = add_months(m, 1)
                estimated += 1
            # 첫 기준점 앞: 뒤에서부터 거꾸로 계산한다
            m = src_points[0]
            while m in ch and add_months(m, -1) >= g_first:
                lv[add_months(m, -1)] = lv[m] - ch[m]
                m = add_months(m, -1)
                estimated += 1
        elif lv:
            # 월간 증감표가 아예 없으면 분기 자료 사이의 두 달은 직전 분기 값을 그대로 둔다
            pts = set(src_points)
            for m in months:
                p1, p2 = add_months(m, -1), add_months(m, -2)
                if m not in lv and add_months(m, 1) <= src_points[-1]:
                    if p1 in pts or (p2 in pts and p1 in lv):
                        lv[m] = lv[p1]
        # 월간 증감이 없는 달은 보유량의 차이로 계산한다
        for m in months:
            if m not in ch:
                prev = add_months(m, -1)
                if m in lv and prev in lv:
                    ch[m] = lv[m] - lv[prev]
        if lv:
            level_out[code] = series(months, lv, 2)
        if ch:
            change_out[code] = series(months, ch, 2)

    aggregates = [c for c in codes if countries.special.get(c, {}).get("aggregate")]
    write_json(SITE_DATA / "reserves.json", {
        "months": months, "level": level_out, "change": change_out, "snapshot": snap,
        "aggregates": aggregates, "names": t.get("names", {}),
    })
    has_level_months = sorted({months[i] for s in level_out.values() for i, v in enumerate(s) if v is not None})
    has_change_months = sorted({months[i] for s in change_out.values() for i, v in enumerate(s) if v is not None})
    return {
        "available": True,
        "countries": len([c for c in codes if c not in aggregates]),
        "months": [months[0], months[-1]],
        "level_months": [has_level_months[0], has_level_months[-1]] if has_level_months else None,
        "change_months": [has_change_months[0], has_change_months[-1]] if has_change_months else None,
        "estimated_points": estimated,
        "files": t.get("files", []),
    }


# ================================================================ 교역 (UN Comtrade)
def build_trade(countries: Countries, cfg: dict) -> dict:
    out_dir = SITE_DATA / "trade"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    files = sorted((STORE / "comtrade").glob("[0-9][0-9][0-9][0-9].csv.gz"))
    main_cmd = "7108"
    # (신고국, 상대국) → {달: [수입t, 수입M$, 수출t, 수출M$]}
    pair: dict[tuple[str, str], dict[str, list]] = defaultdict(dict)
    items: dict[tuple[str, str], dict[str, list]] = defaultdict(dict)   # (신고국, 품목) → 세계 합계
    months_seen: set[str] = set()
    n_rows = 0
    for f in files:
        for r in read_csv_gz(f):
            rep = countries.from_comtrade(r["reporter"])
            par = countries.from_comtrade(r["partner"])
            if not rep or not par or not countries.is_country(rep):
                continue
            ym = f"{r['period'][:4]}-{r['period'][4:6]}"
            usd = float(r["usd"]) / 1e6 if r["usd"] else None
            t = float(r["kg"]) / 1000 if r["kg"] else None
            off = 0 if r["flow"] == "M" else 2
            if r["cmd"] == main_cmd:
                cell = pair[(rep, par)].setdefault(ym, [None, None, None, None])
                months_seen.add(ym)
                n_rows += 1
            elif par == "_WLD":
                cell = items[(rep, r["cmd"])].setdefault(ym, [None, None, None, None])
            else:
                continue
            cell[off], cell[off + 1] = t, usd

    if not months_seen:
        write_json(out_dir / "summary.json", {"months": [], "reporters": {}})
        write_json(out_dir / "index.json", {"years": [], "countries": []})
        return {"available": False}

    months = month_range(min(months_seen), max(months_seen))
    idx = {m: i for i, m in enumerate(months)}
    reporters = sorted({rep for rep, _ in pair})

    # ---- 신고국별 월간 합계: '세계' 행이 있으면 그것을, 없으면 상대국 합을 쓴다
    summary = {}
    for rep in reporters:
        tot: dict[str, list] = {}
        world = pair.get((rep, "_WLD"), {})
        partner_sum: dict[str, list] = defaultdict(lambda: [None, None, None, None])
        for (r2, par), cells in pair.items():
            if r2 != rep or par == "_WLD":
                continue
            for ym, c in cells.items():
                s = partner_sum[ym]
                for k in range(4):
                    if c[k] is not None:
                        s[k] = (s[k] or 0) + c[k]
        for ym in set(world) | set(partner_sum):
            w, p = world.get(ym), partner_sum.get(ym)
            tot[ym] = [(w[k] if w and w[k] is not None else (p[k] if p else None)) for k in range(4)]
        summary[rep] = {
            "m_t": [fmt_num(tot[m][0]) if m in tot else None for m in months],
            "m_usd": [fmt_num(tot[m][1]) if m in tot else None for m in months],
            "x_t": [fmt_num(tot[m][2]) if m in tot else None for m in months],
            "x_usd": [fmt_num(tot[m][3]) if m in tot else None for m in months],
        }
    write_json(out_dir / "summary.json", {"months": months, "reporters": summary})

    # ---- 지도용 흐름: 달마다 금액이 큰 순으로 N개 (수입국 신고 기준 / 수출국 신고 기준)
    top_n = cfg["site"]["flows_per_month"]
    min_t = cfg["site"]["min_flow_kg"] / 1000
    by_year: dict[str, dict[str, dict[str, list]]] = defaultdict(lambda: defaultdict(lambda: {"M": [], "X": []}))
    for (rep, par), cells in pair.items():
        if not countries.is_country(par) or rep == par:
            continue
        for ym, c in cells.items():
            if c[1] is not None and c[1] > 0 and (c[0] is None or c[0] >= min_t):
                by_year[ym[:4]][ym]["M"].append([par, rep, fmt_num(c[0]), fmt_num(c[1])])   # 상대국 → 신고국
            if c[3] is not None and c[3] > 0 and (c[2] is None or c[2] >= min_t):
                by_year[ym[:4]][ym]["X"].append([rep, par, fmt_num(c[2]), fmt_num(c[3])])   # 신고국 → 상대국
    for year, by_month in by_year.items():
        for ym, b in by_month.items():
            for k in ("M", "X"):
                b[k].sort(key=lambda x: -(x[3] or 0))
                del b[k][top_n:]
        write_json(out_dir / "flows" / f"{year}.json", dict(sorted(by_month.items())))

    # ---- 국가별 상세: 자기 신고 내역 + 다른 나라가 신고한 거울 자료
    mirror: dict[str, dict[str, list]] = defaultdict(dict)
    for (rep, par), cells in pair.items():
        if countries.is_country(par):
            mirror[par][rep] = [[idx[ym], *[fmt_num(v) for v in c]] for ym, c in sorted(cells.items())]
    detail_codes = sorted(set(reporters) | set(mirror))
    for code in detail_codes:
        partners = {par: [[idx[ym], *[fmt_num(v) for v in c]] for ym, c in sorted(cells.items())]
                    for (rep, par), cells in pair.items() if rep == code and par != "_WLD"}
        item_out = {cmd: [[idx[ym], *[fmt_num(v) for v in c]] for ym, c in sorted(cells.items())]
                    for (rep, cmd), cells in items.items() if rep == code}
        write_json(out_dir / "country" / f"{code}.json",
                   {"months": months, "partners": partners, "items": item_out, "mirror": mirror.get(code, {})})
    write_json(out_dir / "index.json", {"years": sorted(by_year), "countries": detail_codes, "reporters": reporters})

    return {"available": True, "months": [months[0], months[-1]], "reporters": len(reporters),
            "rows": n_rows, "mode": (read_json(STORE / "comtrade" / "state.json", {}) or {}).get("mode")}


# ================================================================ 스위스 (BAZG)
def build_swiss(countries: Countries, cfg: dict) -> dict:
    d = STORE / "swiss"
    imp = read_csv_gz(d / "imports.csv.gz")
    exp = read_csv_gz(d / "exports.csv.gz")
    keys = read_csv_gz(d / "gold_import_keys.csv.gz")
    # 스위스는 2012년부터 금괴를 국가별 통계에 넣었다. 그 전의 7108 수치는 일부 품목뿐이라 제외한다.
    start = cfg["swiss"].get("start_month")
    if start:
        imp, exp, keys = ([r for r in rows if r["period"] >= start] for rows in (imp, exp, keys))
    if not imp and not exp and keys:
        imp = keys            # 전체 수입 파일이 없으면 통계키 파일의 합으로 대신한다
    if not imp and not exp and not keys:
        write_json(SITE_DATA / "swiss.json", {"months": [], "by_item": {}, "partners": {}, "by_key": {},
                                              "key_partners": {}, "items": {}, "keys": {}})
        return {"available": False}

    def code_of(raw: str) -> str:
        return countries.from_name(raw) or f"?{raw}"

    months_seen = {r["period"] for r in imp + exp + keys}
    months = month_range(min(months_seen), max(months_seen))
    idx = {m: i for i, m in enumerate(months)}

    by_item: dict[str, dict[str, list]] = defaultdict(dict)            # 품목 → 달 → [수입t, 수입MCHF, 수출t, 수출MCHF]
    partners: dict[str, dict[str, list]] = defaultdict(dict)           # 상대국 → 달 → 위와 같음
    item_partners: dict[str, dict[str, dict[str, list]]] = defaultdict(lambda: defaultdict(dict))
    unknown: dict[str, str] = {}
    for rows in (imp, exp):
        for r in rows:
            off = 0 if r["flow"] == "M" else 2
            t = float(r["kg"]) / 1000 if r["kg"] else None
            chf = float(r["chf"]) / 1e6 if r["chf"] else None
            code = code_of(r["partner"])
            if code.startswith("?"):
                unknown[code] = r["partner"]
            for bucket in (by_item[r["tariff"]], partners[code], item_partners[r["tariff"]][code]):
                cell = bucket.setdefault(r["period"], [None, None, None, None])
                if t is not None:
                    cell[off] = (cell[off] or 0) + t
                if chf is not None:
                    cell[off + 1] = (cell[off + 1] or 0) + chf

    by_key: dict[str, dict[str, list]] = defaultdict(dict)             # 통계키 → 달 → [t, MCHF]
    key_partners: dict[str, dict[str, dict[str, list]]] = defaultdict(lambda: defaultdict(dict))
    for r in keys:
        if not r["key"]:
            continue
        t = float(r["kg"]) / 1000 if r["kg"] else None
        chf = float(r["chf"]) / 1e6 if r["chf"] else None
        code = code_of(r["partner"])
        if code.startswith("?"):
            unknown[code] = r["partner"]
        for bucket in (by_key[r["key"]], key_partners[r["key"]][code]):
            cell = bucket.setdefault(r["period"], [None, None])
            if t is not None:
                cell[0] = (cell[0] or 0) + t
            if chf is not None:
                cell[1] = (cell[1] or 0) + chf

    def sparse(cells: dict[str, list]) -> list:
        return [[idx[ym], *[fmt_num(v) for v in c]] for ym, c in sorted(cells.items())]

    def dense(cells: dict[str, list], k: int) -> list:
        return [fmt_num(cells[m][k]) if m in cells else None for m in months]

    names = {**cfg["swiss"].get("items", {})}
    write_json(SITE_DATA / "swiss.json", {
        "months": months,
        "items": {k: names.get(k, k) for k in sorted(by_item)},
        "keys": cfg["swiss"].get("keys", {}),
        "by_item": {k: {"m_t": dense(v, 0), "m_chf": dense(v, 1), "x_t": dense(v, 2), "x_chf": dense(v, 3)}
                    for k, v in sorted(by_item.items())},
        "partners": {k: sparse(v) for k, v in sorted(partners.items())},
        "item_partners": {it: {k: sparse(v) for k, v in sorted(p.items())} for it, p in sorted(item_partners.items())},
        "by_key": {k: {"t": dense(v, 0), "chf": dense(v, 1)} for k, v in sorted(by_key.items())},
        "key_partners": {k: {c: sparse(v) for c, v in sorted(p.items())} for k, p in sorted(key_partners.items())},
        "unknown_partners": unknown,
    })
    return {"available": True, "months": [months[0], months[-1]], "partners": len(partners),
            "has_keys": bool(by_key), "unknown_partners": len(unknown)}


# ================================================================ 금 가격·실시간 그래프 설정
def build_prices(cfg: dict) -> dict:
    path = STORE / "prices" / "monthly.csv"
    months, usd = [], []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines()[1:]:
            m, v = line.split(",")
            if m >= "1970-01":
                months.append(m)
                usd.append(float(v))
    write_json(SITE_DATA / "prices.json", {"months": months, "usd": usd, "live": {
        k: v for k, v in cfg.get("live_chart", {}).items() if not k.startswith("_")}})
    return {"available": bool(months), "months": [months[0], months[-1]] if months else None}


# ================================================================ 채굴량 (WGC)
def build_production(countries: Countries) -> dict:
    t = read_json(STORE / "wgc" / "production.json") or {"countries": {}, "world": {"Q": {}, "A": {}, "M": {}}}
    years = sorted({y for s in t["countries"].values() for y in s})
    agg = [c for c in t["countries"] if countries.special.get(c, {}).get("aggregate")]
    wq = sorted(t["world"]["Q"].items())
    wa = sorted(t["world"]["A"].items())
    write_json(SITE_DATA / "production.json", {
        "years": years,
        "countries": {c: [s.get(y) for y in years] for c, s in sorted(t["countries"].items())},
        "aggregates": agg,
        "world_q": {"periods": [k for k, _ in wq], "t": [v for _, v in wq]},
        "world_a": {"years": [k[:4] for k, _ in wa], "t": [v for _, v in wa]},
    })
    return {"available": bool(years or wq or wa), "years": [years[0], years[-1]] if years else None,
            "countries": len(t["countries"]) - len(agg), "world_quarters": len(wq)}


def main() -> int:
    cfg = load_config()
    countries = Countries()
    SITE_DATA.mkdir(parents=True, exist_ok=True)

    info = {"reserves": build_reserves(countries), "trade": build_trade(countries, cfg),
            "swiss": build_swiss(countries, cfg), "prices": build_prices(cfg), "production": build_production(countries)}

    table = {c["iso3"]: {"ko": c["ko"], "en": c["en"], "lat": round(c["lat"], 2), "lon": round(c["lon"], 2),
                         "num": f"{c['m49']:03d}" if c.get("m49") is not None else None}
             for c in countries.list}
    for code, v in countries.special.items():
        table[code] = {"ko": v["ko"], "special": True, "aggregate": v["aggregate"]}
    write_json(SITE_DATA / "countries.json", table)

    status = read_json(STATUS, {}) or {}
    digest = hashlib.sha1()
    for f in sorted(SITE_DATA.rglob("*.json")):
        if f.name != "meta.json":
            digest.update(f.relative_to(SITE_DATA).as_posix().encode())
            digest.update(f.read_bytes())
    meta = {
        "start_year": cfg["start_year"],
        "data": info,
        "data_hash": digest.hexdigest()[:12],
        "sources": status,
        "unknown_codes": sorted(countries.unknown)[:80],
        "wgc_page": cfg["wgc"]["page"],
    }
    # 내용이 그대로면 생성 시각도 유지한다 (불필요한 커밋·재배포 방지)
    old = read_json(SITE_DATA / "meta.json", {}) or {}
    same = {k: v for k, v in old.items() if k != "generated"} == json.loads(json.dumps(meta))
    meta["generated"] = old.get("generated") if same and old.get("generated") else now_iso()
    write_json(SITE_DATA / "meta.json", meta, pretty=True)
    for k, v in info.items():
        print(f"[build] {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
