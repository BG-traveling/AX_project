# TyphoonPath — 전체 구현 기술 문서

> 작성일: 2026-06-30  
> 버전: v2.0 (LSTM + Analog Blending + GBM + Physics 4단계 폴백 체인)

---

## 1. 프로젝트 개요

TyphoonPath는 사용자가 태풍 발생 위치와 기상 조건을 직접 설정하면, AI·ML·물리 모델이 협력하여 예측 경로를 지도 위에 애니메이션으로 보여주는 **교육용 태풍 경로 예측 서비스**입니다.

### 기술 스택

| 구분 | 기술 |
|------|------|
| 프론트엔드 | React 18 + TypeScript + Vite + Leaflet.js (react-leaflet) |
| 백엔드 | FastAPI 0.115 + Uvicorn + Pydantic v2 |
| AI | Claude Haiku (`claude-haiku-4-5-20251001`) via Anthropic SDK |
| 데이터 | IBTrACS WP 1951-2024 (typhoons.json, 2,645 태풍 / 172,206 트랙 포인트) |
| ML/DL | Scikit-learn GBM + PyTorch LSTM Seq2Seq |
| 지도 | OpenStreetMap 타일 (Leaflet) |

### 프로젝트 구조

```
AX_project/
├── frontend/
│   └── src/
│       ├── App.tsx                     # 앱 상태 머신 + 사이드바 UI
│       ├── components/Map/TyphoonMap.tsx  # 지도 + 경로 애니메이션
│       ├── api/typhoonApi.ts           # HTTP 클라이언트
│       └── types/typhoon.ts            # TypeScript 타입 정의
├── backend/
│   └── app/
│       ├── main.py                     # FastAPI 앱 진입점
│       ├── models/schemas.py           # Pydantic 스키마
│       ├── routers/predict.py          # 예측 라우터 (폴백 체인)
│       └── services/
│           ├── blend_service.py        # 1순위: Analog Blending
│           ├── lstm_prediction_service.py  # 0순위: LSTM 딥러닝
│           ├── ml_prediction_service.py    # 2순위: GBM ML
│           ├── prediction_service.py       # 3순위: 물리 모델
│           ├── claude_service.py           # AI 해설 생성
│           └── typhoon_service.py          # typhoons.json 로더
├── docs/
│   ├── 화면설계서.html                 # 인터랙티브 HTML 와이어프레임
│   └── typhoonpath_flowchart.drawio    # draw.io 플로우차트 3종
├── SRS.md                              # 소프트웨어 요구사항 명세서
└── _archive/                           # 구파일 보관 폴더
```

---

## 2. 전체 서비스 흐름

```
[사용자] 지도 클릭 (위치 선택)
    ↓
[App.tsx] phase: 'pick' → 'config'
    ↓
[사용자] 기압 슬라이더, SST 슬라이더, 풍속, 직경 조정
    ↓
[사용자] "경로 예측하기" 버튼 클릭
    ↓
[App.tsx] loading=true, POST /api/predict
    ↓
[Backend] 4단계 폴백 체인 실행
    ├─ 0순위: LSTM (모델 파일 존재 + 타당성 검사)
    ├─ 1순위: Analog Blending (유사 태풍 가중 평균)
    ├─ 2순위: GBM ML (pkl 모델 존재 + 타당성 검사)
    └─ 3순위: Physics (항상 가능, 최후 폴백)
    ↓
[Backend] Claude Haiku AI 해설 생성
    ↓
[Frontend] PredictResponse 수신
    ↓
[App.tsx] phase: 'result', 애니메이션 시작
    ↓
[TyphoonMap.tsx] 150ms/스텝 경로 애니메이션 + 🌀 아이콘
    ↓
[사이드바] 예측 결과 요약, 강도 타임라인, 유사 태풍 목록
[하단 AI 패널] Claude 기상 해설 텍스트 표시
```

---

## 3. 프론트엔드 구현

### 3-1. 상태 머신 (App.tsx)

앱 전체는 3단계 Phase로 구동됩니다.

```typescript
type Phase = 'pick' | 'config' | 'result'
```

| Phase | 설명 | 진입 조건 |
|-------|------|-----------|
| `pick` | 지도 클릭으로 시작점 선택 | 초기 상태 / 리셋 |
| `config` | 기상 조건 슬라이더 설정 | 지도 클릭 완료 |
| `result` | 예측 결과 표시 | API 응답 성공 |

