// 자료 현황 화면: 출처별 갱신 상태, 보유 기간, 파일 인식 결과, 자료 읽는 법.
import { fmt, h } from "../lib.js";

const day = (s) => (s ? s.slice(0, 10) : "–");
const span = (a) => (a ? `${fmt.month(a[0])} ~ ${fmt.month(a[1])}` : "–");

export async function render(root, ctx) {
  const { meta } = ctx;
  const S = meta.sources || {}, D = meta.data || {};
  const badge = (s) => (!s ? h("span", { class: "pill" }, "아직 실행 전") : s.ok ? h("span", { class: "pill ok" }, "정상") : h("span", { class: "pill bad" }, "확인 필요"));
  const section = (title, s, rows, extra) => h("section", { class: "panel" }, h("div", { class: "body", style: "padding-top:14px" },
    h("h2", {}, title, badge(s)),
    h("dl", {}, rows.filter(Boolean).flatMap(([k, v]) => [h("dt", {}, k), h("dd", {}, v)])),
    extra));

  const wgcReport = (S.wgc && S.wgc.report) || [];
  const swissReport = (S.swiss && S.swiss.report) || {};

  root.append(
    h("div", { class: "lede" }, h("h1", {}, "자료 현황"),
      h("p", {}, "세 출처의 자료가 언제, 어디까지 들어왔는지 보여 줍니다. 문제가 생기면 여기에 원인이 적힙니다.")),
    h("div", { class: "status stack" },
      section("금 보유량 — World Gold Council 엑셀", S.wgc, [
        ["보유 기간", D.reserves && D.reserves.available ? span(D.reserves.months) : "자료 없음"],
        ["국가·기관 수", D.reserves && D.reserves.countries != null ? `${D.reserves.countries}곳` : "–"],
        ["올린 파일", (S.wgc && S.wgc.files && S.wgc.files.length) ? S.wgc.files.join(", ") : "없음"],
        ["마지막 확인", day(S.wgc && S.wgc.last_run)],
        ["상태", (S.wgc && S.wgc.message) || "–"],
        ["갱신 방법", h("span", {}, h("a", { href: meta.wgc_page, target: "_blank", rel: "noopener" }, "gold.org"), " 에서 엑셀을 내려받아 저장소의 ", h("code", {}, "raw/wgc/"), " 폴더에 올리면 자동 반영됩니다 (매달 10일 무렵 새 파일이 나옵니다).")],
      ], wgcReport.length ? h("details", {}, h("summary", {}, `시트별 인식 결과 (${wgcReport.length}개)`),
        h("div", { class: "table-wrap" }, h("table", {}, h("thead", {}, h("tr", {}, ["", "파일", "시트", "결과", "기간", "국가 수", "못 읽은 이름"].map((x, n) => h("th", { class: n ? "name" : "" }, x)))),
          h("tbody", {}, wgcReport.map((r, n) => h("tr", {}, h("td", {}, n + 1), h("td", { class: "name" }, r.file), h("td", { class: "name" }, r.sheet),
            h("td", { class: "name" }, r.result || ""), h("td", { class: "name" }, r.periods ? `${r.periods[0]} ~ ${r.periods[1]}` : ""),
            h("td", { class: "name" }, r.countries ?? ""), h("td", { class: "name" }, (r.unmatched_names || []).join(", "))))))) ) : null),

      section("국가 간 교역 — UN Comtrade (HS 7108)", S.comtrade, [
        ["보유 기간", D.trade && D.trade.available ? span(D.trade.months) : "자료 없음"],
        ["신고국 수", D.trade && D.trade.reporters != null ? `${D.trade.reporters}개국` : "–"],
        ["수집 방식", S.comtrade ? (S.comtrade.mode === "key" ? "API 키 사용 — 전 세계, " + meta.start_year + "년부터" : "키 없음(무료 미리보기) — 주요 30개국, 최근 2년") : "–"],
        ["남은 작업", S.comtrade && S.comtrade.remaining_months ? `${S.comtrade.remaining_months}개월분을 이후 실행에서 이어 받습니다` : "없음"],
        ["마지막 확인", day(S.comtrade && S.comtrade.last_run)],
        ["상태", (S.comtrade && S.comtrade.message) || "–"],
        S.comtrade && S.comtrade.mode !== "key" ? ["전체 수집으로 넓히기", h("span", {}, "UN Comtrade 무료 키를 발급받아 저장소 Secret ", h("code", {}, "COMTRADE_API_KEY"), " 로 등록하면 다음 실행부터 전 세계·전체 기간을 받습니다. 방법은 저장소 README 에 있습니다.")] : null,
      ]),

      section("스위스 교역 — 스위스 관세청 BAZG (SwissImpex 원자료)", S.swiss, [
        ["보유 기간", D.swiss && D.swiss.available ? span(D.swiss.months) : "자료 없음"],
        ["상대국 수", D.swiss && D.swiss.partners != null ? `${D.swiss.partners}개국` : "–"],
        ["통계키(911~914)", D.swiss && D.swiss.available ? (D.swiss.has_keys ? "있음" : "없음") : "–"],
        ["마지막 확인", day(S.swiss && S.swiss.last_run)],
        ["상태", (S.swiss && S.swiss.message) || "–"],
      ], Object.keys(swissReport).length ? h("details", {}, h("summary", {}, "파일별 열 인식 결과"),
        h("div", { class: "table-wrap" }, h("table", {}, h("thead", {}, h("tr", {}, ["", "파일", "사용한 열", "금 행 수", "기간", "받은 주소"].map((x, n) => h("th", { class: n ? "name" : "" }, x)))),
          h("tbody", {}, Object.entries(swissReport).map(([id, r], n) => h("tr", {}, h("td", {}, n + 1), h("td", { class: "name" }, id),
            h("td", { class: "name" }, Object.entries(r.columns_used || {}).map(([k, v]) => `${k}=${v}`).join(", ")),
            h("td", { class: "name" }, fmt.n(r.gold_rows, 0)), h("td", { class: "name" }, r.periods ? `${r.periods[0]} ~ ${r.periods[1]}` : ""),
            h("td", { class: "name", style: "word-break:break-all" }, r.source || ""))))))) : null),

      h("section", { class: "panel" }, h("div", { class: "body", style: "padding-top:14px" },
        h("h2", {}, "자료 읽는 법"),
        h("ul", { style: "margin:8px 0 0;padding-left:1.2em;max-width:85ch" },
          h("li", {}, "중량은 톤(t), 금액은 달러(스위스 화면은 스위스프랑)입니다. 1억 달러 = 100백만 달러."),
          h("li", {}, "보유량의 ‘연초 대비’는 WGC 월간 증감을 그해 1월부터 더한 값입니다. 월간 증감이 없는 곳은 전년 12월 말 보유량과의 차이로 계산합니다."),
          h("li", {}, "WGC 는 분기 보유량과 월간 증감을 따로 발표하며 둘의 집계 기준이 다른 나라가 있습니다(예: 튀르키예). 분기 사이의 달은 월간 증감을 따라 채우되 다음 분기 값에 맞춥니다."),
          h("li", {}, "교역 통계는 수출국 신고와 수입국 신고가 일치하지 않는 일이 흔합니다. 경유지, 신고 시점, 비공개 처리 때문입니다."),
          h("li", {}, "UN Comtrade 는 나라마다 신고가 몇 달씩 늦습니다. 최근 달은 신고국이 적어 합계가 작게 보입니다."),
          h("li", {}, "스위스 통계의 국가별 금 자료는 2012년 1월부터 있습니다. 수입 상대국은 원산지, 수출 상대국은 목적지입니다."),
          h("li", {}, "이 사이트는 각 기관이 공개한 수치를 가공 없이 옮기며, 투자 판단의 근거로 만든 것이 아닙니다.")),
        (meta.unknown_codes && meta.unknown_codes.length) ? h("details", {}, h("summary", {}, `국가로 연결하지 못한 코드·이름 ${meta.unknown_codes.length}개`),
          h("p", { class: "note" }, meta.unknown_codes.join(", "))) : null))));
  return {};
}
