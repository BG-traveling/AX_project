# 🌀 TyphoonPath — AI 기반 태풍 경로 예측 서비스

> LSTM 딥러닝, GBM 머신러닝, IBTrACS 실제 태풍 데이터를 활용한 인터랙티브 태풍 경로 예측 서비스

---

## 📌 프로젝트 소개

지도에서 태풍 발생 시작점과 기상 조건을 설정하면, AI 모델이 자동으로 경로를 예측합니다.
4단계 폴백 예측 체인(LSTM → GBM → 유사태풍 블렌딩 → 물리모델)을 통해 항상 최선의 예측 결과를 제공합니다.
BMAD 방법론(Analyst → PM → Architect → Scrum Master → Developer)으로 3일간 개발하였습니다.

---

## ⚙️ 기술 스택

| 구분 | 기술 |
|------|------|
| 프론트엔드 | React 18, TypeScript, Vite, Leaflet.js |
| 백엔드 | FastAPI (Python 3.11+) |
| 머신러닝 / 딥러닝 | PyTorch (LSTM), scikit-learn (GBM) |
| AI 기상 해설 | Claude Haiku (Anthropic API) |
| 캐싱 | Redis |
| 데이터 | IBTrACS WP — NOAA (1951~2024, 태풍 4,230개) |
| 배포 | Vercel (프론트엔드) · Railway (백엔드 + Redis) |

---

## 🤖 예측 모델 — 4단계 폴백 체인

```
예측 요청
  ↓
① LSTM Seq2Seq + Bahdanau Attention  (앙상블: hidden=48/64/96)
  ↓ 5포인트 미만 생성 시 폴백
② GradientBoosting 머신러닝  (모델 3개: dlat / dlng / dpres)
  ↓ 폴백
③ 유사 태풍 블렌딩  (유사 태풍 10개 이동 벡터 가중평균)
  ↓ 폴백
④ 물리 모델  (Beta drift + SST 기반 강도 모델)
```

### LSTM 모델 상세

- **인코더**: 과거 4스텝(24h) × 8피처 → 은닉 상태 생성
- **어텐션**: Bahdanau Attention으로 중요한 시점 집중
- **디코더**: 자동 회귀 방식, 최대 40스텝(240h = 10일) 예측
- **입력 피처**: `dlat, dlng, dpres, lat_norm, lng_norm, pres_norm, sin_month, cos_month`
- **훈련**: L1Loss · Adam(lr=0.001) · CosineAnnealingLR · 조기 종료(patience=12)

### GBM 모델 입력 피처 (11개)

`lat, lng, pressure, wind_1min_ms, wind_10min_ms, diameter_km, month, prev_dlat, prev_dlng, lat×sin(월), lat×cos(월)`

---

## 📦 데이터셋

| 항목 | 내용 |
|------|------|
| 출처 | IBTrACS WP v04r01 (NOAA) |
| 태풍 수 | 4,230개 (강화 버전) |
| 기간 | 1951년 ~ 2024년 |
| 총 관측점 | 172,206개+ |
| 추가 필드 | `wind_1min_ms` (1분 풍속), `wind_10min_ms` (10분 풍속), `diameter_km` (최대직경) |

---

## 🗂️ 프로젝트 구조

```
AX_project/
├── frontend/                      # React + TypeScript
│   └── src/
│       ├── App.tsx                # 메인 앱 + 3단계 UX 플로우
│       ├── api/typhoonApi.ts      # API 클라이언트
│       ├── types/typhoon.ts       # 타입 정의
│       └── components/Map/
│           └── TyphoonMap.tsx     # Leaflet 지도 + 강도별 색상 구간
│
├── backend/                       # FastAPI
│   ├── app/
│   │   ├── main.py
│   │   ├── routers/
│   │   │   └── predict.py         # 4단계 폴백 체인
│   │   ├── services/
│   │   │   ├── lstm_prediction_service.py
│   │   │   ├── ml_prediction_service.py
│   │   │   ├── blend_service.py
│   │   │   └── claude_service.py
│   │   └── models/schemas.py
│   ├── data/
│   │   ├── typhoons_v2.json       # 강화 데이터셋 (39MB)
│   │   ├── track_model_lat.pkl
│   │   ├── track_model_lng.pkl
│   │   ├── pres_model.pkl
│   │   └── lstm_model_h*.pt       # LSTM 앙상블 가중치
│   └── scripts/
│       ├── convert_data.py        # IBTrACS CSV → typhoons.json
│       ├── enhance_data.py        # 풍속/직경 필드 추가
│       ├── train_model.py         # GBM 모델 훈련
│       └── train_lstm.py          # LSTM 앙상블 훈련
│
└── docs/                          # BMAD 프로젝트 문서
```