**핵심 상태 변수:**

```typescript
const [phase, setPhase]           = useState<Phase>('pick')
const [startPoint, setStartPoint] = useState<{lat,lng} | null>(null)
const [pressure, setPressure]     = useState(960)          // hPa
const [sst, setSst]               = useState(29)           // °C
const [wind1min, setWind1min]     = useState(~)            // m/s (기압에서 자동계산)
const [wind10min, setWind10min]   = useState(~)            // wind1min × 0.88
const [diameter, setDiameter]     = useState(400)          // km
const [loading, setLoading]       = useState(false)
const [predictedTrack, ...]       = useState<PredictedPoint[]>([])
const [analogs, ...]              = useState<AnalogTyphoon[]>([])
const [explanation, ...]          = useState('')           // AI 해설
const [predictionMethod, ...]     = useState('analog_blending')
const [showAnalogs, ...]          = useState(true)
```

**기압 → 풍속 자동 계산 (Atkinson-Holliday 근사):**

```typescript
function pressureToWind1min(p: number): number {
  if (p >= 1010) return 0
  return Math.round(Math.min(85, Math.pow(Math.max(0, 1010 - p), 0.644) * 3.92))
}

// pressure 변경 시 자동 업데이트
useEffect(() => {
  const w1 = pressureToWind1min(pressure)
  setWind1min(w1)
  setWind10min(Math.round(w1 * 0.88))
}, [pressure])
```

**예측 요청 흐름:**

```typescript
async function handlePredict() {
  setLoading(true)
  const month = new Date().getMonth() + 1    // 현재 월 자동 사용
  const result = await postPredict({
    start_lat, start_lng, pressure, sst, month,
    wind_1min_ms, wind_10min_ms, diameter_km
  })
  setPredictedTrack(result.predicted_track)
  setAnalogs(result.analogs)
  setExplanation(result.ai_explanation)
  setPredictionMethod(result.prediction_method)
  setPhase('result')
}
```

**예측 방법 배지 색상:**

| 방법 | 레이블 | 색상 |
|------|--------|------|
| `lstm` | 🧠 LSTM 딥러닝 | `#dc2626` (빨강) |
| `ml` | 🤖 GBM 머신러닝 | `#7c3aed` (보라) |
| `analog_blending` | 📊 유사 태풍 블렌딩 | `#0891b2` (청록) |
| `physics` | ⚙️ 물리 모델 | `#65a30d` (연두) |

**강도별 색상 (INTENSITY_COLOR):**

```typescript
export const INTENSITY_COLOR = {
  TD:  '#94a3b8',   // 열대저압부 — 회색
  TS:  '#34d399',   // 열대폭풍 — 초록
  TY:  '#fb923c',   // 태풍 — 주황
  STY: '#ef4444',   // 강한태풍 — 빨강
}
```

**강도 분류 기준 (사이드바 실시간 표시용):**

```typescript
function pressureToIntensity(p: number) {
  if (p > 997) return 'TD'
  if (p > 979) return 'TS'
  if (p > 945) return 'TY'
  return 'STY'
}
```

### 3-2. 지도 컴포넌트 (TyphoonMap.tsx)

**경로 애니메이션 구현:**

```typescript
const [animIdx, setAnimIdx] = useState(0)
const intervalRef = useRef<...>(null)

useEffect(() => {
  if (predictedTrack.length === 0) { setAnimIdx(0); return }
  
  setAnimIdx(0)
  clearInterval(intervalRef.current)
  
  // 150ms 간격으로 1포인트씩 공개 (= 6시간/포인트)
  intervalRef.current = setInterval(() => {
    setAnimIdx(prev => {
      if (prev >= predictedTrack.length - 1) {
        clearInterval(intervalRef.current)
        return prev
      }
      return prev + 1
    })
  }, 150)
}, [predictedTrack])

const visibleTrack = predictedTrack.slice(0, animIdx + 1)
```

**지도 레이어 구성:**

1. **OpenStreetMap 타일** — 배경 지도
2. **유사 태풍 경로** (showAnalogs=true 시) — 점선 Polyline, 3색 (금색/보라/청록)
3. **예측 경로** — 강도별 색상 구간 분리 Polyline (weight=4)
4. **CircleMarker** — 각 예측 포인트, 24h/48h/72h 등 하루 단위 표시 강조
5. **시간 레이블** (`+1일`, `+2일`...) — Marker with divIcon
6. **🌀 회전 태풍 아이콘** — 애니메이션 중 현재 위치 표시 (CSS spin 애니메이션)
7. **📍 시작점 마커** — 파란 원형 아이콘, 위치 Tooltip

