// 스위스 화면: 세계 금 정련의 중심인 스위스의 월간 금 수출입을 상대국·품목·통계키별로 본다. (자료: 스위스 관세청 BAZG)
import { dataTable, fmt, geoOption, getJSON, h, makeChart, rankOption, seg, theme, timeline, timeOption, tipRow, tooltipBase } from "../lib.js";

export async function render(root, ctx) {
  const d = await getJSON("swiss.json");
  if (!d.months.length) {
    root.append(h("div", { class: "notice" }, h("h2", {}, "스위스 자료를 아직 받지 못했습니다"),
      h("p", {}, "스위스 관세청 공개 파일은 저장소의 자동 작업이 주 1회 내려받습니다. 첫 실행이 끝나면 이 화면이 채워집니다."),
      h("p", { class: "note" }, "진행 상황과 오류는 ‘자료 현황’ 화면에서 볼 수 있습니다.")));
    return {};
  }
  const th = theme();
  const { months } = d;
  const CH = "CHE";
  const state = { i: months.length - 1, metric: "t", flow: "m" };
  const col = () => (state.metric === "t" ? [1, 3] : [2, 4]);     // [수입, 수출]
  const vfmt = (v) => (state.metric === "t" ? fmt.t(v) : fmt.money(v, "프랑"));
  const itemCodes = Object.keys(d.items);
  const totals = (key) => months.map((_, i) => {
    let s = null;
    for (const it of itemCodes) { const v = d.by_item[it][key][i]; if (v != null) s = (s || 0) + v; }
    return s == null ? null : Math.round(s * 100) / 100;
  });
  // 상대국·달 → 값을 빨리 찾기 위한 색인
  const byMonth = months.map(() => []);
  for (const [p, rows] of Object.entries(d.partners)) for (const r of rows) byMonth[r[0]].push([p, r]);

  const mapEl = h("div", { class: "map", role: "img", "aria-label": "스위스 금 수출입 지도" });
  const legendEl = h("div", { class: "legend" },
    h("span", {}, h("i", { class: "line", style: `background:${th.imp}` }), "스위스로 들어온 금"),
    h("span", {}, h("i", { class: "line", style: `background:${th.exp}` }), "스위스에서 나간 금"),
    h("span", {}, "선의 굵기 = 한 달 교역량"));
  const tl = timeline(months, state.i, (i) => { state.i = i; update(); });
  const tableBox = h("div", {}), tableNote = h("p", {});
  const totalEl = h("div", { class: "chart" }), itemEl = h("div", { class: "chart" });
  const keyEl = h("div", { class: "chart" }), mineEl = h("div", { class: "chart tall" });
  const hasKeys = Object.keys(d.by_key).length > 0;

  root.append(
    h("div", { class: "lede" }, h("h1", {}, "스위스를 거쳐 가는 금"),
      h("p", {}, "세계 금의 큰 몫이 스위스 정련소를 거칩니다. 어느 나라에서 들어와 어디로 나가는지 달마다 살펴봅니다.")),
    h("div", { class: "stage" },
      h("section", { class: "panel map-panel" },
        h("div", { class: "controls" },
          seg("단위", [["t", "중량"], ["chf", "금액(프랑)"]], state.metric, (v) => { state.metric = v; update(); drawStatic(); })),
        mapEl, legendEl, tl.el),
      h("section", { class: "panel" }, h("header", {}, h("h2", {}, "상대국별 수입과 수출"), tableNote), h("div", { class: "body" }, tableBox))),
    h("div", { class: "grid2" },
      h("section", { class: "panel" }, h("header", {}, h("h2", {}, "월별 수입과 수출"), h("p", {}, "관세번호 7108 전체")), h("div", { class: "body" }, totalEl)),
      h("section", { class: "panel" },
        h("header", {}, h("h2", {}, "품목별 구성"), seg("흐름", [["m", "수입"], ["x", "수출"]], state.flow, (v) => { state.flow = v; drawStatic(); })),
        h("div", { class: "body" }, itemEl)),
      hasKeys ? h("section", { class: "panel" }, h("header", {}, h("h2", {}, "수입 금의 성격"), h("p", {}, "통계키 911~914, 2021년 이후")), h("div", { class: "body" }, keyEl)) : null,
      hasKeys && d.key_partners["911"] ? h("section", { class: "panel" }, h("header", {}, h("h2", {}, "광산 금을 보낸 나라"), h("p", {}, "통계키 911, 최근 12개월 합계")), h("div", { class: "body" }, mineEl)) : null),
    h("p", { class: "note" }, "스위스 통계는 2012년부터 금을 국가별로 공개합니다. 수입의 상대국은 원산지 기준이라, 런던 금고에서 온 금은 영국으로 잡힙니다. "
      + "통계키는 2021년부터 수입 금을 광산 금(911)과 정련 금(912~914)으로 나눠 보여 줍니다."));

  let map, table;
  const charts = {};

  function update() {
    const i = state.i, [mi, xi] = col();
    const lines = [];
    const rows = [];
    for (const [p, r] of byMonth[i]) {
      rows.push({ p, m: r[mi], x: r[xi] });
      if (!ctx.pos(p) || p === CH) continue;
      if (r[mi] > 0) lines.push({ from: p, to: CH, v: r[mi], t: r[1], chf: r[2], dir: "m" });
      if (r[xi] > 0) lines.push({ from: CH, to: p, v: r[xi], t: r[3], chf: r[4], dir: "x" });
    }
    lines.sort((a, b) => b.v - a.v);
    const shown = lines.slice(0, 50);
    const max = shown.length ? shown[0].v : 1;
    const data = shown.map((l) => ({
      // 들어오는 선과 나가는 선이 겹치지 않도록 좌표 순서로 휘는 방향이 갈린다
      coords: [ctx.pos(l.from), ctx.pos(l.to)], line: l,
      lineStyle: { width: 0.8 + 5.5 * Math.sqrt(l.v / max), color: l.dir === "m" ? th.imp : th.exp, opacity: 0.3 + 0.5 * Math.sqrt(l.v / max) },
    }));
    const ends = {};
    for (const l of shown) { const p = l.dir === "m" ? l.from : l.to; ends[p] = (ends[p] || 0) + l.v; }
    const labelled = new Set(Object.entries(ends).sort((a, b) => b[1] - a[1]).slice(0, 9).map((e) => e[0]));
    map.setOption({
      series: [
        { id: "lines", type: "lines", coordinateSystem: "geo", zlevel: 1, data, lineStyle: { curveness: 0.25 },
          tooltip: { formatter: (p) => { const l = p.data.line; return `<div class="tip"><b>${ctx.name(l.from)} → ${ctx.name(l.to)}</b>${tipRow("", "중량", fmt.t(l.t))}${tipRow("", "금액", fmt.money(l.chf, "프랑"))}<div class="sub">${fmt.month(months[i])}</div></div>`; } } },
        { id: "moving", type: "lines", coordinateSystem: "geo", zlevel: 2, silent: true,
          data: data.slice(0, 30).map((x) => ({ coords: x.coords, lineStyle: { color: x.lineStyle.color } })),
          lineStyle: { width: 0, curveness: 0.25 }, effect: { show: true, period: 5, trailLength: 0.35, symbolSize: 3.5 } },
        { id: "nodes", type: "scatter", coordinateSystem: "geo", zlevel: 3,
          data: [{ name: ctx.name(CH), code: CH, value: [...ctx.pos(CH), 0] },
            ...Object.keys(ends).map((p) => ({ name: ctx.name(p), code: p, value: [...ctx.pos(p), ends[p]] }))],
          symbolSize: (v, p) => (p.data.code === CH ? 13 : 6),
          itemStyle: { color: th.ink, borderColor: th.surface, borderWidth: 1.5 },
          label: { show: true, formatter: (p) => (p.data.code === CH || labelled.has(p.data.code) ? p.name : ""), position: "right", color: th.ink,
            fontSize: 12, textBorderColor: th.surface, textBorderWidth: 3 },
          labelLayout: { hideOverlap: true },
          tooltip: { formatter: (p) => `<div class="tip"><b>${p.name}</b></div>` } },
      ],
    });
    tableNote.textContent = fmt.month(months[i]);
    table.update(rows);
    for (const k of ["total", "item", "key"]) if (charts[k]) charts[k].setOption({ series: [{ markLine: { data: [{ xAxis: months[i] }] } }] });
  }

  function drawStatic() {
    const t = state.metric === "t";
    const axisFmt = t ? undefined : (v) => fmt.n(v / 100, 0) + "억";
    charts.total.setOption(timeOption(th, months, [
      { name: "수입", data: totals(t ? "m_t" : "m_chf"), color: th.imp }, { name: "수출", data: totals(t ? "x_t" : "x_chf"), color: th.exp }],
      { valueFmt: vfmt, axisFmt, markMonth: months[state.i] }), true);
    const key = `${state.flow}_${t ? "t" : "chf"}`;
    charts.item.setOption(timeOption(th, months, itemCodes.map((it, n) => ({ name: d.items[it], type: "bar", stack: "item", data: d.by_item[it][key], color: th.series[n] })),
      { valueFmt: vfmt, axisFmt, markMonth: months[state.i] }), true);
    if (charts.key) {
      const from = months.findIndex((_, i) => Object.values(d.by_key).some((k) => k.t[i] != null));
      const ms = months.slice(Math.max(from, 0));
      charts.key.setOption(timeOption(th, ms, Object.keys(d.by_key).map((k, n) => ({ name: `${d.keys[k] || k} (${k})`, type: "bar", stack: "key",
        data: d.by_key[k][t ? "t" : "chf"].slice(Math.max(from, 0)), color: th.series[n] })), { valueFmt: vfmt, axisFmt, markMonth: months[state.i] }), true);
    }
    if (charts.mine) {
      const from = months.length - 12, ci = t ? 1 : 2, acc = {};
      for (const [p, rows] of Object.entries(d.key_partners["911"])) for (const r of rows) if (r[0] >= from && r[ci] != null) acc[p] = (acc[p] || 0) + r[ci];
      const top = Object.entries(acc).sort((a, b) => b[1] - a[1]).slice(0, 12);
      charts.mine.setOption(rankOption(th, top.map(([p, v]) => ({ name: ctx.name(p), value: Math.round(v * 100) / 100, color: th.gold, label: "광산 금 수입" })), { valueFmt: vfmt }), true);
    }
  }

  return {
    mounted() {
      map = makeChart(mapEl);
      map.setOption({ animation: false, tooltip: { ...tooltipBase(th), trigger: "item" },
        geo: { ...geoOption(th, ctx.name), boundingCoords: [[-130, 72], [150, -42]] }, series: [] });
      table = dataTable([
        { key: "name", label: "상대국", cls: "name", sort: (r) => ctx.name(r.p), render: (r) => (ctx.isCountry(r.p) ? h("a", { href: `#country/${r.p}` }, ctx.name(r.p)) : ctx.name(r.p)) },
        { key: "m", label: "수입", sort: (r) => r.m, render: (r) => vfmt(r.m) },
        { key: "x", label: "수출", sort: (r) => r.x, render: (r) => vfmt(r.x) },
      ], [], { sortKey: "m", limit: 15 });
      tableBox.append(table.el);
      charts.total = makeChart(totalEl);
      charts.item = makeChart(itemEl);
      if (hasKeys) charts.key = makeChart(keyEl);
      if (hasKeys && d.key_partners["911"]) charts.mine = makeChart(mineEl);
      drawStatic();
      update();
    },
    cleanup: () => tl.stop(),
  };
}