---

## 🚀 실행 방법

### 사전 준비
- Python 3.11+
- Node.js 18+
- Redis

### 1. 백엔드 설정

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

`backend/.env` 파일 생성:

```env
ANTHROPIC_API_KEY=발급받은_키
REDIS_URL=redis://localhost:6379
```

### 2. 모델 훈련 (최초 1회)

```bash
# 1단계: CSV → JSON 변환 (typhoons.json이 없는 경우)
python scripts/convert_data.py

# 2단계: 풍속/직경 필드 추가
python scripts/enhance_data.py

# 3단계: GBM 모델 훈련 (약 2분)
python scripts/train_model.py

# 4단계: LSTM 앙상블 훈련 (약 10~30분)
pip install torch --index-url https://download.pytorch.org/whl/cpu
python scripts/train_lstm.py
```

### 3. 백엔드 실행

```bash
uvicorn app.main:app --reload --port 8000
```

### 4. 프론트엔드 실행

```bash
cd frontend
npm install
npm run dev
```

브라우저에서 `http://localhost:5173` 접속

---

## 🗺️ 사용 방법

1. **지도 클릭** → 태풍 발생 시작점 설정
2. **슬라이더 조작** → 중심기압, 해수면 온도, 1분 풍속, 10분 풍속, 최대직경 설정
3. **"경로 예측하기" 클릭** → AI 예측 실행
4. **결과 확인**
   - 강도별 색상 경로 (STY=빨강 / TY=주황 / TS=노랑 / TD=파랑)
   - 24시간마다 `+1일`, `+2일`... 시간 레이블
   - 포인트 클릭 시 상세 팝업 (경과시간, 강도, 기압, 풍속, 위경도)
   - 사이드바: 예측 방법 배지, 총 지속시간, 강도 타임라인 바
   - Claude Haiku AI 기상 해설

---

## 🔖 예측 방법 배지

| 배지 | 방법 | 조건 |
|------|------|------|
| 🧠 LSTM 딥러닝 | LSTM Seq2Seq + Attention | `.pt` 모델 파일 존재 시 |
| 🤖 GBM 머신러닝 | GradientBoosting | `.pkl` 모델 파일 존재 시 |
| 📊 유사 태풍 블렌딩 | Analog Blending | 유사 태풍 탐색 성공 시 |
| ⚙️ 물리 모델 | 위도·기압·SST 공식 | 항상 사용 가능 (최후 폴백) |

---

## 🐛 주요 버그 수정 이력

| 버그 | 원인 | 해결 |
|------|------|------|
| STY 강도가 끝까지 유지됨 | 기압 모델이 계속 강화 방향으로 작동 | `lifecycle_dpres()` 3단계 생애주기 모델 도입 |
| 훈련 후에도 ML 모델 미사용 | `@lru_cache`가 `None`을 캐시 | 전역 dict 캐시로 교체, 성공 시에만 저장 |
| train_model.py 복소수 오류 | 음수^소수 지수 → complex 반환 | `max(0, 1010 - pres)` 클램핑 |
| 예측 경로 미표시 | schemas.py 파일 일부 잘림 → 클래스 누락 | bash heredoc으로 전체 재작성 |

---

## 📄 라이선스

MIT

---

## 👤 개발자

**김동현** · [onthegroundplay403@gmail.com](mailto:onthegroundplay403@gmail.com)