**강도별 구간 분리 로직:**

```typescript
const segments = []
for (let i = 0; i < visibleTrack.length - 1; i++) {
  const p = visibleTrack[i]
  segments.push({
    positions: [[p.lat, p.lng], [visibleTrack[i+1].lat, visibleTrack[i+1].lng]],
    color: INTENSITY_COLOR[p.intensity],
  })
}
// → 각 6시간 구간을 해당 강도의 색으로 그림
```

**팝업 정보:** 각 포인트 클릭 시 강도 / 기압(hPa) / 풍속(m/s) / 위치(°N °E) 표시

---

## 4. 백엔드 API

### 4-1. 엔드포인트 목록

| Method | Path | 설명 |
|--------|------|------|
| POST | `/api/predict` | 태풍 경로 예측 (메인 기능) |
| GET | `/api/typhoons` | 태풍 목록 조회 |
| GET | `/api/typhoons/{id}` | 태풍 상세 + 트랙 조회 |
| POST | `/api/feedback` | 사용자 예측 피드백 (레거시) |

### 4-2. 예측 API 스키마

**Request (`PredictRequest`):**

```python
class PredictRequest(BaseModel):
    start_lat: float       # 시작 위도
    start_lng: float       # 시작 경도
    pressure: float        # 초기 중심기압 (hPa, 850~1010)
    sst: float             # 해수면 온도 (°C, 20~35)
    month: int             # 예측 월 (1~12)
    
    # 선택 파라미터 (없으면 기압에서 자동 추정)
    wind_1min_ms:  Optional[float]   # 1분 지속풍속 (m/s)
    wind_10min_ms: Optional[float]   # 10분 지속풍속 (m/s)
    diameter_km:   Optional[float]   # 태풍 최대직경 (km)
```

**Response (`PredictResponse`):**

```python
class PredictResponse(BaseModel):
    predicted_track: list[PredictedPoint]   # 6시간 간격 예측 경로
    analogs: list[AnalogTyphoon]            # 유사 태풍 3개
    ai_explanation: str                     # Claude AI 기상 해설
    prediction_method: str                  # 사용된 예측 방법

class PredictedPoint(BaseModel):
    lat: float          # 위도
    lng: float          # 경도
    pressure: float     # 중심기압 (hPa)
    wind_ms: float      # 최대풍속 (m/s)
    intensity: str      # TD | TS | TY | STY
    hour: int           # 예측 시간 (0, 6, 12, ... 480)

class AnalogTyphoon(BaseModel):
    id: str
    name_en: str
    year: int
    similarity: float
    track: list[UserTrackPoint]
```

**공통 강도 변환 공식 (Atkinson-Holliday):**

```python
def _pressure_to_wind(pressure: float) -> float:
    return min(85.0, (1010 - pressure) ** 0.644 * 3.92)

def _classify(wind: float) -> str:
    if wind < 17: return "TD"
    if wind < 25: return "TS"
    if wind < 33: return "TY"
    return "STY"
```

---

## 5. 4단계 폴백 체인 (predict.py)

예측 요청이 들어오면 아래 순서로 방법을 시도합니다. 각 단계가 실패하거나 타당성 검사를 통과하지 못하면 다음 순위로 폴백합니다.

```
POST /api/predict
    │
    ├─ [항상 실행] find_analogs_extended()
    │     → blend_analogs (10개, 블렌딩용)
    │     → display_analogs (3개, 화면 표시용)
    │
    ├─ 0순위: LSTM (lstm_available() == True)
    │     → lstm_predict() → _is_plausible() 통과?
    │         YES → method = "lstm"
    │         NO  → predicted = [] → 다음으로
    │
    ├─ 1순위: Analog Blending (predicted == [])
    │     → blend_predict() → _is_plausible() 통과?
    │         YES → method = "analog_blending"
    │         NO  → predicted = [] → 다음으로
    │
    ├─ 2순위: GBM ML (predicted == [] and ml_available())
    │     → ml_predict() → _is_plausible() 통과?
    │         YES → method = "ml"
    │         NO  → predicted = [] → 다음으로
    │
    └─ 3순위: Physics (predicted == [])
          → predict_track() → method = "physics"

    [항상 실행] Claude AI 해설 생성
          → ai_explanation (실패 시 기본 메시지)
    
    return PredictResponse(predicted_track, analogs, ai_explanation, method)
```

