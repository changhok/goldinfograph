// 교역 흐름 화면: 달마다 나라 사이를 오간 금(HS 7108)을 지도 위 선으로 보여 준다. (자료: UN Comtrade)
import { countrySelect, dataTable, fmt, geoOption, getJSON, h, makeChart, rankOption, seg, theme, timeline, timeOption,
  tipRow, tooltipBase } from "../lib.js";

export async function render(root, ctx) {
  const [index, summary] = await Promise.all([getJSON("trade/index.json"), getJSON("trade/summary.json")]);
  if (!summary.months.length) {
    root.append(h("div", { class: "notice" }, h("h2", {}, "교역 자료를 아직 받지 못했습니다"),
      h("p", {}, "UN Comtrade 수집은 저장소의 자동 작업(GitHub Actions)이 실행되면 채워집니다. 첫 실행 뒤 몇 분 안에 최근 2년 치가 나타납니다."),
      h("p", { class: "note" }, "진행 상황은 ‘자료 현황’ 화면에서 볼 수 있습니다.")));
    return {};
  }
  const th = theme();
  const { months } = summary;
  const state = { i: months.length - 1, basis: "M", metric: "t", top: 60, focus: null };
  // 가장 최근 달은 신고국이 적을 수 있으므로 신고국 수가 충분한 마지막 달에서 시작한다
  const counts = months.map((_, i) => Object.values(summary.reporters).filter((r) => r.m_usd[i] != null || r.x_usd[i] != null).length);
  const peak = Math.max(...counts);
  for (let i = months.length - 1; i >= 0; i--) if (counts[i] >= peak * 0.6) { state.i = i; break; }

  const mapEl = h("div", { class: "map", role: "img", "aria-label": "국가 간 금 교역 흐름 지도" });
  const legendEl = h("div", { class: "legend" });
  const tl = timeline(months, state.i, (i) => { state.i = i; update(); });
  const tableBox = h("div", {});
  const tableNote = h("p", {});
  const netEl = h("div", { class: "chart tall" });
  const netTitle = h("p", {});
  const worldEl = h("div", { class: "chart tall" });
  const focusSel = countrySelect(index.countries.filter(ctx.isCountry), ctx.name, null, (v) => { state.focus = v; update(); }, "전 세계");

  root.append(
    h("div", { class: "lede" }, h("h1", {}, "금은 어디에서 어디로 움직이나"),
      h("p", {}, "선 하나가 한 달 동안 두 나라 사이를 오간 금입니다. 굵을수록 많은 양이고, 나라를 누르면 그 나라의 흐름만 남습니다.")),
    h("div", { class: "stage" },
      h("section", { class: "panel map-panel" },
        h("div", { class: "controls" },
          h("label", { class: "field" }, "나라", focusSel),
          seg("크기 기준", [["t", "중량"], ["usd", "금액"]], state.metric, (v) => { state.metric = v; update(); }),
          seg("신고 기준", [["M", "수입국 신고"], ["X", "수출국 신고"]], state.basis, (v) => { state.basis = v; update(); }),
          seg("선 개수", [[30, "30"], [60, "60"], [120, "120"]], state.top, (v) => { state.top = v; update(); })),
        mapEl, legendEl, tl.el),
      h("section", { class: "panel" },
        h("header", {}, h("h2", {}, "이달의 큰 흐름"), tableNote),
        h("div", { class: "body" }, tableBox))),
    h("div", { class: "grid2" },
      h("section", { class: "panel" }, h("header", {}, h("h2", {}, "순수입국과 순수출국"), netTitle), h("div", { class: "body" }, netEl)),
      h("section", { class: "panel" }, h("header", {}, h("h2", {}, "신고된 세계 금 수입 합계"), h("p", {}, "톤, 월별")), h("div", { class: "body" }, worldEl))),
    h("p", { class: "note" }, "같은 거래라도 수출국과 수입국의 신고가 서로 다를 수 있습니다(시차, 경유지, 신고 누락). "
      + "‘수입국 신고’는 받은 나라가 적어 낸 원산지 기준이고, ‘수출국 신고’는 보낸 나라가 적어 낸 목적지 기준입니다. "
      + "일부 국가는 중량을 신고하지 않아 ‘금액’ 기준에서만 보입니다."));

  let map, table, netChart;
  const val = (f) => (state.metric === "t" ? f[2] : f[3]);
  const vfmt = (v) => (state.metric === "t" ? fmt.t(v) : fmt.money(v));

  async function update() {
    const i = state.i, ym = months[i];
    const year = await getJSON(`trade/flows/${ym.slice(0, 4)}.json`).catch(() => ({}));
    if (i !== state.i) return;                       // 불러오는 사이 달이 바뀌었으면 버린다
    let flows = ((year[ym] || {})[state.basis] || []).filter((f) => val(f) != null && val(f) > 0 && ctx.pos(f[0]) && ctx.pos(f[1]));
    if (state.focus) flows = flows.filter((f) => f[0] === state.focus || f[1] === state.focus);
    flows = [...flows].sort((a, b) => val(b) - val(a)).slice(0, state.top);
    const max = flows.length ? val(flows[0]) : 1;
    const color = (f) => (!state.focus ? th.gold : f[0] === state.focus ? th.exp : th.imp);

    const node = {};
    for (const f of flows) { node[f[0]] = (node[f[0]] || 0) + val(f); node[f[1]] = (node[f[1]] || 0) + val(f); }
    const nodeMax = Math.max(1, ...Object.values(node));
    const labelled = new Set(Object.entries(node).sort((a, b) => b[1] - a[1]).slice(0, 10).map((e) => e[0]));
    const lineData = flows.map((f, n) => ({
      coords: [ctx.pos(f[0]), ctx.pos(f[1])], flow: f,
      lineStyle: { width: 0.7 + 5.5 * Math.sqrt(val(f) / max), color: color(f), opacity: 0.25 + 0.5 * Math.sqrt(val(f) / max) },
      effect: n < 30,
    }));
    const tip = (f) => `<div class="tip"><b>${ctx.name(f[0])} → ${ctx.name(f[1])}</b>${tipRow("", "중량", fmt.t(f[2]))}${tipRow("", "금액", fmt.money(f[3]))}`
      + `<div class="sub">${fmt.month(ym)} · ${state.basis === "M" ? "수입국 신고" : "수출국 신고"}</div></div>`;
    map.setOption({
      series: [
        { id: "lines", type: "lines", coordinateSystem: "geo", zlevel: 1, data: lineData,
          lineStyle: { curveness: 0.28 }, emphasis: { lineStyle: { opacity: 1 } },
          tooltip: { formatter: (p) => tip(p.data.flow) } },
        { id: "moving", type: "lines", coordinateSystem: "geo", zlevel: 2, silent: true,
          data: lineData.filter((d) => d.effect).map((d) => ({ coords: d.coords, lineStyle: { width: 0, color: d.lineStyle.color } })),
          lineStyle: { curveness: 0.28, width: 0 },
          effect: { show: true, period: 5, trailLength: 0.35, symbol: "circle", symbolSize: 3.5 } },
        { id: "nodes", type: "scatter", coordinateSystem: "geo", zlevel: 3,
          data: Object.entries(node).map(([c, v]) => ({ name: ctx.name(c), code: c, value: [...ctx.pos(c), v] })),
          symbolSize: (v) => 5 + 20 * Math.sqrt(v[2] / nodeMax),
          itemStyle: { color: th.ink, opacity: 0.85, borderColor: th.surface, borderWidth: 1.5 },
          label: { show: true, formatter: (p) => (labelled.has(p.data.code) ? p.name : ""), position: "right", color: th.ink, fontSize: 12,
            textBorderColor: th.surface, textBorderWidth: 3 },
          labelLayout: { hideOverlap: true },
          tooltip: { formatter: (p) => `<div class="tip"><b>${p.name}</b>${tipRow("", "표시된 흐름 합계", vfmt(p.value[2]))}<div class="sub">누르면 이 나라만 봅니다</div></div>` } },
      ],
    });
    legendEl.replaceChildren(...(state.focus
      ? [h("span", {}, h("i", { class: "line", style: `background:${th.exp}` }), `${ctx.name(state.focus)}에서 나간 금`),
        h("span", {}, h("i", { class: "line", style: `background:${th.imp}` }), `${ctx.name(state.focus)}로 들어온 금`)]
      : [h("span", {}, h("i", { class: "line", style: `background:${th.gold}` }), "선의 굵기 = 한 달 교역량, 점은 이동 방향")]),
      h("span", {}, h("i", { style: `background:${th.ink}` }), "점의 크기 = 그 나라를 지나는 흐름의 합"));

    tableNote.textContent = `${fmt.month(ym)} · 상위 ${flows.length}개`;
    table.update(flows);

    // 순수입·순수출 (신고국 자체 합계 기준)
    const net = Object.entries(summary.reporters).map(([c, r]) => {
      const m = state.metric === "t" ? r.m_t[i] : r.m_usd[i], x = state.metric === "t" ? r.x_t[i] : r.x_usd[i];
      return m == null && x == null ? null : { code: c, v: (m || 0) - (x || 0) };
    }).filter(Boolean);
    const pos = net.filter((d) => d.v > 0).sort((a, b) => b.v - a.v).slice(0, 8);
    const neg = net.filter((d) => d.v < 0).sort((a, b) => a.v - b.v).slice(0, 8).reverse();
    netTitle.textContent = `${fmt.month(ym)} · 수입 − 수출 (${state.metric === "t" ? "톤" : "금액"})`;
    netChart.setOption(rankOption(th, [...pos, ...neg].map((d) => ({ name: ctx.name(d.code), value: Math.round(d.v * 10) / 10,
      color: d.v > 0 ? th.imp : th.exp, label: d.v > 0 ? "순수입" : "순수출" })), { valueFmt: vfmt }), true);
  }

  return {
    mounted() {
      map = makeChart(mapEl);
      map.setOption({ animation: false, tooltip: { ...tooltipBase(th), trigger: "item" }, geo: geoOption(th, ctx.name), series: [] });
      map.on("click", (p) => {
        const code = p.componentType === "geo" ? p.name : p.data && p.data.code;
        if (!code || !ctx.isCountry(code)) return;
        state.focus = state.focus === code ? null : code;
        focusSel.value = state.focus || "";
        update();
      });
      table = dataTable([
        { key: "from", label: "보낸 나라", cls: "name", sort: (f) => ctx.name(f[0]), render: (f) => h("a", { href: `#country/${f[0]}` }, ctx.name(f[0])) },
        { key: "to", label: "받은 나라", cls: "name", sort: (f) => ctx.name(f[1]), render: (f) => h("a", { href: `#country/${f[1]}` }, ctx.name(f[1])) },
        { key: "t", label: "중량", sort: (f) => f[2], render: (f) => fmt.t(f[2]) },
        { key: "usd", label: "달러", sort: (f) => f[3], render: (f) => fmt.moneyShort(f[3]) },
      ], [], { limit: 14 });
      tableBox.append(table.el);
      netChart = makeChart(netEl);
      const worldImports = months.map((_, i) => {
        let s = null;
        for (const r of Object.values(summary.reporters)) if (r.m_t[i] != null) s = (s || 0) + r.m_t[i];
        return s == null ? null : Math.round(s * 10) / 10;
      });
      makeChart(worldEl).setOption(timeOption(th, months, [{ name: "수입 합계", data: worldImports, color: th.imp, type: "bar" }],
        { axisFmt: (v) => fmt.n(v, 0) }));
      update();
    },
    cleanup: () => tl.stop(),
  };
}
