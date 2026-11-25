// 보유량 화면: 국가별 금 보유량·월간 증감·연초 대비 증감을 지도와 순위표로 보여 준다. (자료: WGC)
import { dataTable, deltaCell, fmt, geoOption, getJSON, h, latestAt, makeChart, rankOption, seg, theme, timeline,
  timeOption, tipRow, tooltipBase } from "../lib.js";

export async function render(root, ctx) {
  const [data, prices] = await Promise.all([getJSON("reserves.json"), getJSON("prices.json").catch(() => ({ months: [], usd: [] }))]);
  if (!data.months.length) {
    root.append(emptyNotice(ctx, data));
    return {};
  }
  const th = theme();
  const { months } = data;
  const agg = new Set(data.aggregates || []);
  const holders = Object.keys({ ...data.level, ...data.change }).filter((c) => !agg.has(c));

  // ---- 계산
  const level = (c, i) => latestAt(data.level[c], i, 3)[0];
  const mom = (c, i) => (data.change[c] ? data.change[c][i] : null);
  // 연초 대비: WGC 월간 증감의 그해 누계 (WGC 발표와 같은 방식). 증감 자료가 없으면 전년 말 보유량과의 차이.
  const ytd = (c, i) => {
    const jan = i - (Number(months[i].slice(5, 7)) - 1);          // 그해 1월의 위치
    const ch = data.change[c];
    let s = null;
    if (ch) for (let k = Math.max(jan, 0); k <= i; k++) if (ch[k] != null) s = (s || 0) + ch[k];
    if (s != null) return s;
    const lv = data.level[c];
    return lv && lv[i] != null && jan - 1 >= 0 && lv[jan - 1] != null ? lv[i] - lv[jan - 1] : null;
  };
  // 세계 합계: WGC 가 낸 'World' 행이 있으면 그것을, 없으면 표에 실린 곳의 합을 쓴다
  const world = months.map((_, i) => {
    const w = latestAt(data.level._WLD, i, 0)[0];
    if (w != null) return Math.round(w * 10) / 10;
    if (data.level._WLD) return null;
    let s = 0, n = 0;
    for (const c of holders) { const v = latestAt(data.level[c], i, 6)[0]; if (v != null) { s += v; n++; } }
    return n ? Math.round(s * 10) / 10 : null;
  });
  const maxLevel = Math.max(...holders.map((c) => Math.max(0, ...(data.level[c] || []).filter((v) => v != null))));
  const robustMax = (fn) => {   // 재생 중 원 크기가 달마다 널뛰지 않도록 전체 기간에서 기준을 잡는다
    const all = [];
    for (const c of holders) for (let i = 0; i < months.length; i += 1) { const v = fn(c, i); if (v) all.push(Math.abs(v)); }
    all.sort((a, b) => a - b);
    return all.length ? all[Math.floor(all.length * 0.995)] : 1;
  };
  const scale = { level: maxLevel || 1, mom: null, ytd: null };

  const state = { i: lastIndexWithData(), mode: "level" };
  function lastIndexWithData() {
    for (let i = months.length - 1; i >= 0; i--) if (holders.some((c) => data.level[c] && data.level[c][i] != null || mom(c, i) != null)) return i;
    return months.length - 1;
  }

  // ---- 틀
  const mapEl = h("div", { class: "map", role: "img", "aria-label": "국가별 금 보유량 지도" });
  const legendEl = h("div", { class: "legend" });
  const tl = timeline(months, state.i, (i) => { state.i = i; update(); });
  const tableBox = h("div", {});
  const worldEl = h("div", { class: "chart" });
  const priceEl = h("div", { class: "chart" });
  // 월평균 금 가격을 보유량과 같은 달 축에 맞춘다 (같은 위치에 기준 월 표시선이 서도록)
  const priceAt = Object.fromEntries(prices.months.map((m, k) => [m, prices.usd[k]]));
  const priceSeries = months.map((m) => priceAt[m] ?? null);
  const momEl = h("div", { class: "chart tall" });
  const ytdEl = h("div", { class: "chart tall" });
  const momTitle = h("p", {});
  const ytdTitle = h("p", {});

  root.append(
    h("div", { class: "lede" }, h("h1", {}, "각국 중앙은행은 금을 얼마나 쥐고 있나"),
      h("p", {}, "원의 크기는 금의 양입니다. 아래 막대를 움직이면 달마다 누가 사고 누가 팔았는지 볼 수 있습니다.")),
    h("div", { class: "stage" },
      h("section", { class: "panel map-panel" },
        h("div", { class: "controls" },
          seg("지도에 표시할 값", [["level", "보유량"], ["mom", "월간 증감"], ["ytd", "연초 대비 증감"]], state.mode,
            (v) => { state.mode = v; update(); })),
        mapEl, legendEl, tl.el),
      h("section", { class: "panel" },
        h("header", {}, h("h2", {}, "국가별 순위"), h("p", {}, "나라 이름을 누르면 상세 화면으로 갑니다")),
        h("div", { class: "body" }, tableBox))),
    h("div", { class: "grid2" },
      h("section", { class: "panel" }, h("header", {}, h("h2", {}, "세계 공식 금 보유량 합계"), h("p", {}, "톤")), h("div", { class: "body" }, worldEl)),
      h("section", { class: "panel" }, h("header", {}, h("h2", {}, "금 가격"), h("p", {}, "월평균, 달러 / 트로이온스")), h("div", { class: "body" }, priceEl))),
    h("div", { class: "grid2" },
      h("section", { class: "panel" }, h("header", {}, h("h2", {}, "이달에 많이 사고판 곳"), momTitle), h("div", { class: "body" }, momEl)),
      h("section", { class: "panel" }, h("header", {}, h("h2", {}, "올해 들어 많이 사고판 곳"), ytdTitle), h("div", { class: "body" }, ytdEl))),
    h("p", { class: "note" }, noteText(ctx)));

  let map, worldChart, priceChart, momChart, ytdChart, table;

  function rows(i) {
    return holders.map((c) => ({ code: c, name: ctx.name(c), level: level(c, i), mom: mom(c, i), ytd: ytd(c, i),
      share: data.snapshot[c] ? data.snapshot[c].share : null }))
      .filter((r) => r.level != null || r.mom != null);
  }

  function update() {
    const i = state.i, rs = rows(i);
    // 지도
    const mode = state.mode;
    if (mode !== "level" && scale[mode] == null) scale[mode] = robustMax(mode === "mom" ? mom : ytd) || 1;
    const pts = rs.filter((r) => ctx.pos(r.code) && r[mode] != null && (mode === "level" ? r.level > 0 : Math.abs(r[mode]) >= 0.05))
      .map((r) => ({ name: r.name, code: r.code, row: r, value: [...ctx.pos(r.code), r[mode]] }))
      .sort((a, b) => Math.abs(b.value[2]) - Math.abs(a.value[2]));   // 큰 원을 먼저 그려 작은 원이 위에 오게
    const top = new Set(pts.slice(0, 9).map((p) => p.code));
    map.setOption({
      series: [{
        id: "bubbles", type: "scatter", coordinateSystem: "geo", data: pts,
        symbolSize: (v) => Math.max(4, Math.sqrt(Math.min(1.2, Math.abs(v[2]) / scale[mode])) * (mode === "level" ? 62 : 46)),
        itemStyle: {
          color: (p) => (mode === "level" ? th.gold : p.value[2] > 0 ? th.up : th.down),
          opacity: 0.82, borderColor: th.surface, borderWidth: 1.5,
        },
        label: { show: true, formatter: (p) => (top.has(p.data.code) ? p.name : ""), position: "right", color: th.ink,
          fontSize: 12, textBorderColor: th.surface, textBorderWidth: 3 },
        labelLayout: { hideOverlap: true },
        emphasis: { scale: 1.08, itemStyle: { opacity: 1 } },
        tooltip: {
          formatter: (p) => {
            const r = p.data.row;
            return `<div class="tip"><b>${r.name}</b>${tipRow("", "보유량", fmt.t(r.level))}${tipRow("", "월간 증감", fmt.signedT(r.mom))}`
              + `${tipRow("", "연초 대비", fmt.signedT(r.ytd))}${r.share != null ? tipRow("", "외환보유액 중 금", fmt.pct(r.share)) : ""}`
              + `<div class="sub">${fmt.month(months[i])} 기준</div></div>`;
          },
        },
      }],
    });
    legendEl.replaceChildren(...(mode === "level"
      ? [h("span", {}, h("i", { style: `background:${th.gold}` }), "원의 넓이 = 보유량(톤)")]
      : [h("span", {}, h("i", { style: `background:${th.up}` }), "증가(매입)"), h("span", {}, h("i", { style: `background:${th.down}` }), "감소(매각)"),
        h("span", {}, "원의 넓이 = 증감 폭")]),
      h("span", {}, "IMF·BIS·ECB 같은 국제기구는 지도에 없고 순위표에만 나옵니다"));

    // 순위표
    table.update(rs);

    // 세계 합계: 선택한 달 표시만 옮긴다
    worldChart.setOption({ series: [{ markLine: { data: [{ xAxis: months[i] }] } }] });
    if (priceChart) priceChart.setOption({ series: [{ markLine: { data: [{ xAxis: months[i] }] } }] });

    // 이달·연초 대비 상위
    const movers = (key) => {
      const s = rs.filter((r) => r[key] != null && Math.abs(r[key]) >= 0.05);
      const up = s.filter((r) => r[key] > 0).sort((a, b) => b[key] - a[key]).slice(0, 7);
      const down = s.filter((r) => r[key] < 0).sort((a, b) => a[key] - b[key]).slice(0, 5).reverse();
      return [...up, ...down].map((r) => ({ name: r.name, value: Math.round(r[key] * 10) / 10, color: r[key] > 0 ? th.up : th.down,
        label: r[key] > 0 ? "증가" : "감소" }));
    };
    const m1 = movers("mom"), m2 = movers("ytd");
    momTitle.textContent = fmt.month(months[i]);
    ytdTitle.textContent = `${months[i].slice(0, 4)}년 1월 ~ ${Number(months[i].slice(5, 7))}월`;
    momChart.setOption(m1.length ? rankOption(th, m1, { signed: true }) : blank(th, "이달에는 보고된 변동이 없습니다"), true);
    ytdChart.setOption(m2.length ? rankOption(th, m2, { signed: true }) : blank(th, "올해 보고된 변동이 없습니다"), true);
  }

  return {
    mounted() {
      map = makeChart(mapEl);
      map.setOption({ animation: false, tooltip: { ...tooltipBase(th), trigger: "item" }, geo: geoOption(th, ctx.name), series: [] });
      map.on("click", (p) => {
        const code = p.componentType === "geo" ? p.name : p.data && p.data.code;
        if (code && ctx.isCountry(code)) location.hash = `#country/${code}`;
      });
      table = dataTable([
        { key: "name", label: "국가", cls: "name", sort: (r) => r.name,
          render: (r) => (ctx.isCountry(r.code) ? h("a", { href: `#country/${r.code}` }, r.name) : r.name) },
        { key: "level", label: "보유량", sort: (r) => r.level, render: (r) => fmt.t(r.level) },
        { key: "mom", label: "월간", sort: (r) => r.mom, render: (r) => deltaCell(r.mom) },
        { key: "ytd", label: "연초 대비", sort: (r) => r.ytd, render: (r) => deltaCell(r.ytd) },
      ], [], { sortKey: "level", limit: 15 });
      tableBox.append(table.el);
      worldChart = makeChart(worldEl);
      worldChart.setOption(timeOption(th, months, [{ name: "세계 합계", data: world, color: th.gold, area: true }],
        { markMonth: months[state.i], zeroBased: false, axisFmt: (v) => fmt.n(v, 0) }));
      if (priceSeries.some((v) => v != null)) {
        priceChart = makeChart(priceEl);
        priceChart.setOption(timeOption(th, months, [{ name: "금 가격", data: priceSeries, color: th.s1, area: true }],
          { markMonth: months[state.i], valueFmt: (v) => "$" + fmt.n(v, 0), axisFmt: (v) => fmt.n(v, 0) }));
      } else {
        priceEl.replaceWith(h("p", { class: "note" }, "금 가격 자료가 아직 없습니다."));
      }
      momChart = makeChart(momEl);
      ytdChart = makeChart(ytdEl);
      update();
    },
    cleanup: () => tl.stop(),
  };
}