### 물리적 타당성 검사 (_is_plausible)

서태평양 저위도 태풍의 비정상적 움직임을 걸러냅니다:

```python
def _is_plausible(predicted, start_lat, start_lng) -> bool:
    if len(predicted) < 8: return True       # 포인트 부족 시 통과
    if start_lat >= 25 or start_lng <= 125: return True  # 고위도/서쪽 시작 허용
    
    p0 = predicted[0]
    p8 = predicted[min(8, len(predicted) - 1)]   # 48h 후 위치
    
    net_dlng = p8.lng - p0.lng   # 48h 경도 변화
    net_dlat = p8.lat - p0.lat   # 48h 위도 변화
    
    if net_dlng > 3.0: return False    # 동쪽으로 3° 이상 이동 → 비정상
    if net_dlat < -2.5: return False   # 남쪽으로 2.5° 이상 이동 → 비정상
    return True
```

**적용 범위:** `lat < 25°N AND lng > 125°E` 인 서태평양 저위도 태풍에만 적용

---

## 6. 0순위: LSTM Seq2Seq + Bahdanau Attention

### 모델 구조

```
입력: 과거 4스텝 × 8개 피처
     [dlat, dlng, dpres, lat_norm, lng_norm, pres_norm, sin(월), cos(월)]
     
Encoder: LSTM(8→hidden, 2층, dropout=0.2)
Attention: BahdanauAttention(hidden → context vector)
Decoder: LSTM(3+hidden→hidden) + out_track(hidden×2→3)

출력: [dlat, dlng, dpres] per step (최대 80스텝 = 480h)

앙상블: h48 + h64 + h96 모델 평균 → 예측 노이즈 감소
```

### 정규화 범위

```python
LAT_MIN, LAT_MAX   =  0.0,  60.0
LNG_MIN, LNG_MAX   = 70.0, 210.0
PRES_MIN, PRES_MAX = 850.0, 1010.0
```

### Warm-up 합성 (시작점 1개에서 이력 생성)

LSTM은 과거 4스텝 이력이 필요하므로, 시작점 위도에 따라 전형적인 과거 이동 방향을 역산합니다:

```python
def _synthetic_warmup(start_lat, start_lng, pressure, month):
    if start_lat < 22:
        step_dlat, step_dlng = -0.6,  1.0   # 저위도: 남서에서 왔다고 가정
    elif start_lat < 28:
        step_dlat, step_dlng = -0.8,  0.4
    else:
        step_dlat, step_dlng = -1.2, -0.5
    
    # 과거 기압: 현재보다 높았다고 가정 (강화 중으로 역산)
    track_pres = [min(1010, pressure + 1.5 * (PAST_STEPS - i)) for i in range(PAST_STEPS)]
```

### 기압 변화 제약

LSTM 예측값이 비현실적이 될 수 있어 위도 기반 보정 적용:

```python
if step < 4:                       # 초기 24h: 강화 허용
    dpres = max(-2.0, min(1.5, dpres_raw))
elif lat > 35:                     # 고위도: 반드시 약화
    dpres = max(1.5, dpres_raw, (lat - 30) * 0.2)
elif lat > 25:                     # 중위도: 완만한 약화
    dpres = max(0.5, dpres_raw)
else:                              # 저위도: SST 기반
    dpres = min(0.8, dpres_raw) if sst >= 28 else max(0.8, dpres_raw)
```

### 소멸 조건

`pres >= 1008 hPa` OR 범위 이탈 (`lat > 65` or `lat < -5` or `lng > 215` or `lng < 55`)

---

## 7. 1순위: Analog Blending (blend_service.py)

### 유사 태풍 탐색 (find_analogs_extended)

IBTrACS의 2,645개 태풍에서 초기 조건이 유사한 태풍을 검색합니다.

**필터 조건:**
- 트랙 포인트 8개 이상
- 시작 위치 거리 ≤ 1,500 km
- 기압 차이 ≤ 80 hPa
- 월 차이 ≤ 3개월

