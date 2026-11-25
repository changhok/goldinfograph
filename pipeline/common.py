"""수집·변환 스크립트가 함께 쓰는 도구 모음: 경로, 설정, 국가 기준표, 파일 입출력, 상태 기록."""
from __future__ import annotations

import csv
import datetime as dt
import gzip
import io
import json
import os
import re
import unicodedata
from pathlib import Path

# 테스트에서는 GOLDINFOGRAPH_ROOT 로 작업 폴더를 바꿔 실제 자료를 건드리지 않는다
ROOT = Path(os.environ.get("GOLDINFOGRAPH_ROOT") or Path(__file__).resolve().parent.parent)
CONFIG = ROOT / "config" / "sources.json"
STORE = ROOT / "data-store"          # 수집한 원자료를 정리해 쌓아 두는 곳 (사이트는 직접 읽지 않음)
SITE_DATA = ROOT / "site" / "data"   # 사이트가 읽는 JSON
REFERENCE = Path(__file__).resolve().parent / "reference"
STATUS = STORE / "status.json"


# ---------------------------------------------------------------- 설정·시간
def load_config() -> dict:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def today() -> dt.date:
    return dt.datetime.now(dt.timezone.utc).date()


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def month_range(start: str, end: str) -> list[str]:
    """'YYYY-MM' 두 개 사이의 모든 달(양끝 포함)."""
    y, m = int(start[:4]), int(start[5:7])
    ey, em = int(end[:4]), int(end[5:7])
    out = []
    while (y, m) <= (ey, em):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def add_months(ym: str, n: int) -> str:
    y, m = int(ym[:4]), int(ym[5:7])
    k = y * 12 + (m - 1) + n
    return f"{k // 12:04d}-{k % 12 + 1:02d}"


_MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}


def parse_period(value) -> tuple[str, str] | None:
    """parse_period_raw 결과 중 연도가 1950~2100 인 것만 인정한다 (8133.5 같은 수치를 기간으로 오해하지 않도록)."""
    if isinstance(value, bool) or (isinstance(value, float) and not value.is_integer()):
        return None
    p = _parse_period_raw(value)
    if p and 1950 <= int(p[1][:4]) <= 2100:
        return p
    return None


def _parse_period_raw(value) -> tuple[str, str] | None:
    """여러 표기의 기간을 ('M'|'Q'|'A', 'YYYY-MM') 로 바꾼다. 분기·연도는 마지막 달로 표시한다.

    예: 202401, '2024-01', '01.2024', '2024M01', 'Jan-24', 'Q3 2024', '2024Q3', 2024, 날짜 객체.
    """
    if value is None:
        return None
    if isinstance(value, (dt.datetime, dt.date)):
        return "M", f"{value.year:04d}-{value.month:02d}"
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    s = str(value).strip()
    if not s:
        return None
    low = s.lower()
    m = re.fullmatch(r"(\d{4})[-/.](\d{1,2})(?:[-/.]\d{1,2})?(?:[ t].*)?", low)
    if m and 1 <= int(m[2]) <= 12:
        return "M", f"{m[1]}-{int(m[2]):02d}"
    m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})?", low)
    if m and 1900 <= int(m[1]) <= 2100 and 1 <= int(m[2]) <= 12:
        return "M", f"{m[1]}-{m[2]}"
    m = re.fullmatch(r"(\d{1,2})[-/.](\d{4})", low)
    if m and 1 <= int(m[1]) <= 12:
        return "M", f"{m[2]}-{int(m[1]):02d}"
    m = re.fullmatch(r"(\d{4})\s*m(\d{1,2})", low)
    if m and 1 <= int(m[2]) <= 12:
        return "M", f"{m[1]}-{int(m[2]):02d}"
    m = re.fullmatch(r"([a-z]{3})[a-z]*[\s\-.'/]*(\d{2}|\d{4})", low)
    if m and m[1] in _MONTHS:
        year = int(m[2])
        if year < 100:
            year += 2000 if year < 70 else 1900
        return "M", f"{year:04d}-{_MONTHS[m[1]]:02d}"
    m = re.fullmatch(r"(\d{4})[\s\-]*([a-z]{3})[a-z]*", low)
    if m and m[2] in _MONTHS:
        return "M", f"{m[1]}-{_MONTHS[m[2]]:02d}"
    m = re.fullmatch(r"q([1-4])[\s\-'/]*(\d{2}|\d{4})", low) or None
    if m:
        year = int(m[2])
        if year < 100:
            year += 2000 if year < 70 else 1900
        return "Q", f"{year:04d}-{int(m[1]) * 3:02d}"
    m = re.fullmatch(r"(\d{4})[\s\-:]*q([1-4])", low)
    if m:
        return "Q", f"{m[1]}-{int(m[2]) * 3:02d}"
    m = re.fullmatch(r"([1-4])q[\s\-'/]*(\d{2}|\d{4})", low)
    if m:
        year = int(m[2])
        if year < 100:
            year += 2000 if year < 70 else 1900
        return "Q", f"{year:04d}-{int(m[1]) * 3:02d}"
    m = re.fullmatch(r"(\d{4})", low)
    if m and 1950 <= int(m[1]) <= 2100:
        return "A", f"{m[1]}-12"
    return None


