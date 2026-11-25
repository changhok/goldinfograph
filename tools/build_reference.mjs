// 국가 기준표와 지도·차트 라이브러리를 npm 패키지에서 다시 만들어 내는 도구.
// 평소에는 실행할 필요가 없고, 국가 목록이나 라이브러리 버전을 바꿀 때만 실행한다.
//   cd tools && npm install && node build_reference.mjs
import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");
const countries = require("world-countries");

// 한국어 표기 보정 (패키지 번역이 옛 표기이거나 길 때)
const KO = {
  TUR: "튀르키예", USA: "미국", GBR: "영국", ARE: "아랍에미리트", KOR: "한국", PRK: "북한",
  HKG: "홍콩", MAC: "마카오", TWN: "대만", RUS: "러시아", CZE: "체코", COD: "콩고민주공화국",
  COG: "콩고공화국", ZAF: "남아프리카공화국", SAU: "사우디아라비아", LAO: "라오스", VNM: "베트남",
};

const list = countries
  .filter((c) => c.cca3 && c.cca3 !== "UNK" || c.cca3 === "UNK")
  .map((c) => ({
    iso3: c.cca3 === "UNK" ? "XKX" : c.cca3,
    iso2: c.cca3 === "UNK" ? "XK" : c.cca2,
    m49: c.ccn3 ? Number(c.ccn3) : null,
    ko: KO[c.cca3] || (c.translations.kor && c.translations.kor.common) || c.name.common,
    en: c.name.common,
    lat: c.latlng[0],
    lon: c.latlng[1],
    region: c.region,
    aliases: [c.name.official, ...(c.altSpellings || [])].filter((s) => s && s.length > 3),
  }))
  .sort((a, b) => a.iso3.localeCompare(b.iso3));

fs.mkdirSync(path.join(root, "pipeline/reference"), { recursive: true });
fs.writeFileSync(
  path.join(root, "pipeline/reference/countries.json"),
  JSON.stringify(list, null, 0).replace(/\},\{/g, "},\n{") + "\n"
);

// 사이트에서 쓰는 라이브러리와 세계 지도 (CDN 없이 저장소 안에 보관)
const vendor = path.join(root, "site/vendor");
fs.mkdirSync(vendor, { recursive: true });
const copy = (from, to) => fs.copyFileSync(require.resolve(from), path.join(vendor, to));
copy("echarts/dist/echarts.min.js", "echarts.min.js");
copy("topojson-client/dist/topojson-client.min.js", "topojson-client.min.js");
copy("world-atlas/countries-50m.json", "world-50m.topo.json");
const v = (n) => require(`${n}/package.json`).version;
fs.writeFileSync(
  path.join(vendor, "VERSIONS.txt"),
  ["echarts", "topojson-client", "world-atlas", "world-countries"].map((n) => `${n} ${v(n)}`).join("\n") + "\n"
);
console.log(`countries: ${list.length}, vendor files written`);