**유사도 점수:**

```python
pos_score    = max(0.0, 1.0 - dist_km / 1500)       # 위치 유사도
pres_score   = max(0.0, 1.0 - pres_diff / 80)        # 기압 유사도
season_score = max(0.0, 1.0 - month_diff(m1, m2) / 3) # 계절 유사도
len_bonus    = min(0.1, len(track) / 400)             # 긴 경로 보너스

score = pos_score × 0.45 + pres_score × 0.3 + season_score × 0.2 + len_bonus
```

상위 10개를 블렌딩에, 상위 3개를 화면 표시에 사용합니다.

### 경로 블렌딩 (blend_predict)

각 유사 태풍의 **상대 이동 벡터**를 유사도 가중 평균합니다:

```python
# step별 가중 평균 변위
b_lat = sum((atr[step].lat - atr[0].lat) * w for analog, w in zip(analogs, norm_w))
b_lng = sum((atr[step].lng - atr[0].lng) * w for analog, w in zip(analogs, norm_w))

pred_lat = start_lat + b_lat / used_w
pred_lng = start_lng + b_lng / used_w
```

유사 태풍이 해당 스텝에 트랙이 없으면 최대 12스텝(72h) 외삽:

```python
elif step < n + 12:
    extra = step - n + 1
    decay = 0.8 ** extra         # 감쇠 외삽
    cumul_lat = (atr[-1].lat - atr[0].lat) + dl * extra
```

### 생애주기 기압 모델 (_lifecycle_dpres)

단순한 선형 모델이 아니라 태풍 생애주기(강화→성숙→약화)를 반영:

| 단계 | 조건 | 기압 변화 |
|------|------|-----------|
| 초기 (0~24h, step < 4) | SST≥29°C, lat<22°N, pres>940 | -1.0 hPa (강화) |
| 초기 (기타) | | +0.3 hPa (유지) |
| 성숙기 (24~72h, step < 12) | lat > 28°N | +1.5 (약화 시작) |
| 성숙기 | SST ≥ 28°C | +0.5 (유지) |
| 약화기 (72h~, step ≥ 12) | lat > 40°N | +4.0 (급격 약화) |
| 약화기 | lat > 35°N | +2.5 |
| 약화기 | lat > 28°N | +1.8 |
| 약화기 | lat ≤ 28°N | +1.0 |

**보정:** `SST < 25°C → ×1.5 가속`, `SST ≥ 28°C + lat < 25°N → ×0.5 둔화`, `pres > 990 → ×1.5 가속`

### 소멸 조건

`pres >= 1008 hPa` OR 범위 이탈 (`lat > 65` or `lat < -5` or `lng > 215` or `lng < 55`)

---

## 8. 2순위: GBM ML (ml_prediction_service.py)

### 모델 구성

Scikit-learn `GradientBoostingRegressor` 3개:

| 모델 | 파일 | 예측 대상 |
|------|------|-----------|
| lat 모델 | `track_model_lat.pkl` | 6시간 위도 변화 (dlat) |
| lng 모델 | `track_model_lng.pkl` | 6시간 경도 변화 (dlng) |
| pres 모델 | `pres_model.pkl` | 6시간 기압 변화 (dpres) |

### 11개 입력 피처

```python
def _make_feature(lat, lng, pres, w1, w10, diam, month, prev_dlat, prev_dlng):
    lsm = math.sin(2 * math.pi * month / 12)
    lcm = math.cos(2 * math.pi * month / 12)
    return [
        lat, lng, pres,           # 현재 위치/기압
        w1, w10, diam,            # 풍속(1분/10분), 직경
        month,                    # 월
        prev_dlat, prev_dlng,     # 이전 스텝 이동 방향 (관성)
        lsm * lat, lcm * lat,     # 계절 × 위도 교호작용
    ]
```

### 초기 관성 벡터 (warm start)

```python
if lat < 22:
    prev_dlat, prev_dlng = 0.6, -1.0    # 저위도: 북서진
elif lat < 28:
    prev_dlat, prev_dlng = 0.9, -0.4    # 중위도: 북북서
else:
    prev_dlat, prev_dlng = 1.3, 0.6     # 고위도: 북동진
```

### 기압 변화 제약 (LSTM과 동일 로직)

