# 세계 금 지도 (goldinfograph)

국가별 금 보유량과 월간 증감, 나라 사이의 금 수출입 흐름을 세계 지도와 그래프로 보여 주는 사이트입니다.
GitHub 저장소에 자료와 화면이 함께 들어 있고, Cloudflare Pages 가 `site/` 폴더를 그대로 내보냅니다.

| 화면 | 내용 | 출처 | 갱신 |
|---|---|---|---|
| 보유량 | 국가별 금 보유량, 월간 증감, 연초 대비 증감 | World Gold Council 엑셀 | 엑셀을 `raw/wgc/` 에 올리면 자동 |
| 교역 흐름 · 국가별 | 나라 사이 금(HS 7108) 수출입 금액·중량 | UN Comtrade | 매일 자동 |
| 스위스 | 스위스의 상대국·품목·통계키별 월간 금 교역 | 스위스 관세청 BAZG 공개 자료 (SwissImpex 원자료) | 주 1회 자동 |
| 위쪽 실시간 시세 | 국제 금 시세(달러)·원화 금 시세 그래프 | TradingView 무료 위젯 | 실시간 (사이트 갱신과 무관) |
| 자료 현황 (관리자용) | 출처별 갱신 상태, 보유 기간, 오류 원인 | – | – |

**자료 현황 탭은 숨겨져 있습니다.** 사이트 주소 끝에 `#admin` 을 붙여 열면 그 브라우저에서 탭이 보이고, `#admin-off` 로 다시 숨깁니다.
실시간 그래프의 종목은 `config/sources.json` 의 `live_chart` 에서 바꿉니다.

## 처음 한 번만 하는 설정

### 1. Cloudflare Pages 연결

Cloudflare 대시보드 → **Workers & Pages** → **Create** → **Pages** → **Connect to Git** 에서 이 저장소를 고르고 아래처럼 둡니다.

| 항목 | 값 |
|---|---|
| Framework preset | None |
| Build command | (비워 둠) |
| Build output directory | `site` |

빌드 과정이 없어서 저장소에 새 커밋이 생길 때마다 수십 초 안에 사이트가 바뀝니다.

### 2. UN Comtrade 무료 키 등록 (권장)

키가 없어도 주요 30개국의 최근 2년 치는 받습니다. 키를 등록하면 전 세계·2000년부터 전체를 받습니다.

1. <https://comtrade.un.org> 오른쪽 위 **Login** → **Sign-up now** 로 가입합니다 (이메일 인증 코드 입력 후 **Create**).
2. 로그인한 상태에서 <https://comtrade.un.org/en/api-portal> (오른쪽 위 **My Comtrade** → **My API Portal**)을 엽니다.
3. **Generate API Key** 를 누르고, 나온 키를 복사합니다.
4. <https://github.com/changhok/goldinfograph/settings/secrets/actions/new> 를 엽니다
   (저장소 → **Settings** → **Secrets and variables** → **Actions** → **New repository secret** 과 같은 화면).
   - Name: `COMTRADE_API_KEY`
   - Secret: 복사한 키
   - **Add secret** 을 누릅니다.
5. 저장소 → **Actions** → 왼쪽 **자료 갱신** → 오른쪽 **Run workflow** 로 바로 실행하거나, 다음 날 새벽 자동 실행을 기다립니다.

무료 키는 하루 500회 호출 제한이 있습니다. 한 번 실행에 최대 400회를 쓰므로 2000년부터의 과거 자료(약 320개월)는 한두 번의 실행으로 채워집니다.

### 3. WGC 엑셀 올리기

[`raw/wgc/README.md`](raw/wgc/README.md) 를 따라 엑셀을 올립니다. 매달 한 번, 새 판이 나오면 다시 올립니다.

### 4. 첫 실행

저장소 → **Actions** → **자료 갱신** → **Run workflow**. 스위스 파일이 커서(수 GB) 첫 실행은 10~30분쯤 걸립니다.
끝나면 사이트의 **자료 현황** 화면에서 결과를 확인합니다.

## 평소 운영

- **매달 할 일은 하나**입니다: WGC 엑셀을 `raw/wgc/` 에 올리기.
- UN Comtrade·스위스·월평균 금 가격은 매달 5일과 20일 새벽 자동 작업이 받습니다. 바뀐 것이 없으면 커밋도 생기지 않습니다.
- 문제가 생기면 사이트 **자료 현황** 화면에 원인이 적힙니다. 더 자세한 기록은 Actions 실행 로그에 있습니다.
- GitHub 는 저장소에 60일 동안 활동이 없으면 예약 실행을 멈춥니다. Actions 화면에 안내가 뜨면 **Enable workflow** 를 누르면 됩니다.

