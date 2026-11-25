// 국가별 화면: 한 나라의 금 보유량 추이와 수출입, 상대국 내역. (자료: WGC, UN Comtrade)
import { countrySelect, dataTable, deltaCell, disposeCharts, fmt, getJSON, h, latestAt, makeChart, rankOption, seg, theme, timeOption } from "../lib.js";

const ITEM_NAMES = { "710811": "금 분말", "710812": "금괴 등 가공하지 않은 금", "710813": "반가공 금", "710820": "화폐용 금" };

export async function render(root, ctx, param) {
  const [reserves, index, summary] = await Promise.all([getJSON("reserves.json"), getJSON("trade/index.json"), getJSON("trade/summary.json")]);
  const th = theme();
  const agg = new Set(reserves.aggregates || []);
  const codes = [...new Set([...Object.keys(reserves.level), ...Object.keys(reserves.change), ...index.countries])]
    .filter((c) => ctx.isCountry(c) && !agg.has(c));
  if (!codes.length) {
    root.append(h("div", { class: "notice" }, h("h2", {}, "아직 표시할 자료가 없습니다"),
      h("p", {}, "보유량(WGC 엑셀)이나 교역(UN Comtrade) 자료가 들어오면 나라별 화면이 열립니다. ‘자료 현황’에서 진행 상황을 확인하세요.")));
    return {};
  }
  const preferred = ["KOR", "CHN", "CHE", "USA"].find((c) => codes.includes(c)) || codes[0];
  const code = codes.includes(param) ? param : preferred;
  const state = { range: 60, metric: "t" };
  const detail = index.countries.includes(code) ? await getJSON(`trade/country/${code}.json`) : null;
  // 자체 신고가 아예 없거나 최근 18개월 동안 끊긴 나라는 상대국 신고(거울 자료)로 보여 준다
  const own = summary.reporters[code];
  const isReporter = Boolean(own) && own.m_usd.slice(-18).some((v, i) => v != null || own.x_usd.slice(-18)[i] != null);

  const body = h("div", {});
  root.append(
    h("div", { class: "lede" }, h("h1", {}, `${ctx.name(code)}의 금`),
      h("p", {}, "중앙은행 보유량의 변화와, 이 나라를 드나든 금의 상대국을 함께 봅니다.")),
    h("div", { class: "panel" }, h("div", { class: "controls", style: "border-bottom:0" },
      h("label", { class: "field" }, "나라", countrySelect(codes, ctx.name, code, (v) => { location.hash = `#country/${v}`; })),
      seg("기간", [[12, "최근 1년"], [36, "3년"], [60, "5년"], [0, "전체"]], state.range, (v) => { state.range = v; draw(); }),
      seg("교역 단위", [["t", "중량"], ["usd", "금액"]], state.metric, (v) => { state.metric = v; draw(); }))),
    body);

  const pending = [];   // 화면에 붙은 뒤 그릴 차트들
  const chartPanel = (title, sub, cls, option) => {
    const el = h("div", { class: `chart ${cls || ""}` });
    pending.push(() => makeChart(el).setOption(option));
    return h("section", { class: "panel" }, h("header", {}, h("h2", {}, title), h("p", {}, sub || "")), h("div", { class: "body" }, el));
  };
  const slice = (months, arr, n) => (n ? arr.slice(Math.max(0, months.length - n)) : arr);

  function draw() {
    if (body.isConnected) disposeCharts();   // 다시 그릴 때 이전 차트를 정리한다
    pending.length = 0;
    const parts = [];

    // ---------------- 보유량
    const lv = reserves.level[code], ch = reserves.change[code], rm = reserves.months;
    if (lv || ch) {
      let last = rm.length - 1;
      while (last > 0 && (!lv || lv[last] == null) && (!ch || ch[last] == null)) last--;
      const [cur] = latestAt(lv, last, 3);
      const jan = last - (Number(rm[last].slice(5, 7)) - 1);
      const ytd = lv && lv[last] != null && jan - 1 >= 0 && lv[jan - 1] != null ? lv[last] - lv[jan - 1]
        : ch ? ch.slice(Math.max(jan, 0), last + 1).reduce((s, v) => s + (v || 0), 0) : null;
      const yoy = lv && last >= 12 && lv[last] != null && lv[last - 12] != null ? lv[last] - lv[last - 12] : null;
      const snap = reserves.snapshot[code];
      parts.push(h("div", { class: "tiles" },
        tile("금 보유량", fmt.t(cur), `${fmt.month(rm[last])} 기준`),
        tile("월간 증감", deltaCell(ch ? ch[last] : null), "전월 대비"),
        tile("연초 대비", deltaCell(ytd), `${rm[last].slice(0, 4)}년 누계`),
        tile("1년 전 대비", deltaCell(yoy), "12개월 변화"),
        snap && snap.share != null ? tile("외환보유액 중 금 비중", fmt.pct(snap.share), "WGC 현황표") : null));
      const months = slice(rm, rm, state.range);
      const g = h("div", { class: "grid2" });
      if (lv) g.append(chartPanel("금 보유량", "톤", "", timeOption(th, months, [{ name: "보유량", data: slice(rm, lv, state.range), color: th.gold, area: true }], { zeroBased: false })));
      if (ch) g.append(chartPanel("월간 증감", "톤 · 빨강은 증가, 파랑은 감소", "", timeOption(th, months,
        [{ name: "월간 증감", type: "bar", data: slice(rm, ch, state.range), signColors: [th.up, th.down] }], { valueFmt: fmt.signedT })));
      parts.push(g);
    } else {
      parts.push(h("p", { class: "note" }, "이 나라의 중앙은행 보유량 자료는 WGC 엑셀에 없습니다."));
    }

    // ---------------- 교역
    if (detail) {
      const tm = detail.months, n = tm.length;
      const from = state.range ? Math.max(0, n - state.range) : 0;
      const k = state.metric === "t" ? [1, 3] : [2, 4];          // [수입, 수출] 열 위치
      const vfmt = state.metric === "t" ? (v) => fmt.t(v) : (v) => fmt.money(v);
      // 신고국이면 자기 신고를, 아니면 상대국들이 신고한 내용을 뒤집어서 쓴다
      const src = isReporter ? detail.partners : detail.mirror;
      const mi = isReporter ? k[0] : k[1], xi = isReporter ? k[1] : k[0];
      const imp = new Array(n).fill(null), exp = new Array(n).fill(null);
      const pImp = {}, pExp = {};
      for (const [p, rowsP] of Object.entries(src)) {
        for (const r of rowsP) {
          if (r[mi] != null) { imp[r[0]] = (imp[r[0]] || 0) + r[mi]; if (r[0] >= from) pImp[p] = (pImp[p] || 0) + r[mi]; }
          if (r[xi] != null) { exp[r[0]] = (exp[r[0]] || 0) + r[xi]; if (r[0] >= from) pExp[p] = (pExp[p] || 0) + r[xi]; }
        }
      }
      if (isReporter) {   // 합계는 신고국이 낸 '세계' 값이 더 정확하다
        const s = summary.reporters[code];
        const a = state.metric === "t" ? s.m_t : s.m_usd, b = state.metric === "t" ? s.x_t : s.x_usd;
        for (let i = 0; i < n; i++) { if (a[i] != null) imp[i] = a[i]; if (b[i] != null) exp[i] = b[i]; }
      }
      const months = tm.slice(from);
      const round = (v) => (v == null ? null : Math.round(v * 100) / 100);
      const net = imp.map((v, i) => (v == null && exp[i] == null ? null : round((v || 0) - (exp[i] || 0))));
      parts.push(h("div", { class: "lede", style: "margin-top:28px" }, h("h1", { style: "font-size:22px" }, "수출입"),
        h("p", {}, isReporter ? "이 나라가 UN Comtrade 에 신고한 금(HS 7108) 교역입니다."
          : "이 나라는 최근 자체 신고가 없어, 상대국들이 신고한 내용을 모아 거꾸로 추정했습니다. 신고국이 많지 않은 달은 실제보다 작게 나옵니다.")));
      const top = (obj) => Object.entries(obj).filter((e) => e[1] > 0).sort((a, b) => b[1] - a[1]).slice(0, 10);
      const rangeText = state.range ? `최근 ${state.range / 12}년 합계` : "전체 기간 합계";
      parts.push(h("div", { class: "grid2" },
        chartPanel("월별 수입과 수출", state.metric === "t" ? "톤" : "백만 달러 기준", "",
          timeOption(th, months, [{ name: "수입", data: imp.slice(from).map(round), color: th.imp }, { name: "수출", data: exp.slice(from).map(round), color: th.exp }],
            { valueFmt: vfmt, axisFmt: state.metric === "t" ? undefined : (v) => fmt.n(v / 100, 0) + "억" })),
        chartPanel("순수입 (수입 − 수출)", "0 위는 들여온 달, 아래는 내보낸 달", "",
          timeOption(th, months, [{ name: "순수입", type: "bar", data: net.slice(from), signColors: [th.imp, th.exp] }],
            { valueFmt: vfmt, axisFmt: state.metric === "t" ? undefined : (v) => fmt.n(v / 100, 0) + "억" })),
        chartPanel("금을 들여온 나라", rangeText, "tall", rankOption(th, top(pImp).map(([p, v]) => ({ name: ctx.name(p), value: round(v), color: th.imp, label: "수입" })), { valueFmt: vfmt })),
        chartPanel("금을 내보낸 나라", rangeText, "tall", rankOption(th, top(pExp).map(([p, v]) => ({ name: ctx.name(p), value: round(v), color: th.exp, label: "수출" })), { valueFmt: vfmt }))));

      // 상대국 표
      const rows = [...new Set([...Object.keys(pImp), ...Object.keys(pExp)])].map((p) => ({ p, m: pImp[p] || 0, x: pExp[p] || 0 }));
      const tbl = dataTable([
        { key: "name", label: "상대국", cls: "name", sort: (r) => ctx.name(r.p), render: (r) => (ctx.isCountry(r.p) ? h("a", { href: `#country/${r.p}` }, ctx.name(r.p)) : ctx.name(r.p)) },
        { key: "m", label: "수입", sort: (r) => r.m, render: (r) => vfmt(round(r.m)) },
        { key: "x", label: "수출", sort: (r) => r.x, render: (r) => vfmt(round(r.x)) },
        { key: "net", label: "순수입", sort: (r) => r.m - r.x, render: (r) => vfmt(round(r.m - r.x)) },
      ], rows, { sortKey: "m", limit: 15 });
      const itemRows = isReporter ? Object.entries(detail.items).map(([cmd, rs]) => {
        let m = 0, x = 0;
        for (const r of rs) if (r[0] >= from) { m += r[k[0]] || 0; x += r[k[1]] || 0; }
        return { cmd, m, x };
      }).filter((r) => r.m || r.x) : [];
      const g = h("div", { class: "grid2" },
        h("section", { class: "panel" }, h("header", {}, h("h2", {}, "상대국별 내역"), h("p", {}, rangeText)), h("div", { class: "body" }, tbl.el)));
      if (itemRows.length) {
        g.append(h("section", { class: "panel" }, h("header", {}, h("h2", {}, "품목별 내역"), h("p", {}, rangeText)),
          h("div", { class: "body" }, dataTable([
            { key: "name", label: "품목 (HS)", cls: "name", render: (r) => `${ITEM_NAMES[r.cmd] || r.cmd} (${r.cmd})` },
            { key: "m", label: "수입", sort: (r) => r.m, render: (r) => vfmt(round(r.m)) },
            { key: "x", label: "수출", sort: (r) => r.x, render: (r) => vfmt(round(r.x)) },
          ], itemRows, { sortKey: "m" }).el)));
      }
      parts.push(g);
    } else {
      parts.push(h("p", { class: "note", style: "margin-top:20px" }, "이 나라의 교역 자료는 아직 수집되지 않았습니다."));
    }
    body.replaceChildren(...parts);
    if (body.isConnected) flush();
  }
  const flush = () => { pending.splice(0).forEach((fn) => fn()); };
  draw();
  return { mounted: flush };
}

function tile(k, v, s) {
  return h("div", { class: "tile" }, h("div", { class: "k" }, k), h("div", { class: "v num" }, v), h("div", { class: "s" }, s));
}