```python
if step < 4:
    dpres_capped = max(-3.0, min(2.0, dpres))
elif lat > 35:
    lat_decay = (lat - 30) * 0.25
    dpres_capped = max(1.5, dpres, lat_decay)
elif lat > 25:
    dpres_capped = max(0.5, dpres)
else:
    if sst >= 28:
        dpres_capped = min(dpres, 0.5)   # 강화 억제
    else:
        dpres_capped = max(0.8, dpres)   # 약화 촉진
```

---

## 9. 3순위: 물리 모델 (prediction_service.py)

가장 단순하지만 항상 작동하는 최후 폴백. NWP를 단순화한 교육용 모델입니다.

### 위도별 조향 벡터 (_steering_vector)

```python
intensity = max(0.0, (1010 - pressure) / 160.0)    # 0~1 강도 지수
sst_boost = max(0.0, (sst - 26) / 9.0)             # SST 26°C 이상 부스트

# 위도 구간별 이동 벡터 (6시간)
if lat < 15:        # 저위도: 서북서 (무역풍 강, 베타 약)
    dlat = 0.5 + intensity×0.3 + sst_boost×0.2
    dlng = -1.8 - intensity×0.3

elif lat < 22:      # 북서 (전형적인 태풍 경로)
    dlat = 0.9 + intensity×0.4 + sst_boost×0.2
    dlng = -1.4 - intensity×0.2

elif lat < 28:      # 전향 시작 (북북동으로 점차 회전)
    t = (lat - 22) / 6.0       # 0→1 전향 진행도
    dlat = 1.3 + t×1.2 + intensity×0.3
    dlng = -1.2 + t×3.0        # 서→동 점진적 전환

else:               # 고위도: 북동~동북동 (편서풍 편입, 가속)
    dlat = 2.0 + intensity×0.5
    dlng = 1.5 + (lat - 28)×0.25
```

### SST 기반 기압 변화 (_decay_pressure)

```python
if sst >= 28 and lat < 25:
    delta = -(sst - 26) × 0.8          # 발달 (기압 하강)
elif sst < 26 or lat > 35:
    delta = (26 - sst) × 1.2 + max(0, lat - 30) × 0.5  # 약화
else:
    delta = 0.5                         # 유지
```

### 소멸 조건

`pres >= 1005 hPa` OR 범위 이탈 (`lat > 55` or `lat < 0` or `lng > 180` or `lng < 80`)

---

## 10. Claude AI 해설 생성 (claude_service.py)

### 예측 해설 (generate_prediction_explanation)

예측 완료 후 자동으로 호출됩니다. 실패해도 경로 결과는 정상 반환됩니다.

**프롬프트 구성:**

```
- 시작 위치 (lat/lng)
- 중심기압 (hPa)
- 해수면 온도 (°C)
- 예측 월
- 예측 경로 포인트 수 / 총 시간
- 최종 위치 및 강도 (기압, 풍속)
- 유사 과거 태풍 이름(연도) 목록
```

**요청 내용 (200자 이내):**
1. 이 경로가 예측된 주요 기상 원인 (기압, SST, 위도 조향력)
2. 유사 과거 태풍과의 공통점 1가지
3. 변수를 바꾸면 경로가 어떻게 달라질지 힌트

**모델:** `claude-haiku-4-5-20251001` / `max_tokens=500`

### 피드백 해설 (generate_feedback) — 레거시

사용자가 직접 예측한 경로와 실제 경로를 비교하는 교육 피드백 기능 (현재 메인 UI에서는 미사용).

**오차 계산:**
```python
def _calc_error(user_track, actual_track):
    # Haversine 거리 평균
    avg_dist = mean([haversine(u, a) for u, a in zip(user_sample, actual_sample)])
    # 최종점 편향 (북/남/동/서)
    bias = ...
    return avg_dist, bias
```

---

## 11. 데이터 (typhoons.json)

### 소스

IBTrACS WP (Western Pacific) 1951-2024, v04r01

### 통계

| 항목 | 수치 |
|------|------|
| 총 태풍 수 | 2,645개 |
| 총 트랙 포인트 | 172,206개 |
| 기간 | 1951~2024 |
| 지역 | 서태평양 (WP) |

### 데이터 필드

```json
{
  "id": "WP011987",
  "name_en": "ABBY",
  "year": 1987,
  "season_no": 1,
  "track": [
    {
      "dt": "1987-05-26T00:00:00",
      "lat": 9.4,
      "lng": 149.8,
      "wind_ms": 15.0,
      "pressure": 998,
      "intensity": "TD"
    }
  ]
}
```

