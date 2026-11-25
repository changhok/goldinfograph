// 화면들이 함께 쓰는 도구: DOM 만들기, 숫자·날짜 표기, 자료 불러오기, 조작부, 차트 기본 설정.
/* global echarts */

// ---------------------------------------------------------------- DOM
export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "html") el.innerHTML = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) {
    if (c == null || c === false) continue;
    el.append(c.nodeType ? c : document.createTextNode(String(c)));
  }
  return el;
}

// ---------------------------------------------------------------- 색 (style.css 의 변수를 그대로 읽는다)
const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
export function theme() {
  const names = ["page", "surface", "ink", "ink-2", "rule", "grid", "land", "land-line", "sea", "gold", "up", "down",
    "imp", "exp", "neutral", "s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8"];
  const t = {};
  for (const n of names) t[n.replace(/-(\w)/g, (_, c) => c.toUpperCase())] = cssVar(`--${n}`);
  t.series = [t.s1, t.s2, t.s3, t.s4, t.s5, t.s6, t.s7, t.s8];
  return t;
}

// ---------------------------------------------------------------- 표기
const nf = (d) => new Intl.NumberFormat("ko-KR", { minimumFractionDigits: 0, maximumFractionDigits: d });
export const fmt = {
  n(v, d = 1) { return v == null || Number.isNaN(v) ? "–" : nf(d).format(v); },
  t(v, d) { // 톤: 큰 값은 소수 없이, 작은 값은 한두 자리
    if (v == null) return "–";
    const a = Math.abs(v);
    return nf(d ?? (a >= 100 ? 0 : a >= 10 ? 1 : 2)).format(v) + "t";
  },
  signedT(v) {
    if (v == null) return "–";
    const a = Math.abs(v);
    const s = nf(a >= 100 ? 0 : a >= 10 ? 1 : 2).format(a);
    return (v > 0 ? "+" : v < 0 ? "−" : "") + s + "t";
  },
  money(v, unit = "달러") { // 입력은 백만 단위
    if (v == null) return "–";
    const a = Math.abs(v);
    if (a >= 1e6) return nf(2).format(v / 1e6) + "조 " + unit;
    if (a >= 100) return nf(a >= 1e4 ? 0 : 1).format(v / 100) + "억 " + unit;
    return nf(1).format(v) + "백만 " + unit;
  },
  moneyShort(v) { // 표의 좁은 칸용: 억 단위 숫자만
    if (v == null) return "–";
    const e = v / 100;
    return nf(Math.abs(e) >= 100 ? 0 : Math.abs(e) >= 1 ? 1 : 2).format(e) + "억";
  },
  pct(v) { return v == null ? "–" : nf(1).format(v) + "%"; },
  month(ym) { return ym ? `${ym.slice(0, 4)}년 ${Number(ym.slice(5, 7))}월` : "–"; },
  monthShort(ym) { return ym ? `${ym.slice(2, 4)}.${ym.slice(5, 7)}` : ""; },
};

// ---------------------------------------------------------------- 자료 불러오기
const cache = new Map();
let version = "";
export function setDataVersion(v) { version = v || ""; }
export function getJSON(path) {
  if (!cache.has(path)) {
    const url = `data/${path}${version ? `?v=${version}` : ""}`;
    cache.set(path, fetch(url).then((r) => {
      if (!r.ok) throw new Error(`${path} 을(를) 불러오지 못했습니다 (HTTP ${r.status})`);
      return r.json();
    }).catch((e) => { cache.delete(path); throw e; }));
  }
  return cache.get(path);
}

// ---------------------------------------------------------------- 조작부
// 여러 선택지 중 하나를 고르는 버튼 묶음
export function seg(label, options, value, onChange) {
  const wrap = h("div", { class: "seg", role: "group", "aria-label": label });
  const btns = options.map(([val, text]) => h("button", {
    type: "button", "aria-pressed": String(val === value),
    onclick: () => { btns.forEach((b, i) => b.setAttribute("aria-pressed", String(options[i][0] === val))); onChange(val); },
  }, text));
  wrap.append(...btns);
  return wrap;
}

const ICON = {
  play: '<svg viewBox="0 0 16 16"><path d="M4 2.5v11l9-5.5z"/></svg>',
  pause: '<svg viewBox="0 0 16 16"><path d="M3.5 2.5h3v11h-3zM9.5 2.5h3v11h-3z"/></svg>',
  prev: '<svg viewBox="0 0 16 16"><path d="M10.5 2.5v11L3.5 8z"/></svg>',
  next: '<svg viewBox="0 0 16 16"><path d="M5.5 2.5v11l7-5.5z"/></svg>',
};

