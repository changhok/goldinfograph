// 시작점: 공통 자료를 불러오고, 주소(#reserves, #flows, #country/KOR …)에 맞는 화면을 그린다.
import { disposeCharts, ensureWorldMap, getJSON, h, setDataVersion } from "./lib.js";

const VIEWS = {
  reserves: () => import("./views/reserves.js"),
  flows: () => import("./views/flows.js"),
  country: () => import("./views/country.js"),
  swiss: () => import("./views/swiss.js"),
  status: () => import("./views/status.js"),
};

const root = document.getElementById("view");
let ctx = null;
let cleanup = null;
let token = 0;

async function route() {
  const [name, param] = (location.hash.replace(/^#\/?/, "") || "reserves").split("/");
  const view = VIEWS[name] ? name : "reserves";
  document.querySelectorAll(".tabs a").forEach((a) =>
    (a.dataset.view === view ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current")));
  const mine = ++token;
  if (cleanup) { try { cleanup(); } catch { /* 화면 정리 중 오류는 무시 */ } cleanup = null; }
  disposeCharts();
  root.replaceChildren(h("p", { class: "loading" }, "자료를 불러오는 중입니다…"));
  try {
    const mod = await VIEWS[view]();
    if (mine !== token) return;
    const box = h("div", {});
    const result = await mod.render(box, ctx, param ? decodeURIComponent(param) : null);
    if (mine !== token) return;
    root.replaceChildren(box);
    if (result && result.mounted) result.mounted();   // 차트는 화면에 붙은 뒤에 그려야 크기가 맞는다
    cleanup = result && result.cleanup;
  } catch (e) {
    console.error(e);
    root.replaceChildren(h("div", { class: "notice" }, h("h2", {}, "화면을 그리지 못했습니다"),
      h("p", {}, String(e.message || e)), h("p", { class: "note" }, "잠시 뒤 새로 고침 해 주세요. 계속되면 ‘자료 현황’ 화면에서 수집 상태를 확인하세요.")));
  }
}

async function boot() {
  const meta = await fetch("data/meta.json", { cache: "no-cache" }).then((r) => r.json());
  setDataVersion(meta.data_hash);
  const countries = await getJSON("countries.json");
  await ensureWorldMap(countries);
  ctx = {
    meta, countries,
    name: (code) => (countries[code] && countries[code].ko) || (code && code.startsWith("?") ? `미분류(${code.slice(1)})` : code),
    isCountry: (code) => Boolean(countries[code] && !countries[code].special),
    pos: (code) => (countries[code] && countries[code].lat != null ? [countries[code].lon, countries[code].lat] : null),
  };
  const when = (meta.generated || "").slice(0, 10);
  document.getElementById("updated").textContent = when ? `자료 갱신 ${when}` : "";
  window.addEventListener("hashchange", route);
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", route);   // 밝기 바뀌면 차트 색도 다시
  route();
}

boot().catch((e) => {
  console.error(e);
  root.replaceChildren(h("div", { class: "notice" }, h("h2", {}, "자료를 불러오지 못했습니다"), h("p", {}, String(e.message || e))));
});