### 전처리 과정 (아카이브)

1. `convert_data.py` — IBTrACS CSV → typhoons.json 변환 (1회 실행 완료)
2. `enhance_data.py` — wind_10min, diameter 필드 추가 (1회 실행 완료)

---

## 12. 파일 분류 현황

### 현재 사용 중인 파일

```
frontend/src/
├── App.tsx                         ✅ 메인 앱
├── components/Map/TyphoonMap.tsx   ✅ 지도
├── api/typhoonApi.ts               ✅ API 클라이언트
└── types/typhoon.ts                ✅ 타입 정의

backend/app/
├── main.py                         ✅ FastAPI 진입점
├── models/schemas.py               ✅ Pydantic 스키마
├── routers/predict.py              ✅ 예측 라우터
├── routers/typhoons.py             ✅ 태풍 목록 라우터
├── routers/feedback.py             ✅ 피드백 라우터
└── services/
    ├── blend_service.py            ✅ 1순위: Analog Blending
    ├── lstm_prediction_service.py  ✅ 0순위: LSTM
    ├── ml_prediction_service.py    ✅ 2순위: GBM ML
    ├── prediction_service.py       ✅ 3순위: 물리 모델
    ├── claude_service.py           ✅ AI 해설
    └── typhoon_service.py          ✅ 데이터 로더

backend/data/
├── typhoons.json                   ✅ 메인 데이터 (IBTrACS WP)
├── lstm_model_h48.pt               ✅ LSTM 앙상블 h48
├── lstm_model_h64.pt               ⚠️ 훈련 필요 여부 확인
├── lstm_model_h96.pt               ⚠️ 훈련 필요 여부 확인
├── lstm_meta.json                  ✅ LSTM 성능 메타데이터
├── track_model_lat.pkl             ✅ GBM lat 모델
├── track_model_lng.pkl             ✅ GBM lng 모델
├── pres_model.pkl                  ✅ GBM pres 모델
└── model_meta.json                 ✅ GBM 성능 메타데이터
```

### _archive 보관 파일

```
_archive/
├── root/             # requirements.txt, test.py, 초기 SVG 다이어그램
├── AX_Games/         # 별개 게임 프로젝트
├── frontend/         # v1 컴포넌트 (TyphoonSelector, VariablePanel, FeedbackPanel, useTyphoonData)
├── backend/services/ # analog_service.py (blend_service로 대체됨)
├── backend/scripts/  # convert_data.py, enhance_data.py (실행 완료)
├── backend/data/     # typhoons_sample.json, typhoons_v2.json, IBTrACS 원본 CSV
└── docs/             # diagram.html (초기 HTML 플로우차트)
```

---

## 13. 미완료 사항 (TODO)

| 항목 | 상태 | 설명 |
|------|------|------|
| LSTM h64/h96 훈련 | ⚠️ 미확인 | `scripts/train_lstm.py` 재실행 필요 |
| GitHub 푸시 | ❌ 미완료 | 최근 변경사항 (애니메이션, max_steps=80, 폴백 재정렬) 미반영 |
| Railway 배포 | ❌ 미완료 | 백엔드 클라우드 배포 필요 |
| Vercel 배포 | ❌ 미완료 | 프론트엔드 클라우드 배포 필요 |
| 수동 삭제 | ⚠️ 권장 | `AX_Games/` 루트폴더, 빈 폴더 3개 직접 삭제 |

---

## 14. 핵심 수식 정리

| 수식 | 코드 |
|------|------|
| 기압 → 풍속 | `min(85.0, (1010-P)^0.644 × 3.92)` |
| 1분→10분 풍속 | `wind_10min = wind_1min × 0.88` |
| 유사도 점수 | `score = pos×0.45 + pres×0.3 + season×0.2 + len_bonus` |
| 위치 유사도 | `1.0 - dist_km / 1500` |
| 기압 유사도 | `1.0 - pres_diff / 80` |
| 계절 유사도 | `1.0 - month_diff / 3` |
| 전향 진행도 | `t = (lat - 22) / 6.0` (22~28°N 구간) |
| SST 부스트 | `max(0, (sst - 26) / 9.0)` |
| 강도 지수 | `max(0, (1010 - pressure) / 160.0)` |