function blank(th, text) {
  return { title: { text, left: "center", top: "middle", textStyle: { color: th.ink2, fontSize: 13, fontWeight: 400 } }, series: [] };
}

function noteText(ctx) {
  const r = ctx.meta.data.reserves || {};
  const parts = ["보유량은 World Gold Council 이 IMF 통계와 각국 중앙은행 발표를 모아 낸 수치입니다."];
  if (r.estimated_points) parts.push("분기 자료 사이의 달은 직전 보유량에 월간 증감을 더해 채웠습니다.");
  parts.push("늦게 보고하는 나라는 최근 석 달 안의 마지막 값을 표시합니다.");
  return parts.join(" ");
}

function emptyNotice(ctx, data) {
  const snap = Object.entries(data.snapshot || {});
  const box = h("div", { class: "notice" },
    h("h2", {}, "보유량 자료가 아직 없습니다"),
    h("p", {}, "World Gold Council 엑셀은 로그인 후에만 받을 수 있어, 내려받은 파일을 저장소에 올려 주어야 합니다."),
    h("ol", {},
      h("li", {}, h("a", { href: ctx.meta.wgc_page, target: "_blank", rel: "noopener" }, "gold.org 의 ‘Gold reserves by country’"), " 에서 엑셀 파일을 내려받습니다."),
      h("li", {}, "GitHub 저장소의 ", h("code", {}, "raw/wgc/"), " 폴더에 파일을 올립니다 (Add file → Upload files)."),
      h("li", {}, "몇 분 뒤 이 화면에 자동으로 반영됩니다.")));
  if (snap.length) box.append(h("p", { class: "note" }, `현황표만 읽혔습니다(${snap.length}개국). 월별 추이를 보려면 ‘Changes’ 와 ‘Quarterly’ 파일도 함께 올려 주세요.`));
  return box;
}