// 월 선택 막대: 이전/다음 달, 재생, 끌어서 이동
export function timeline(months, index, onChange) {
  let i = Math.max(0, Math.min(index, months.length - 1));
  let timer = null;
  const when = h("span", { class: "when", "aria-live": "polite" }, fmt.month(months[i]));
  const range = h("input", { type: "range", min: 0, max: months.length - 1, value: i, "aria-label": "기준 월" });
  const playBtn = h("button", { class: "icon-btn", type: "button", "aria-label": "재생", html: ICON.play });
  const set = (n, fire = true) => {
    i = Math.max(0, Math.min(n, months.length - 1));
    range.value = i;
    when.textContent = fmt.month(months[i]);
    if (fire) onChange(i);
  };
  const stop = () => { clearInterval(timer); timer = null; playBtn.innerHTML = ICON.play; playBtn.setAttribute("aria-label", "재생"); };
  const play = () => {
    if (i >= months.length - 1) set(Math.max(0, months.length - 61));   // 끝에 있으면 5년 전부터 다시
    playBtn.innerHTML = ICON.pause; playBtn.setAttribute("aria-label", "멈춤");
    timer = setInterval(() => { if (i >= months.length - 1) stop(); else set(i + 1); }, 650);
  };
  range.addEventListener("input", () => { stop(); set(Number(range.value)); });
  playBtn.addEventListener("click", () => (timer ? stop() : play()));
  const el = h("div", { class: "timeline" },
    playBtn,
    h("button", { class: "icon-btn", type: "button", "aria-label": "이전 달", html: ICON.prev, onclick: () => { stop(); set(i - 1); } }),
    when,
    h("button", { class: "icon-btn", type: "button", "aria-label": "다음 달", html: ICON.next, onclick: () => { stop(); set(i + 1); } }),
    range,
    h("span", { class: "muted num" }, `${fmt.monthShort(months[0])} – ${fmt.monthShort(months[months.length - 1])}`));
  return { el, get: () => i, set, stop };
}

// 국가 선택 상자 (이름 순)
export function countrySelect(codes, nameOf, value, onChange, firstOption) {
  const sel = h("select", { "aria-label": "국가 선택", onchange: () => onChange(sel.value || null) });
  if (firstOption) sel.append(h("option", { value: "" }, firstOption));
  [...codes].sort((a, b) => nameOf(a).localeCompare(nameOf(b), "ko")).forEach((c) =>
    sel.append(h("option", { value: c, selected: c === value }, nameOf(c))));
  return sel;
}

// 정렬되는 표. columns: [{key, label, cls, render(row), sort(row)}]
export function dataTable(columns, rows, { sortKey, desc = true, limit } = {}) {
  let key = sortKey, down = desc, showAll = !limit;
  const wrap = h("div", { class: "table-wrap" });
  const draw = () => {
    const col = columns.find((c) => c.key === key);
    const sorted = col && col.sort ? [...rows].sort((a, b) => {
      const x = col.sort(a), y = col.sort(b);
      if (x == null && y == null) return 0;
      if (x == null) return 1;
      if (y == null) return -1;
      return typeof x === "string" ? (down ? y.localeCompare(x, "ko") : x.localeCompare(y, "ko")) : (down ? y - x : x - y);
    }) : rows;
    const shown = showAll ? sorted : sorted.slice(0, limit);
    const thead = h("thead", {}, h("tr", {}, h("th", {}, "#"), columns.map((c) => h("th", { class: c.cls || "" },
      c.sort ? h("button", { type: "button", "aria-sort": c.key === key ? (down ? "descending" : "ascending") : null,
        onclick: () => { if (key === c.key) down = !down; else { key = c.key; down = true; } draw(); } }, c.label) : c.label))));
    const tbody = h("tbody", {}, shown.map((r, n) => h("tr", {}, h("td", { class: "num" }, n + 1),
      columns.map((c) => { const v = c.render(r); return h("td", { class: `${c.cls || "num"}` }, v); }))));
    wrap.replaceChildren(h("table", {}, thead, tbody));
    if (limit && sorted.length > limit) {
      wrap.append(h("p", { class: "note", style: "padding:0 10px 8px" }, h("button", {
        type: "button", class: "pill", style: "cursor:pointer;background:none;font:inherit;font-size:12px",
        onclick: () => { showAll = !showAll; draw(); },
      }, showAll ? `상위 ${limit}개만 보기` : `전체 ${sorted.length}개 보기`)));
    }
  };
  draw();
  return { el: wrap, update(newRows) { rows = newRows; draw(); } };
}

