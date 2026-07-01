# 🌀 TyphoonPath — AI 기반 태풍 경로 예측 서비스

> LSTM 딥러닝, 유사 태풍 블렌딩, IBTrACS 실제 태풍 데이터를 활용한 인터랙티브 태풍 경로 예측 서비스

🔗 **[라이브 데모](https://bg-traveling.github.io/AX_project/)** &nbsp;|&nbsp; 백엔드: [Railway](https://axproject-production.up.railway.app)

---

## 📌 프로젝트 소개

지도에서 태풍 발생 시작점과 기상 조건을 설정하면, AI 모델이 자동으로 경로를 예측합니다.
4단계 폴백 예측 체인(LSTM → 유사태풍 블렌딩 → GBM → 물리모델)을 통해 항상 최선의 예측 결과를 제공하며,
불확실성 원뿔(Cone of Uncertainty), 타임라인 애니메이션, 모바일 반응형 UI를 포함합니다.

BMAD 방법론(Analyst → PM → Architect → Scrum Master → Developer)으로 진행하였습니다.

---

## ⚙️ 기술 스택

| 구분 | 기술 |
|------|------|
| 프론트엔드 | React 18, TypeScript, Vite, Leaflet.js |
| 백엔드 | FastAPI (Python 3.11+) |
| 머신러닝 / 딥러닝 | PyTorch (LSTM Seq2Seq), scikit-learn (GBM) |
| AI 기상 해설 | Claude Haiku (Anthropic API) |
| 캐싱 | Redis |
| 데이터 | IBTrACS WP — NOAA (1951~2024, 태풍 2,645개) |
| 배포 | GitHub Pages (프론트엔드) · Railway (백엔드) |

---

## 🤖 예측 모델 — 4단계 폴백 체인

```
예측 요청
  ↓
① LSTM Seq2Seq + Bahdanau Attention  (앙상블: hidden=48/64/96)
  ↓ 물리 타당성 기각 또는 타임아웃 시 폴백
② 유사 태풍 블렌딩  (유사 태풍 10개 이동 벡터 가중평균) ← 검증 결과 가장 정확
  ↓ 타당성 기각 시 폴백
③ GradientBoosting 머신러닝  (모델 3개: dlat / dlng / dpres)
  ↓ 폴백
④ 물리 모델  (Beta drift + SST 기반 강도 모델)
```

### 물리적 타당성 검사 (`_is_plausible`)

저위도(lat<25, lng>125) 태풍의 비정상 이동 패턴을 기각합니다.

| 모델 | 동진 한도(Δlng) | 남진 한도(Δlat) |
|------|----------------|----------------|
| LSTM / GBM | ≤ 3.0° | ≥ −2.5° |
| Analog Blending | ≤ 5.0° | ≥ −5.0° |

### LSTM 모델 상세

- **인코더**: 과거 4스텝(24h) × 8피처 → 은닉 상태 생성
- **어텐션**: Bahdanau Attention으로 중요한 시점 집중
- **디코더**: 자동 회귀 방식, 최대 80스텝(480h) 예측
- **입력 피처**: `dlat, dlng, dpres, lat_norm, lng_norm, pres_norm, sin_month, cos_month`
- **훈련**: L1Loss · Adam(lr=0.001) · CosineAnnealingLR · 조기 종료(patience=12)

---

## ✨ 주요 기능

### 불확실성 원뿔 (Cone of Uncertainty)
NHC 스타일의 예측 불확실성 영역을 지도에 시각화합니다.
- 시작 반경 30km → 120h(5일) 기준 300km로 선형 확대
- 반투명 파란색 폴리곤으로 렌더링

### 타임라인 슬라이더
- 예측 경로를 시간 순서대로 단계별로 재생
- 재생(▶) / 정지(⏸) 버튼, 120ms 간격 자동 진행
- 슬라이더 드래그로 특정 시점 즉시 이동

### 모바일 반응형 UI
- 768px 브레이크포인트 기준 레이아웃 전환
- iOS Safari 대응 `100dvh` 적용
- Bottom Sheet 패턴으로 모바일 컨트롤 패널 표시

### 예측 결과 시각화
- 강도별 색상 경로 (STY=빨강 / TY=주황 / TS=노랑 / TD=파랑)
- 24시간마다 `+1일`, `+2일`... 시간 레이블
- 포인트 클릭 시 상세 팝업 (경과시간, 강도, 기압, 풍속, 위경도)
- 사이드바: 예측 방법 배지, 총 지속시간, 강도 타임라인 바
- Claude Haiku AI 기상 해설

---

## 📦 데이터셋

| 항목 | 내용 |
|------|------|
| 출처 | IBTrACS WP v04r01 (NOAA) |
| 태풍 수 | 2,645개 |
| 기간 | 1951년 ~ 2024년 |
| 추가 필드 | `wind_1min_ms` (1분 풍속), `wind_10min_ms` (10분 풍속), `diameter_km` (최대직경) |

---

## 🗂️ 프로젝트 구조

```
AX_project/
├── frontend/                      # React + TypeScript
│   ├── src/
│   │   ├── App.tsx                # 메인 앱 + 타임라인 슬라이더 상태
│   │   ├── api/typhoonApi.ts      # API 클라이언트 (VITE_API_BASE_URL)
│   │   ├── types/typhoon.ts       # 타입 정의
│   │   └── components/
│   │       ├── Map/TyphoonMap.tsx # Leaflet 지도 + 불확실성 원뿔
│   │       ├── Controls/          # VariablePanel, TyphoonSelector
│   │       └── Feedback/          # FeedbackPanel
│   └── vite.config.ts             # base: '/AX_project/' (GitHub Pages)
│
├── backend/                       # FastAPI
│   ├── app/
│   │   ├── main.py                # startup 사전 로드 (typhoons.json + LSTM)
│   │   ├── routers/predict.py     # 4단계 폴백 체인 + LSTM 20초 타임아웃
│   │   ├── services/
│   │   │   ├── lstm_prediction_service.py
│   │   │   ├── ml_prediction_service.py
│   │   │   ├── blend_service.py
│   │   │   └── claude_service.py
│   │   └── models/schemas.py
│   └── data/
│       ├── typhoons.json          # 17MB 메인 데이터셋
│       ├── track_model_*.pkl      # GBM 모델
│       └── lstm_model_h*.pt       # LSTM 앙상블 가중치 (h48/h64/h96)
│
├── .github/workflows/
│   └── deploy-frontend.yml        # GitHub Pages 자동 배포
├── railway.toml                   # Railway 백엔드 배포 설정
└── docs/                          # BMAD 프로젝트 문서
```

---

## 🚀 배포 구성

### 프론트엔드 — GitHub Pages

`main` 브랜치 `frontend/**` 변경 시 GitHub Actions가 자동 배포합니다.

```
Repository Settings → Secrets → VITE_API_BASE_URL
값: https://axproject-production.up.railway.app
```

### 백엔드 — Railway

```toml
# railway.toml
[deploy]
startCommand = "cd backend && uvicorn app.main:app --host 0.0.0.0 --port $PORT"
```

환경변수 설정 (Railway Dashboard → Variables):
```
ANTHROPIC_API_KEY=발급받은_키
REDIS_URL=Railway Redis 연결 URL
```

---

## 💻 로컬 실행 방법

### 사전 준비
- Python 3.11+, Node.js 18+, Redis

### 1. 백엔드

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

`backend/.env` 생성:
```env
ANTHROPIC_API_KEY=발급받은_키
REDIS_URL=redis://localhost:6379
```

```bash
uvicorn app.main:app --reload --port 8000
```

### 2. 모델 훈련 (최초 1회, 선택사항)

```bash
python scripts/train_model.py      # GBM (~2분)
python scripts/train_lstm.py       # LSTM (~10~30분, GPU 권장)
```

### 3. 프론트엔드

```bash
cd frontend
npm install
npm run dev
# http://localhost:5173 접속
```

---

## 🔖 예측 방법 배지

| 배지 | 방법 | 조건 |
|------|------|------|
| 🧠 LSTM 딥러닝 | LSTM Seq2Seq + Attention | `.pt` 모델 파일 존재 + 타당성 통과 |
| 📊 유사 태풍 블렌딩 | Analog Blending | 기본 예측 방식 (가장 신뢰도 높음) |
| 🤖 GBM 머신러닝 | GradientBoosting | `.pkl` 모델 파일 존재 + 타당성 통과 |
| ⚙️ 물리 모델 | 위도·기압·SST 공식 | 항상 사용 가능 (최후 폴백) |

---

## 🐛 주요 버그 수정 이력

| 버그 | 원인 | 해결 |
|------|------|------|
| STY 강도가 끝까지 유지됨 | 기압 모델이 계속 강화 방향 작동 | `lifecycle_dpres()` 3단계 생애주기 모델 도입 |
| 훈련 후에도 ML 모델 미사용 | `@lru_cache`가 `None`을 캐시 | 전역 dict 캐시로 교체, 성공 시에만 저장 |
| train_model.py 복소수 오류 | 음수^소수 지수 → complex 반환 | `max(0, 1010 - pres)` 클램핑 |
| 예측 경로 미표시 | schemas.py 클래스 누락 | bash heredoc으로 전체 재작성 |
| TypeScript 빌드 오류 | `vite-env.d.ts` 누락 | `/// <reference types="vite/client" />` 추가 |
| 배포 후 API URL 오류 | GitHub Secret에 `https://` 미포함 | Secret 값 `https://axproject-...` 으로 수정 |
| 첫 예측 요청 타임아웃 | `typhoons.json` 17MB cold start | startup 이벤트에서 사전 로드 추가 |
| LSTM 추론 무한 대기 | Railway CPU에서 PyTorch 추론 지연 | `asyncio.wait_for` 20초 타임아웃 → Analog Blending 자동 폴백 |

---

## 📄 라이선스

MIT

---

## 👤 개발자

**김동현** · [onthegroundplay403@gmail.com](mailto:onthegroundplay403@gmail.com)
