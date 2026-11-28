// 채굴량 화면: 국가별 연간 금 광산 생산량(지도·순위)과 세계 분기별 생산량. (자료: WGC / Metals Focus)
import { dataTable, fmt, geoOption, getJSON, h, makeChart, rankOption, theme, timeline, tipRow, tooltipBase } from "../lib.js";

const UPLOAD = "https://github.com/changhok/goldinfograph/upload/main/raw/production";

export async function render(root, ctx) {
  const d = await getJSON("production.json").catch(() => ({ years: [], countries: {}, world_q: { periods: [], t: [] }, world_a: { years: [], t: [] } }));
  const hasCountries = d.years.length > 0, hasWorld = d.world_q.periods.length > 0 || d.world_a.years.length > 0;
  if (!hasCountries && !hasWorld) {
    root.append(h("div", { class: "notice" }, h("h2", {}, "채굴량 자료가 아직 없습니다"),
      h("p", {}, "전 세계 월별 채굴량 통계는 공개된 것이 없어, World Gold Council 의 국가별 연간 생산량과 분기별 세계 광산 생산량을 씁니다. 두 엑셀 모두 gold.org 로그인 후 받을 수 있습니다."),
      h("ol", {},
        h("li", {}, h("a", { href: "https://www.gold.org/goldhub/data/gold-production-by-country", target: "_blank", rel: "noopener" }, "국가별 연간 생산량 엑셀"), " 과 Gold Demand Trends 의 자료 엑셀(공급 표)을 내려받습니다."),
        h("li", {}, h("a", { href: UPLOAD, target: "_blank", rel: "noopener" }, "올리는 화면"), " 에 파일을 끌어다 놓고 Commit changes 를 누릅니다."),
        h("li", {}, "몇 분 뒤 이 화면에 지도와 차트가 나타납니다."))));
    return {};
  }
  const th = theme();
  const agg = new Set(d.aggregates || []);
  const codes = Object.keys(d.countries).filter((c) => !agg.has(c));
  const years = d.years;
  const state = { i: Math.max(0, years.length - 1) };
  const mapEl = h("div", { class: "map", role: "img", "aria-label": "국가별 금 채굴량 지도" });
  const tableBox = h("div", {});
  const rankEl = h("div", { class: "chart tall" }), worldEl = h("div", { class: "chart tall" });
  const rankTitle = h("p", {});
  const yearLabel = (y) => `${y}년`;
  const tl = hasCountries ? timeline(years, state.i, (i) => { state.i = i; update(); }, yearLabel, (y) => y, ["이전 해", "다음 해", "기준 연도"]) : null;
  const max = Math.max(1, ...codes.flatMap((c) => d.countries[c].filter((v) => v != null)));

  root.append(
    h("div", { class: "lede" }, h("h1", {}, "금은 어디에서 캐내나"),
      h("p", {}, "원의 크기는 한 해 동안 광산에서 생산한 금의 양입니다. 전 세계 월별 통계는 없어 연간(국가별)과 분기(세계 합계) 자료로 보여 줍니다.")),
    hasCountries ? h("div", { class: "stage" },
      h("section", { class: "panel map-panel" }, mapEl,
        h("div", { class: "legend" }, h("span", {}, h("i", { style: `background:${th.gold}` }), "원의 넓이 = 연간 광산 생산량(톤)")), tl.el),
      h("section", { class: "panel" }, h("header", {}, h("h2", {}, "국가별 순위"), h("p", {}, "톤")), h("div", { class: "body" }, tableBox))) : null,
    h("div", { class: "grid2" },
      hasCountries ? h("section", { class: "panel" }, h("header", {}, h("h2", {}, "생산량 상위 국가"), rankTitle), h("div", { class: "body" }, rankEl)) : null,
      hasWorld ? h("section", { class: "panel" }, h("header", {}, h("h2", {}, "세계 광산 생산량"), h("p", {}, d.world_q.periods.length ? "분기별, 톤" : "연간, 톤")), h("div", { class: "body" }, worldEl)) : null),
    h("p", { class: "note" }, "자료: World Gold Council, Metals Focus. 최근 연도·분기는 추정치이며 이후 수정될 수 있습니다."));

  let map, table, rank;
  function update() {
    const i = state.i;
    const rows = codes.map((c) => ({ code: c, name: ctx.name(c), v: d.countries[c][i], prev: i > 0 ? d.countries[c][i - 1] : null }))
      .filter((r) => r.v != null && r.v > 0).sort((a, b) => b.v - a.v);
    const total = rows.reduce((s, r) => s + r.v, 0);
    const top = new Set(rows.slice(0, 10).map((r) => r.code));
    map.setOption({ series: [{
      id: "b", type: "scatter", coordinateSystem: "geo",
      data: rows.filter((r) => ctx.pos(r.code)).map((r) => ({ name: r.name, code: r.code, row: r, value: [...ctx.pos(r.code), r.v] })),
      symbolSize: (v) => Math.max(4, Math.sqrt(v[2] / max) * 54),
      itemStyle: { color: th.gold, opacity: 0.82, borderColor: th.surface, borderWidth: 1.5 },
      label: { show: true, formatter: (p) => (top.has(p.data.code) ? p.name : ""), position: "right", color: th.ink, fontSize: 12, textBorderColor: th.surface, textBorderWidth: 3 },
      labelLayout: { hideOverlap: true },
      tooltip: { formatter: (p) => `<div class="tip"><b>${p.name}</b>${tipRow("", `${years[i]}년 생산량`, fmt.t(p.data.row.v))}${tipRow("", "세계 비중", fmt.pct(p.data.row.v / total * 100))}</div>` },
    }] });
    table.update(rows.map((r) => ({ ...r, share: r.v / total * 100 })));
    rankTitle.textContent = `${years[i]}년`;
    rank.setOption(rankOption(th, rows.slice(0, 12).map((r) => ({ name: r.name, value: r.v, color: th.gold, label: "생산량" }))), true);
  }

  return {
    mounted() {
      if (hasWorld) {
        const q = d.world_q.periods.length > 0;
        const x = q ? d.world_q.periods.map((p) => `${p.slice(2, 4)}년 ${Number(p.slice(5, 7)) / 3}분기`) : d.world_a.years;
        const y = q ? d.world_q.t : d.world_a.t;
        makeChart(worldEl).setOption({
          animation: false, grid: { left: 8, right: 16, top: 16, bottom: 4, containLabel: true },
          tooltip: { ...tooltipBase(th), trigger: "axis", formatter: (ps) => `<div class="tip"><b>${ps[0].axisValue}</b>${tipRow(th.gold, "광산 생산량", fmt.t(ps[0].value))}</div>` },
          xAxis: { type: "category", data: x, axisTick: { show: false }, axisLine: { lineStyle: { color: th.rule } }, axisLabel: { color: th.ink2, fontSize: 12, hideOverlap: true } },
          yAxis: { type: "value", axisLabel: { color: th.ink2, fontSize: 12 }, splitLine: { lineStyle: { color: th.grid } } },
          series: [{ type: "bar", data: y, barMaxWidth: 24, itemStyle: { color: th.gold, borderRadius: [3, 3, 0, 0] } }],
        });
      }
      if (!hasCountries) return;
      map = makeChart(mapEl);
      map.setOption({ animation: false, tooltip: { ...tooltipBase(th), trigger: "item" }, geo: geoOption(th, ctx.name), series: [] });
      table = dataTable([
        { key: "name", label: "국가", cls: "name", sort: (r) => r.name, render: (r) => r.name },
        { key: "v", label: "생산량", sort: (r) => r.v, render: (r) => fmt.t(r.v) },
        { key: "share", label: "비중", sort: (r) => r.share, render: (r) => fmt.pct(r.share) },
        { key: "chg", label: "전년 대비", sort: (r) => (r.prev ? r.v - r.prev : null), render: (r) => (r.prev ? fmt.signedT(r.v - r.prev) : "–") },
      ], [], { sortKey: "v", limit: 15 });
      tableBox.append(table.el);
      rank = makeChart(rankEl);
      update();
    },
    cleanup: () => tl && tl.stop(),
  };
}