// 증감 표기용 (▲/▼ 는 색, 숫자는 글자색)
export function deltaCell(v) {
  if (v == null) return h("span", { class: "muted" }, "–");
  if (Math.abs(v) < 0.005) return h("span", { class: "muted" }, "0");
  return h("span", { class: v > 0 ? "delta-up" : "delta-down" }, fmt.signedT(v).replace(/^[+−]/, ""));
}

// ---------------------------------------------------------------- 차트
const charts = new Set();
export function makeChart(el) {
  const c = echarts.init(el, null, { renderer: "canvas" });
  charts.add(c);
  return c;
}
export function disposeCharts() { charts.forEach((c) => c.dispose()); charts.clear(); }
window.addEventListener("resize", () => charts.forEach((c) => c.resize()));

export function tooltipBase(th) {
  return {
    backgroundColor: th.surface, borderColor: th.rule, borderWidth: 1, padding: [8, 12],
    textStyle: { color: th.ink, fontSize: 13 }, extraCssText: "box-shadow:0 4px 18px rgba(0,0,0,.14);border-radius:6px;",
    confine: true,
  };
}
export const tipRow = (color, label, value) =>
  `<div class="row"><span>${color ? `<i style="background:${color}"></i>` : ""}${label}</span><span>${value}</span></div>`;

// 월 축: 연도만 표시하고 기간이 길면 간격을 넓힌다
function monthAxis(months, th) {
  const years = months.length / 12;
  const step = years > 18 ? 5 : years > 8 ? 2 : 1;
  return {
    type: "category", data: months, boundaryGap: true,
    axisLine: { lineStyle: { color: th.rule } }, axisTick: { show: false },
    axisLabel: {
      color: th.ink2, fontSize: 12, hideOverlap: true,
      interval: (i, v) => (years <= 2.5 ? true : v.endsWith("-01") && Number(v.slice(0, 4)) % step === 0),
      formatter: (v) => (years <= 2.5 ? fmt.monthShort(v) : v.slice(0, 4)),
    },
  };
}
function valueAxis(th, unitFmt) {
  return {
    type: "value", scale: false, splitNumber: 4,
    axisLabel: { color: th.ink2, fontSize: 12, formatter: unitFmt || ((v) => fmt.n(v, 0)) },
    splitLine: { lineStyle: { color: th.grid } },
  };
}

// 월별 선·막대 그래프. series: [{name, data, color, type: 'line'|'bar', stack, signColors}]
export function timeOption(th, months, series, { valueFmt = (v) => fmt.t(v), axisFmt, markMonth, zeroBased = true, legend } = {}) {
  const showLegend = legend ?? series.length > 1;
  const thinBars = months.length > 48;
  return {
    animation: false,
    grid: { left: 8, right: 16, top: showLegend ? (series.length > 3 ? 60 : 36) : 16, bottom: 4, containLabel: true },
    legend: showLegend ? { top: 0, left: 0, icon: "circle", itemWidth: 9, itemHeight: 9, textStyle: { color: th.ink2, fontSize: 12.5 } } : undefined,
    tooltip: {
      ...tooltipBase(th), trigger: "axis",
      axisPointer: { type: "line", lineStyle: { color: th.neutral, width: 1 } },
      formatter: (ps) => `<div class="tip"><b>${fmt.month(ps[0].axisValue)}</b>` + ps.filter((p) => p.value != null)
        .map((p) => tipRow(typeof p.color === "string" ? p.color : th.neutral, p.seriesName, valueFmt(p.value))).join("") + "</div>",
    },
    xAxis: monthAxis(months, th),
    yAxis: { ...valueAxis(th, axisFmt), scale: !zeroBased },
    dataZoom: [{ type: "inside", zoomOnMouseWheel: "ctrl", moveOnMouseMove: true }],
    series: series.map((s) => {
      const base = { name: s.name, type: s.type || "line", data: s.data, stack: s.stack, emphasis: { focus: "none" } };
      if (base.type === "line") {
        Object.assign(base, {
          showSymbol: false, symbol: "circle", symbolSize: 8, connectNulls: false, lineStyle: { width: 2, color: s.color },
          itemStyle: { color: s.color, borderColor: th.surface, borderWidth: 2 },
          areaStyle: s.area ? { color: s.color, opacity: 0.1 } : undefined,
        });
      } else {
        Object.assign(base, {
          barMaxWidth: 24, barCategoryGap: thinBars ? "20%" : "35%",
          itemStyle: s.signColors
            ? { color: (p) => (p.value >= 0 ? s.signColors[0] : s.signColors[1]),
                borderRadius: 0 }
            : { color: s.color, borderColor: th.surface, borderWidth: s.stack && !thinBars ? 1 : 0,
                borderRadius: s.stack ? 0 : [3, 3, 0, 0] },
        });
      }
      if (markMonth && s === series[0]) {
        base.markLine = { silent: true, symbol: "none", animation: false, label: { show: false },
          lineStyle: { color: th.ink, width: 1, type: "solid", opacity: 0.55 }, data: [{ xAxis: markMonth }] };
      }
      return base;
    }),
  };
}

