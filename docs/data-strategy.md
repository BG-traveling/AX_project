# 데이터 전략 문서 — TyphoonPath

**작성일:** 2026-06-29  
**상태:** 탐색 완료 → 전략 확정

---

## 탐색한 데이터 소스

### ① 기상청_태풍정보 조회서비스 (REST API)
- **URL:** `http://apis.data.go.kr/1360000/TyphoonInfoService/getTyphoonInfo`
- **포맷:** JSON / XML
- **API 키:** 공공데이터포털 자동승인 (무료, 개발계정 10,000건)
- **용도:** 현재/최근 발표된 태풍 실황 정보
- **한계:** 통보문 발표 날짜 기반 조회 → 1951~2024 전체 이력을 얻으려면 수천 번 반복 호출 필요

**응답 필드 구조:**
| 필드 | 설명 | 프로젝트 활용 |
|------|------|--------------|
| `typLat` / `typLon` | 위도 / 경도 | Leaflet 마커 위치 |
| `typPs` | 중심기압 (hPa) | 슬라이더 변수, 강도 표시 |
| `typWs` | 최대풍속 (m/s) | 강도 색상 구분 |
| `typDir` | 진행방향 (NE 등) | 화살표 표시 |
| `typSp` | 진행속도 (km/h) | 이동 속도 표시 |
| `typ25` | 폭풍반경 km | 반경 원 표시 |
| `typ15` | 강풍반경 km | 반경 원 표시 |
| `typName` / `typEn` | 태풍 이름 (한글/영문) | 필터 UI |
| `typTm` | 태풍 시각 | 시계열 표시 |

---

### ② 기상청_태풍 베스트트랙 (LINK → apihub.kma.go.kr)
- **보유기간:** 2015년~
- **특징:** 재분석된 정밀 사후 데이터 (가장 정확한 이력)
- **한계:** 2015년 이전 데이터 없음 → 1951~2014 커버 불가

---

### ③ 기상청_태풍경로 (CSV 파일데이터) ✅ 채택
- **링크:** https://www.data.go.kr/data/15043568/fileData.do
- **보유기간:** 1951년 ~ 최신 (매년 업데이트)
- **포맷:** CSV
- **API 키:** 불필요 (파일 직접 다운로드)
- **특징:** 기상청이 보유한 전체 과거 태풍 경로 데이터

---

### ④ IBTrACS (NOAA 국제 태풍 데이터)
- **URL:** https://www.ncei.noaa.gov/products/international-best-track-archive
- **보유기간:** 1841년~현재 (전 세계)
- **포맷:** CSV, NetCDF
- **한계:** 샌드박스 네트워크에서 다운로드 불가 → 로컬에서 수동 다운로드 필요
- **필드:** SID, SEASON, NAME, ISO_TIME, LAT, LON, WMO_PRES, WMO_WIND 등

---

## 결정된 데이터 전략

```
[데이터 수집 방법]
1. 기상청_태풍경로 CSV 다운로드 (data.go.kr → 파일 직접 다운)
   또는
   IBTrACS WP(서태평양) CSV 다운로드 (로컬 환경에서)
   → backend/data/typhoons_raw.csv 저장

2. Python 전처리 스크립트로 JSON 변환
   → backend/data/typhoons.json 생성

3. FastAPI가 JSON 파일에서 데이터 읽어서 서빙
   (DB 없음, 파일 기반 → Redis 캐싱으로 속도 보완)
```

### 데이터 변환 후 최종 스키마 (JSON)
```json
{
  "typhoons": [
    {
      "id": "2023-KHANUN",
      "name_ko": "카눈",
      "name_en": "KHANUN",
      "year": 2023,
      "season_no": 6,
      "track": [
        {
          "datetime": "2023-07-28T00:00:00",
          "lat": 17.5,
          "lng": 151.2,
          "pressure": 998,
          "wind_speed": 18,
          "intensity": "TS",
          "direction": "NW",
          "speed_kmh": 20
        },
        ...
      ]
    }
  ]
}
```

### 강도 분류 (intensity)
| 코드 | 최대풍속 | 설명 |
|------|---------|------|
| TD | < 17 m/s | 열대저압부 |
| TS | 17~24 m/s | 열대폭풍 |
| TY | 25~32 m/s | 태풍 |
| STY | ≥ 33 m/s | 강한 태풍 |

---

## 데이터 수집 Action Items

개발 시작 전 사전 작업 (로컬에서 직접 수행):

1. **기상청 태풍경로 CSV 다운로드**
   - https://www.data.go.kr/data/15043568/fileData.do 접속
   - 파일 다운로드 → `backend/data/typhoons_raw.csv` 로 저장

2. **또는 IBTrACS WP CSV 다운로드 (더 풍부한 데이터)**
   - https://www.ncei.noaa.gov/data/international-best-track-archive-for-climate-stewardship-ibtracs/v04r01/access/csv/ibtracs.WP.list.v04r01.csv
   - 파일 저장 → `backend/data/ibtracs_wp.csv`

3. **전처리 스크립트 실행** (`backend/scripts/convert_data.py`)
   - CSV → `backend/data/typhoons.json` 변환

---

## 전처리 스크립트 (작성 예정)

`backend/scripts/convert_data.py`로 작성 예정:
- CSV 파싱 → 태풍별 그룹화 → 강도 분류 → JSON 직렬화
- 필터: 서태평양(WP) 태풍만, 1951~2024 기간
- 예상 데이터 규모: 약 1,200개 태풍 × 평균 30 관측점 = ~36,000 레코드
