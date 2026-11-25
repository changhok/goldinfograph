// 화면 위쪽의 실시간 금 시세 그래프. TradingView 무료 위젯을 그대로 끼워 넣는다(확대·이동·기간·봉 단위 변경 가능).
// 종목 기호는 config/sources.json 의 live_chart 에서 바꾼다. 위젯은 TradingView 서버에서 직접 그려지므로
// 이 사이트의 자료 갱신과 무관하게 항상 최신 시세가 보인다.
import { h, seg } from "./lib.js";

const store = {
  get(k, d) { try { const v = localStorage.getItem(k); return v == null ? d : v; } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch { /* 저장이 막힌 브라우저에서는 기억만 못 할 뿐 동작은 한다 */ } },
};

// 그래프 높이(픽셀): 화면 높이의 60%, 최소 460 ~ 최대 720
const chartHeight = () => Math.round(Math.max(460, Math.min(720, window.innerHeight * 0.6)));

function widget(symbol, dark) {
  // 위젯 스크립트가 자기 틀의 크기를 마음대로 바꾸므로, 높이가 고정된 바깥 상자(live-frame) 안에 넣고
  // 위젯에도 같은 높이를 숫자로 알려 준다. 이렇게 해야 그래프가 상자 밖으로 삐져나오지 않는다.
  const px = chartHeight();
  const inner = h("div", { class: "tradingview-widget-container", style: "width:100%;height:100%" },
    h("div", { class: "tradingview-widget-container__widget", style: "width:100%;height:100%" }));
  const s = document.createElement("script");
  s.src = "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js";
  s.async = true;
  s.text = JSON.stringify({
    width: "100%", height: px, symbol, interval: "60", timezone: "Asia/Seoul", theme: dark ? "dark" : "light", style: "1", locale: "kr",
    allow_symbol_change: true, hide_side_toolbar: true, withdateranges: true, save_image: false, calendar: false,
    support_host: "https://www.tradingview.com",
  });
  inner.append(s);
  return h("div", { class: "live-frame", style: `height:${px}px` }, inner);
}

export function mountLive(el, symbols) {
  const panes = [
    { key: "global", title: "국제 금 시세", unit: "달러 / 트로이온스", symbol: symbols.global || "OANDA:XAUUSD" },
    { key: "korea", title: "원화 금 시세", unit: "원화 기준", symbol: symbols.korea || "XAUKRWUSDT.P" },
  ];
  let open = store.get("gold-live-open", "1") === "1";
  let pinned = store.get("gold-live-pin", "0") === "1";
  let tab = store.get("gold-live-tab", "global");
  const dark = () => matchMedia("(prefers-color-scheme: dark)").matches;
  const narrow = () => matchMedia("(max-width: 900px)").matches;
  const body = h("div", { class: "live-charts" });
  const loaded = {};

  function draw() {
    el.classList.toggle("pinned", pinned && open);
    el.classList.toggle("closed", !open);
    body.hidden = !open;
    if (!open) return;
    for (const p of panes) {
      const show = !narrow() || p.key === tab;       // 좁은 화면에서는 고른 것 하나만 불러온다
      if (show && !loaded[p.key]) {
        loaded[p.key] = h("figure", { class: "live-pane" }, h("figcaption", {}, h("b", {}, p.title), h("span", {}, p.unit)), widget(p.symbol, dark()));
        body.append(loaded[p.key]);
      }
      if (loaded[p.key]) loaded[p.key].hidden = !show;
    }
    body.dataset.count = narrow() ? "1" : "2";
  }

  const tabs = seg("시세 선택", panes.map((p) => [p.key, p.title]), tab, (v) => { tab = v; store.set("gold-live-tab", v); draw(); });
  tabs.classList.add("narrow-only");
  const pinBtn = h("button", { type: "button", class: "pill btn", "aria-pressed": String(pinned),
    onclick: () => { pinned = !pinned; store.set("gold-live-pin", pinned ? "1" : "0"); pinBtn.setAttribute("aria-pressed", String(pinned)); pinBtn.textContent = pinned ? "고정 해제" : "스크롤해도 고정"; draw(); } },
    pinned ? "고정 해제" : "스크롤해도 고정");
  const openBtn = h("button", { type: "button", class: "pill btn",
    onclick: () => { open = !open; store.set("gold-live-open", open ? "1" : "0"); openBtn.textContent = open ? "접기" : "실시간 시세 펼치기"; pinBtn.hidden = !open; tabs.hidden = !open; draw(); } },
    open ? "접기" : "실시간 시세 펼치기");
  pinBtn.hidden = !open; tabs.hidden = !open;
  el.replaceChildren(h("div", { class: "live-bar" }, h("strong", {}, "실시간 금 시세"), tabs, h("span", { class: "spacer" }), pinBtn, openBtn), body);
  draw();
  matchMedia("(max-width: 900px)").addEventListener("change", draw);
  // 밝기가 바뀌면 위젯을 새 색으로 다시 만든다
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => { for (const k of Object.keys(loaded)) { loaded[k].remove(); delete loaded[k]; } draw(); });
}