## 자주 고치는 곳

모든 수집 범위와 주소는 [`config/sources.json`](config/sources.json) 한 파일에 있습니다. 코드를 고칠 필요가 없습니다.

| 하고 싶은 일 | 고칠 곳 |
|---|---|
| 수집 시작 연도 바꾸기 | `start_year` |
| 키 없이 받을 나라·기간 바꾸기 | `comtrade.preview_mode.reporters_iso3`, `recent_months` |
| 금 외 품목(예: 은 7106) 추가 | `comtrade.commodity_codes`, `swiss.tariff_prefixes` |
| 스위스 파일 주소가 바뀌었을 때 | `swiss.files[].urls` 맨 앞에 새 주소 추가 |
| 스위스 파일의 열 이름을 잘못 읽을 때 | `swiss.column_overrides` 에 열 이름 직접 지정 |
| 지도에 그리는 흐름 개수 | `site.flows_per_month` |

국가 이름이 연결되지 않으면(자료 현황 → "국가로 연결하지 못한 코드·이름") `pipeline/common.py` 의 `NAME_ALIASES` 에 한 줄 추가합니다.

## 폴더 구조

```
config/sources.json      수집 범위·출처 주소 설정
raw/wgc/                 WGC 엑셀을 올리는 곳 (사람이 올림)
pipeline/                수집·변환 스크립트 (Python)
  fetch_comtrade.py        UN Comtrade → data-store/comtrade/
  fetch_swiss.py           스위스 관세청 → data-store/swiss/
  import_wgc.py            raw/wgc/*.xlsx → data-store/wgc/
  build_site_data.py       data-store/ → site/data/*.json
  run_all.py               위 전부를 순서대로 실행
  common.py                공통 도구, 국가 이름·코드 연결
data-store/              정리된 원자료 (자동 작업이 채움, 직접 고치지 않음)
site/                    Cloudflare Pages 가 내보내는 폴더
  index.html, assets/      화면 (빌드 없이 그대로 동작하는 HTML·CSS·JS)
  vendor/                  차트(ECharts)·세계 지도 파일
  data/                    화면이 읽는 JSON (자동 작업이 채움)
tests/                   가짜 자료로 전 과정을 점검하는 테스트
tools/                   국가 기준표·지도 파일을 다시 만드는 도구 (평소엔 쓸 일 없음)
.github/workflows/       자동 작업 정의
```

화면을 고치려면 `site/assets/views/` 아래에서 화면별 파일 하나만 보면 됩니다(`reserves.js`, `flows.js`, `country.js`, `swiss.js`, `status.js`).
색은 `site/assets/style.css` 맨 위의 변수만 바꾸면 차트까지 함께 바뀝니다.

## 내 컴퓨터에서 돌려 보기

```bash
pip install -r pipeline/requirements.txt
python tests/run_tests.py                 # 가짜 자료로 전 과정 점검 (실제 자료는 건드리지 않음)
python -m http.server 8000 --directory tests/_out/site   # 가짜 자료가 들어간 화면 미리 보기

python pipeline/run_all.py --only wgc     # 실제 WGC 엑셀만 다시 읽기
python -m http.server 8000 --directory site              # 실제 화면
```

## 알아 둘 점

- **신고 불일치**: 같은 거래라도 수출국과 수입국의 신고가 다를 수 있습니다. 지도에서 ‘수입국 신고 / 수출국 신고’를 바꿔 볼 수 있습니다.
- **신고 지연**: UN Comtrade 는 나라마다 몇 달씩 늦게 들어옵니다. 최근 24개월은 약 25일마다 다시 받아 뒤늦은 신고와 수정을 반영합니다.
- **신고하지 않는 나라**: 자체 신고가 없는 나라는 상대국들의 신고를 모아 보여 줍니다(국가별 화면에 안내 문구 표시).
- **스위스**: 국가별 금 통계는 2012년부터 공개됩니다. 수입 금의 성격을 나누는 통계키(911~914)는 2021년부터입니다.
- **보유량의 빈 달**: 분기 자료 사이의 달은 직전 보유량에 WGC 월간 증감을 더해 채웁니다.
- **자료 이용 조건**: 각 기관의 이용 약관을 따릅니다. 사이트 아래쪽에 출처를 표기하고 있으며, WGC 자료를 공개 사이트에 싣기 전에 gold.org 의 이용 약관을 확인하세요. 스위스 관세청 자료는 출처 표기가 필요하고 상업적 이용은 허가가 필요합니다.