// 가로 막대 순위. items: [{name, value, color}] (양수·음수 섞여도 됨)
export function rankOption(th, items, { valueFmt = (v) => fmt.t(v), signed = false } = {}) {
  const rev = [...items].reverse();   // ECharts 는 아래에서 위로 그리므로 뒤집는다
  return {
    animation: false,
    grid: { left: 8, right: 64, top: 6, bottom: 4, containLabel: true },
    tooltip: {
      ...tooltipBase(th), trigger: "item",
      formatter: (p) => `<div class="tip"><b>${p.name}</b>${tipRow(p.color, p.data.kind || "", valueFmt(p.value))}</div>`,
    },
    xAxis: { type: "value", axisLabel: { show: false }, splitLine: { lineStyle: { color: th.grid } } },
    yAxis: { type: "category", data: rev.map((d) => d.name), axisTick: { show: false }, axisLine: { lineStyle: { color: th.rule } },
      axisLabel: { color: th.ink, fontSize: 12.5, width: 110, overflow: "truncate" } },
    series: [{
      type: "bar", barMaxWidth: 18,
      data: rev.map((d) => ({ value: d.value, kind: d.label,
        itemStyle: { color: d.color, borderRadius: d.value >= 0 ? [0, 4, 4, 0] : [4, 0, 0, 4] } })),
      label: { show: true, position: "right", color: th.ink2, fontSize: 12, formatter: (p) => (signed ? fmt.signedT(p.value) : valueFmt(p.value)) },
    }],
  };
}

// ---------------------------------------------------------------- 지도
let mapReady = null;
export function ensureWorldMap(countries) {
  if (!mapReady) {
    mapReady = fetch("vendor/world-50m.topo.json").then((r) => r.json()).then((topo) => {
      const byNum = {};
      for (const [iso3, c] of Object.entries(countries)) if (c.num) byNum[c.num] = iso3;
      const geo = window.topojson.feature(topo, topo.objects.countries);
      geo.features = geo.features.filter((f) => f.id !== "010");                 // 남극 제외
      geo.features.forEach((f) => { f.properties.name = byNum[f.id] || f.properties.name; });
      echarts.registerMap("world", geo);
    });
  }
  return mapReady;
}

export function geoOption(th, nameOf) {
  return {
    map: "world", roam: true, scaleLimit: { min: 1, max: 14 },
    left: 0, right: 0, top: 6, bottom: 6, boundingCoords: [[-168, 78], [180, -56]],
    itemStyle: { areaColor: th.land, borderColor: th.landLine, borderWidth: 0.6 },
    emphasis: { label: { show: false }, itemStyle: { areaColor: th.neutral } },
    select: { disabled: true },
    tooltip: { show: true, ...tooltipBase(th), formatter: (p) => `<div class="tip"><b>${nameOf(p.name)}</b></div>` },
  };
}

// 값 배열에서 i 번째 또는 그 이전 최근 값(최대 back 개월 전)을 찾는다. → [값, 실제 위치]
export function latestAt(arr, i, back = 3) {
  if (!arr) return [null, -1];
  for (let k = i; k >= Math.max(0, i - back); k--) if (arr[k] != null) return [arr[k], k];
  return [null, -1];
}
export const sum = (a) => a.reduce((s, v) => s + (v || 0), 0);
