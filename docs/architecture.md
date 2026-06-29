# Architecture Document — TyphoonPath

## 상태: 작성 완료
**작성자:** Architect (BMAD)  
**날짜:** 2026-06-29  
**BMAD 단계:** Phase 3 - Architect  
**참조:** docs/prd.md

---

## 1. 시스템 아키텍처 개요

```
┌─────────────────────────────────────────────────────────┐
│                      CLIENT (Browser)                    │
│   React 18 + TypeScript + Vite + Leaflet.js             │
└────────────────────────┬────────────────────────────────┘
                         │ HTTP/REST
                         ▼
┌─────────────────────────────────────────────────────────┐
│                  BACKEND (FastAPI)                        │
│                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  Typhoon API │  │  Predict API │  │  Feedback API│  │
│  │  /typhoons   │  │  /predict    │  │  /feedback   │  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  │
│         │                 │                  │           │
│  ┌──────▼───────┐         │         ┌────────▼───────┐  │
│  │    Redis     │         │         │   Claude API   │  │
│  │  (캐싱 TTL   │         │         │  (Anthropic)   │  │
│  │   1시간)     │         │         └────────────────┘  │
│  └──────┬───────┘         │                             │
│         │                 │                             │
│  ┌──────▼─────────────────▼──────────────────────────┐  │
│  │           기상청 / 공공데이터포털 API                │  │
│  │         (1951~2024 태풍 통합 데이터)                │  │
│  └────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘

배포
├── Frontend → Vercel
└── Backend  → Railway
```

---

## 2. 프로젝트 디렉토리 구조

```
typhoon-path/
├── frontend/                    # React + Vite
│   ├── src/
│   │   ├── components/
│   │   │   ├── Map/
│   │   │   │   ├── TyphoonMap.tsx       # Leaflet 지도 컴포넌트
│   │   │   │   ├── TyphoonTrack.tsx     # 경로 폴리라인
│   │   │   │   └── DrawingLayer.tsx     # 사용자 드로잉
│   │   │   ├── Controls/
│   │   │   │   ├── TyphoonSelector.tsx  # 연도/이름 필터
│   │   │   │   └── VariablePanel.tsx    # 기압/온도 슬라이더
│   │   │   └── Feedback/
│   │   │       └── FeedbackPanel.tsx    # AI 피드백 표시
│   │   ├── hooks/
│   │   │   ├── useTyphoonData.ts
│   │   │   └── usePrediction.ts
│   │   ├── api/
│   │   │   └── typhoonApi.ts            # API 클라이언트
│   │   ├── types/
│   │   │   └── typhoon.ts               # 타입 정의
│   │   └── App.tsx
│   ├── package.json
│   └── vite.config.ts
│
├── backend/                     # FastAPI
│   ├── app/
│   │   ├── main.py
│   │   ├── routers/
│   │   │   ├── typhoons.py      # 태풍 데이터 라우터
│   │   │   ├── predict.py       # 예측 경로 라우터
│   │   │   └── feedback.py      # AI 피드백 라우터
│   │   ├── services/
│   │   │   ├── typhoon_service.py    # 기상청 API 연동
│   │   │   ├── cache_service.py      # Redis 캐싱
│   │   │   └── claude_service.py     # Claude API 연동
│   │   ├── models/
│   │   │   └── schemas.py            # Pydantic 모델
│   │   └── core/
│   │       ├── config.py             # 환경변수
│   │       └── redis.py              # Redis 연결
│   ├── requirements.txt
│   └── Dockerfile
│
└── docs/                        # BMAD 문서
    ├── project-brief.md
    ├── prd.md
    ├── architecture.md
    └── stories/
```

---

## 3. API 설계

### 3.1 태풍 목록 조회
```
GET /api/typhoons
Query: year (optional), name (optional)
Response: {
  typhoons: [
    { id, name, year, season }
  ]
}
```

### 3.2 태풍 경로 상세 조회
```
GET /api/typhoons/{typhoon_id}/track
Response: {
  id, name, year,
  track: [
    { datetime, lat, lng, pressure, wind_speed, intensity }
  ]
}
```

### 3.3 예측 경로 제출 + AI 피드백
```
POST /api/feedback
Body: {
  typhoon_id: string,
  user_track: [{ lat, lng }],      # 사용자 예측 경로
  user_variables: {
    pressure: number,               # 사용자 설정 기압
    temperature: number             # 사용자 설정 온도
  }
}
Response: {
  actual_track: [{ lat, lng }],
  feedback: string,                 # Claude API 한국어 피드백
  error_summary: {
    avg_distance_km: number,
    direction_bias: string
  }
}
```

---

## 4. 데이터 모델

### Typhoon
```python
class TyphoonTrackPoint(BaseModel):
    datetime: str          # ISO 8601
    lat: float             # 위도
    lng: float             # 경도
    pressure: int          # hPa
    wind_speed: int        # kt
    intensity: str         # TD, TS, TY, STY

class TyphoonData(BaseModel):
    id: str
    name: str
    year: int
    track: List[TyphoonTrackPoint]
```

### FeedbackRequest
```python
class UserTrackPoint(BaseModel):
    lat: float
    lng: float

class FeedbackRequest(BaseModel):
    typhoon_id: str
    user_track: List[UserTrackPoint]
    user_variables: dict
```

---

## 5. Claude API 프롬프트 설계

```python
FEEDBACK_PROMPT = """
당신은 기상 교육 전문가입니다. 사용자가 태풍 경로를 예측했으며, 실제 경로와 비교 분석이 필요합니다.

[태풍 정보]
- 태풍명: {typhoon_name} ({year}년)

[사용자 조작 변수]
- 기압: {pressure} hPa
- 온도: {temperature}°C

[오차 분석]
- 평균 거리 오차: {avg_distance_km} km
- 경로 편향: {direction_bias}

[예측 경로] {user_track}
[실제 경로] {actual_track}

다음을 포함하여 한국어로 교육적 피드백을 작성해주세요:
1. 예측의 주요 차이점
2. 오차가 발생한 기상학적 원인
3. 핵심 학습 포인트 (3가지 이내)
피드백은 300자 이내로 작성해주세요.
"""
```

---

## 6. Redis 캐싱 전략

| 키 패턴 | TTL | 설명 |
|---------|-----|------|
| `typhoon:list:{year}` | 1시간 | 연도별 태풍 목록 |
| `typhoon:track:{id}` | 1시간 | 태풍 경로 상세 |

---

## 7. 환경변수 (.env)

```
# Backend
ANTHROPIC_API_KEY=
KMA_API_KEY=              # 기상청 API 키
PUBLIC_DATA_API_KEY=      # 공공데이터포털 API 키
REDIS_URL=redis://localhost:6379

# Frontend
VITE_API_BASE_URL=http://localhost:8000
```

---

## 8. 배포 계획

| 구분 | 플랫폼 | 설정 |
|------|--------|------|
| Frontend | Vercel | Auto-deploy from main branch |
| Backend | Railway | Dockerfile 기반 배포 |
| Redis | Railway | Redis 플러그인 |

---

## 다음 단계
→ 개발 스토리 작성 (Scrum Master 단계)