def to_number(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().replace("−", "-").replace("'", "").replace("’", "").replace(" ", "")
    if s in ("", "-", "–", "—", "..", "...", "n/a", "na", "NA", "null", "None"):
        return None
    if "," in s and "." in s:
        s = s.replace(",", "")
    elif "," in s:
        # 쉼표만 있으면: 세 자리 묶음이면 천 단위, 아니면 소수점
        s = s.replace(",", "") if re.fullmatch(r"-?\d{1,3}(,\d{3})+", s) else s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


# ---------------------------------------------------------------- 파일 입출력
def read_json(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, obj, pretty: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if pretty:
        text = json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True)
    else:
        text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    path.write_text(text + "\n", encoding="utf-8")


def read_csv_gz(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_csv_gz(path: Path, fields: list[str], rows) -> None:
    """내용이 같으면 파일도 같도록(mtime=0) 압축해서 git 변경 기록을 깔끔하게 유지한다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(fields)
    for r in rows:
        w.writerow(["" if r.get(k) is None else r.get(k) for k in fields] if isinstance(r, dict) else r)
    with open(path, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as gz:
        gz.write(buf.getvalue().encode("utf-8"))


def fmt_num(x: float | None, digits: int = 3):
    """JSON 크기를 줄이기 위한 반올림. 정수면 정수로 내보낸다."""
    if x is None:
        return None
    r = round(x, digits)
    return int(r) if r == int(r) else r


# ---------------------------------------------------------------- 상태 기록
def update_status(source: str, ok: bool, message: str, **extra) -> None:
    """출처별 마지막 실행 결과. 사이트의 '자료 현황' 화면과 Actions 로그에서 확인한다."""
    status = read_json(STATUS, {}) or {}
    prev = status.get(source, {})
    entry = {"ok": ok, "message": message, "last_run": now_iso(),
             "last_success": now_iso() if ok else prev.get("last_success")}
    entry.update(extra)
    # 결과가 지난번과 같으면 시각도 그대로 둔다 → 바뀐 것이 없는 날에는 저장소에 커밋이 생기지 않는다
    same = {k: v for k, v in prev.items() if k not in ("last_run", "last_success")} == \
           {k: v for k, v in entry.items() if k not in ("last_run", "last_success")}
    if same:
        entry["last_run"], entry["last_success"] = prev.get("last_run"), prev.get("last_success")
    status[source] = entry
    write_json(STATUS, status, pretty=True)
    print(f"[{source}] {'성공' if ok else '문제'}: {message}")


# ---------------------------------------------------------------- 국가 기준표
def norm_name(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower()
    s = s.replace("&", " and ")
    s = re.sub(r"['\u2019`]", "", s)          # People's → peoples
    s = re.sub(r"(?<=[a-z.])\s*\d{1,2}\)\s*$", "", s)   # 'Turkey5)' 같은 각주 번호 제거
    s = re.sub(r"\(.*?\)", " ", s)          # 괄호 안 설명 제거
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"\b\d+\b", " ", s)          # 각주 번호 제거
    return " ".join(s.split())


# UN Comtrade 가 쓰는 코드 가운데 ISO 숫자 코드와 다른 것
COMTRADE_CODE_FIX = {
    757: "CHE", 842: "USA", 251: "FRA", 579: "NOR", 699: "IND", 490: "TWN", 381: "ITA",
    58: "BEL", 711: "ZAF", 736: "SDN", 891: "SRB", 412: "XKX", 729: "SDN", 230: "ETH", 866: "PAN",
}
# 국가가 아닌 묶음·특수 분류 (지도에는 그리지 않고 표에만 표시)
COMTRADE_SPECIAL = {
    0: ("_WLD", "세계 합계"), 899: ("_NES", "지역 미상"), 837: ("_BNK", "선박·항공 연료 보급"),
    838: ("_FZ", "자유무역지대"), 839: ("_SPC", "특수 분류"), 568: ("_EUN", "기타 유럽"),
    577: ("_AFN", "기타 아프리카"), 636: ("_AMN", "기타 아메리카"), 637: ("_NAN", "기타 북중미"),
    473: ("_LAN", "기타 중남미"), 527: ("_OCN", "기타 오세아니아"), 97: ("_EU", "유럽연합"),
    290: ("_NEU", "기타 북유럽"), 492: ("_EUR", "기타 유럽"), 536: ("_NTZ", "중립 지대"),
}
# 국제기구·통화권 (WGC 엑셀에 국가와 나란히 나온다). True = 다른 행의 합계라 총계에서 제외
INSTITUTIONS = {
    "imf": ("_IMF", "국제통화기금(IMF)", False),
    "international monetary fund": ("_IMF", "국제통화기금(IMF)", False),
    "ecb": ("_ECB", "유럽중앙은행(ECB)", False),
    "european central bank": ("_ECB", "유럽중앙은행(ECB)", False),
    "bis": ("_BIS", "국제결제은행(BIS)", False),
    "bank for international settlements": ("_BIS", "국제결제은행(BIS)", False),
    "waemu": ("_WAEMU", "서아프리카 경제통화동맹", False),
    "west african economic monetary union": ("_WAEMU", "서아프리카 경제통화동맹", False),
    "west african economic and monetary union": ("_WAEMU", "서아프리카 경제통화동맹", False),
    "beac": ("_BEAC", "중앙아프리카 국가은행", False),
    "cemac": ("_BEAC", "중앙아프리카 국가은행", False),
    "eccb": ("_ECCB", "동카리브 중앙은행", False),
    "eccu": ("_ECCB", "동카리브 중앙은행", False),
    "banque des etats de lafrique centrale": ("_BEAC", "중앙아프리카 국가은행", False),
    "state oil fund of the republic of azerbaijan": ("_SOFAZ", "아제르바이잔 국부펀드(SOFAZ)", False),
    "sofaz": ("_SOFAZ", "아제르바이잔 국부펀드(SOFAZ)", False),
    "netherlands antilles": ("_ANT", "네덜란드령 안틸레스(옛)", False),
    "total above": ("_TOT", "표에 실린 국가 합계", True),
    "euro area": ("_EA", "유로 지역 합계", True),
    "euro area incl ecb": ("_EA", "유로 지역 합계", True),
    "euro area including ecb": ("_EA", "유로 지역 합계", True),
    "eurozone": ("_EA", "유로 지역 합계", True),
    "world": ("_WLD", "세계 합계", True),
    "total": ("_WLD", "세계 합계", True),
    "all countries": ("_WLD", "세계 합계", True),
    "world total": ("_WLD", "세계 합계", True),
    "advanced economies": ("_ADV", "선진국 합계", True),
    "emerging and developing economies": ("_EMDE", "신흥·개도국 합계", True),
    "emerging market and developing economies": ("_EMDE", "신흥·개도국 합계", True),
}
# IMF·WGC·스위스 자료에서 쓰이는 영어 국가명 변형
NAME_ALIASES = {
    "united states": "USA", "united states of america": "USA", "usa": "USA", "us": "USA",
    "united kingdom": "GBR", "uk": "GBR", "great britain": "GBR",
    "russia": "RUS", "russian federation": "RUS",
    "china": "CHN", "china p r mainland": "CHN", "china mainland": "CHN", "mainland china": "CHN",
    "china p r": "CHN", "peoples republic of china": "CHN", "china peoples republic of": "CHN",
    "hong kong": "HKG", "china p r hong kong": "HKG", "hong kong sar": "HKG", "hong kong china": "HKG",
    "hong kong sar china": "HKG", "china hong kong sar": "HKG",
    "hong kong special administrative region peoples republic of china": "HKG",
    "macao special administrative region peoples republic of china": "MAC",
    "aruba kingdom of the netherlands": "ABW", "curacao and st maarten": "CUW",
    "curacao kingdom of the netherlands": "CUW", "sint maarten kingdom of the netherlands": "SXM",
    "macao": "MAC", "macau": "MAC", "china p r macao": "MAC", "macao sar": "MAC", "china macao sar": "MAC",
    "taiwan": "TWN", "taiwan province of china": "TWN", "chinese taipei": "TWN", "other asia nes": "TWN",
    "korea": "KOR", "south korea": "KOR", "korea republic of": "KOR", "korea rep of": "KOR",
    "republic of korea": "KOR", "korea rep": "KOR", "korea south": "KOR",
    "north korea": "PRK", "korea dem peoples rep of": "PRK", "korea democratic peoples republic of": "PRK",
    "turkey": "TUR", "turkiye": "TUR", "republic of turkiye": "TUR", "turkiye republic of": "TUR",
    "iran": "IRN", "iran islamic republic of": "IRN", "iran islamic rep of": "IRN",
    "egypt": "EGY", "egypt arab rep of": "EGY", "egypt arab republic of": "EGY",
    "venezuela": "VEN", "venezuela republica bolivariana de": "VEN", "venezuela rep bolivariana de": "VEN",
    "venezuela bolivarian republic of": "VEN",
    "laos": "LAO", "lao peoples dem rep": "LAO", "lao pdr": "LAO", "lao peoples democratic republic": "LAO",
    "kyrgyz republic": "KGZ", "kyrgyzstan": "KGZ", "slovak republic": "SVK", "slovakia": "SVK",
    "czech republic": "CZE", "czechia": "CZE", "syria": "SYR", "syrian arab republic": "SYR",
    "yemen": "YEM", "yemen republic of": "YEM", "north macedonia": "MKD", "macedonia fyr": "MKD",
    "macedonia": "MKD", "bolivia": "BOL", "bolivia plurinational state of": "BOL",
    "cote d ivoire": "CIV", "ivory coast": "CIV",
    "congo dem rep of the": "COD", "congo democratic republic of the": "COD", "congo dem rep of": "COD", "congo democratic republic of": "COD", "democratic republic of the congo": "COD",
    "dr congo": "COD", "congo dem rep": "COD", "congo republic of": "COG", "congo rep of": "COG", "congo": "COG",
    "bahamas": "BHS", "bahamas the": "BHS", "gambia": "GMB", "gambia the": "GMB",
    "brunei": "BRN", "brunei darussalam": "BRN", "cabo verde": "CPV", "cape verde": "CPV",
    "eswatini": "SWZ", "swaziland": "SWZ", "moldova": "MDA", "moldova republic of": "MDA",
    "tanzania": "TZA", "tanzania united republic of": "TZA", "vietnam": "VNM", "viet nam": "VNM",
    "united arab emirates": "ARE", "uae": "ARE", "emirates": "ARE",
    "west bank and gaza": "PSE", "palestine": "PSE", "state of palestine": "PSE",
    "myanmar": "MMR", "burma": "MMR", "timor leste": "TLS", "east timor": "TLS",
    "st lucia": "LCA", "st kitts and nevis": "KNA", "st vincent and the grenadines": "VCT",
    "sao tome and principe": "STP", "micronesia": "FSM", "micronesia federated states of": "FSM",
    "kosovo": "XKX", "serbia": "SRB", "montenegro": "MNE", "curacao": "CUW", "curacao and sint maarten": "CUW",
    "sint maarten": "SXM", "aruba": "ABW", "holy see": "VAT", "vatican": "VAT",
    "bosnia and herzegovina": "BIH", "bosnia herzegovina": "BIH", "trinidad and tobago": "TTO",
    "antigua and barbuda": "ATG", "papua new guinea": "PNG", "saudi arabia": "SAU",
    "south africa": "ZAF", "new zealand": "NZL", "sri lanka": "LKA", "el salvador": "SLV",
    "dominican republic": "DOM", "costa rica": "CRI", "burkina faso": "BFA", "sierra leone": "SLE",
    "equatorial guinea": "GNQ", "guinea bissau": "GNB", "central african republic": "CAF",
    "czech": "CZE", "slovak": "SVK", "kyrgyz": "KGZ", "dominican": "DOM", "central african": "CAF",
    "south sudan": "SSD", "solomon islands": "SLB", "marshall islands": "MHL",
}
_STRIP_PHRASES = [
    "federal democratic republic of", "federal dem rep of", "islamic rep of", "dem rep of", "democratic rep of",
    "islamic republic of", "federal republic of", "democratic republic of", "peoples republic of",
    "republic of", "rep of", "republic", "rep", "kingdom of", "state of", "commonwealth of", "sultanate of",
    "principality of", "grand duchy of", "union of", "federation of", "the",
]


class Countries:
    """국가 코드·이름을 ISO3 하나로 통일한다. 못 찾은 이름은 unknown 에 모아 상태 기록에 남긴다."""

    def __init__(self) -> None:
        self.list = read_json(REFERENCE / "countries.json", [])
        self.by_iso3 = {c["iso3"]: c for c in self.list}
        self.by_iso2 = {c["iso2"]: c["iso3"] for c in self.list if c.get("iso2")}
        self.by_m49 = {c["m49"]: c["iso3"] for c in self.list if c.get("m49") is not None}
        self.by_name: dict[str, str] = {}
        for c in self.list:
            for n in [c["en"], *c.get("aliases", [])]:
                self.by_name.setdefault(norm_name(n), c["iso3"])
        self.by_name.update(NAME_ALIASES)
        self.special: dict[str, dict] = {}   # '_WLD' 같은 가상 코드 → {ko, aggregate}
        for code, ko in COMTRADE_SPECIAL.values():
            self.special[code] = {"ko": ko, "aggregate": code == "_WLD"}
        for code, ko, agg in INSTITUTIONS.values():
            self.special[code] = {"ko": ko, "aggregate": agg}
        self.unknown: dict[str, int] = {}

    def from_comtrade(self, code) -> str | None:
        try:
            code = int(code)
        except (TypeError, ValueError):
            return None
        if code in COMTRADE_SPECIAL:
            return COMTRADE_SPECIAL[code][0]
        if code in COMTRADE_CODE_FIX:
            return COMTRADE_CODE_FIX[code]
        iso3 = self.by_m49.get(code)
        if iso3 is None:
            self.unknown[f"comtrade:{code}"] = self.unknown.get(f"comtrade:{code}", 0) + 1
        return iso3

    def m49_for(self, iso3: str) -> int | None:
        for code, v in COMTRADE_CODE_FIX.items():
            if v == iso3 and code in (757, 842, 251, 579, 699, 490):
                return code
        c = self.by_iso3.get(iso3)
        return c.get("m49") if c else None

    def from_name(self, name, record: bool = True) -> str | None:
        """record=False 면 못 찾아도 unknown 목록에 남기지 않는다 (열 탐색용)."""
        if name is None:
            return None
        raw = str(name).strip()
        if not raw:
            return None
        if re.fullmatch(r"[A-Z]{3}", raw) and raw in self.by_iso3:
            return raw
        if re.fullmatch(r"[A-Z]{2}", raw) and raw in self.by_iso2:
            return self.by_iso2[raw]
        n = norm_name(raw)
        if not n:
            return None
        if n in INSTITUTIONS:
            return INSTITUTIONS[n][0]
        if n in self.by_name:
            return self.by_name[n]
        # "Korea, Republic of" → "korea republic of" → 수식어를 떼고 다시 찾는다
        stripped = n
        for p in _STRIP_PHRASES:
            stripped = re.sub(rf"\b{p}\b", " ", stripped)
        stripped = " ".join(stripped.split())
        if stripped and stripped in self.by_name:
            return self.by_name[stripped]
        if record:
            self.unknown[f"name:{raw}"] = self.unknown.get(f"name:{raw}", 0) + 1
        return None

    def label(self, code: str) -> str:
        if code in self.by_iso3:
            return self.by_iso3[code]["ko"]
        if code in self.special:
            return self.special[code]["ko"]
        return code

    def is_country(self, code: str | None) -> bool:
        return bool(code) and code in self.by_iso3
