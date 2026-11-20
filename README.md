# K-Brief 무료 도구

| 폴더 | 도구 | 데이터 갱신 |
|---|---|---|
| `commute/` | 두 직장 통근 지도 | `commute/prices.js`: GitHub Actions "실거래가 갱신"(매주 월요일) |
| `startup/` | 창업 타당성 분석기 | `startup/data.js`(분기), `startup/bench.js`(월간): Claude 예약 작업이 이 저장소에 커밋 |
| `index.html` | 두 도구로 가는 첫 화면 | — |

아래는 통근 지도 설명입니다.

# 두 직장 통근 지도 (1차 버전)

집 후보 한 곳에서 여러 도착지(직장)까지의 대중교통 소요시간을 한 번에 조회하는 정적 웹페이지입니다.
지도와 주소 검색은 네이버 지도, 소요시간은 ODsay를 씁니다.

**이 코드는 키가 없어 실제로 실행해 보지 못했습니다.** 키를 넣은 뒤 아래 "첫 실행 점검"을 꼭 해 주세요.

## 파일

- `index.html` 화면과 동작 전체
- `config.js` 키 설정 (여기만 고치면 됩니다)

## 설정 순서

1. **네이버 지도 키**
   - 네이버 클라우드 플랫폼 콘솔 > Maps > Application 등록
   - API 선택: Web Dynamic Map, Geocoding
   - Web 서비스 URL: 이 페이지를 올릴 주소 (예: `https://commute.k-brief.com`). 로컬 확인용으로 `http://localhost:8000`도 추가
   - 발급된 Client ID를 `config.js`의 `NAVER_KEY_ID`에 입력
   - 무료 이용량은 대표 계정에만 적용됩니다. 콘솔에서 이용 한도를 설정해 두세요.
2. **ODsay 키**
   - lab.odsay.com 가입 > 애플리케이션 등록
   - 웹(URI 등록형) 키가 있으면: 같은 주소를 등록하고 `ODSAY_KEY`에 입력
   - 서버(IP 등록형) 키만 있으면: 고정 IP 서버에 전달용 주소를 만들고 `ODSAY_PROXY`에 그 주소 입력
3. **올리기**: 두 파일을 정적 호스팅(GitHub Pages 등)에 올립니다.

## 첫 실행 점검

- 지도가 뜨는가 (안 뜨면 Client ID 또는 등록 URL 문제)
- 주소 입력 후 "찾기"로 표시가 찍히는가
- "소요시간 계산"에서 시간이 나오는가 (오류 문구가 나오면 그대로 알려 주세요)
- 네이버 지도 스크립트 주소의 키 파라미터 이름(`ncpKeyId`)이 현재 콘솔 안내와 같은지 확인

## 알려진 한계

- 주소 검색은 도로명·지번 주소만 됩니다. "강남역", 회사 이름 같은 장소명은 찾지 못하므로 "지도에서 직접 찍기"를 쓰거나, 다음 버전에서 장소 검색을 붙여야 합니다.
- 조회 1회에 도착지 수만큼 ODsay를 호출합니다 (도착지 2곳이면 2건).
- 키가 브라우저에 노출됩니다. 등록한 주소에서만 쓰이도록 반드시 URL을 제한하세요.

## 동네 찾기 (추정)
- `commute/network.js`는 `tools/build_network.py`가 `commute/stations.js`에서 만든 노선별 역 연결입니다. 역 순서 원자료가 없어 가까운 역끼리 잇는 방식으로 추정하고, 분기·순환 구간은 스크립트 안에서 직접 바로잡았습니다.
- 소요시간은 역 사이 직선거리와 노선별 속도로 계산한 추정치입니다. 버스·급행은 반영하지 않습니다. 실제 시간은 역을 고른 뒤 '소요시간 계산'(ODsay)으로 확인합니다.
- 역 자료를 새로 받으면 `python3 tools/build_network.py --write`로 다시 만듭니다.

## 예산 맞춤 (아파트 실거래가)
- `commute/prices.js`는 GitHub Actions "실거래가 갱신"(`.github/workflows/prices.yml`)이 `tools/fetch_prices.py`로 만듭니다. 매주 월요일 새벽에 돌고, Actions 화면에서 직접 실행할 수도 있습니다.
- 저장소 Settings → Secrets and variables → Actions 에 `MOLIT_KEY`(공공데이터포털 인증키), `NAVER_ID`, `NAVER_SECRET`(네이버 클라우드 Maps 인증 정보)를 넣어야 합니다. 이 값들은 저장소 파일에 쓰지 않습니다.
- 개별 거래는 저장하지 않고 법정동별 중위가격만 공개합니다.
