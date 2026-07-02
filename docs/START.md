# 🌀 TyphoonPath — 실행 가이드

## 환경 준비

### 필수 설치
- Python 3.11+
- Node.js 20+

---

## 백엔드 실행

```bash
cd backend

# 1. 가상환경 생성
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Mac/Linux

# 2. 패키지 설치
pip install -r requirements.txt

# 3. 환경변수 설정
copy .env.example .env
# .env 파일에서 ANTHROPIC_API_KEY 값을 입력

# 4. 서버 시작
uvicorn app.main:app --reload --port 8000
```

API 확인: http://localhost:8000/docs

---

## 프론트엔드 실행

```bash
cd frontend

# 1. 패키지 설치
npm install

# 2. 개발 서버 시작
npm run dev
```

서비스: http://localhost:5173

---

## Redis (선택 — 캐싱)

Redis가 없어도 동작합니다. 캐싱 없이 실행됩니다.
설치가 필요할 경우: https://redis.io/downloads

---

## 프로젝트 구조

```
AX_project/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI 앱 진입점
│   │   ├── core/            # 설정, Redis 연결
│   │   ├── models/          # Pydantic 스키마
│   │   ├── routers/         # API 엔드포인트
│   │   └── services/        # 비즈니스 로직
│   ├── data/
│   │   └── typhoons.json    # 변환된 태풍 데이터 (16.5MB)
│   └── requirements.txt
│
├── frontend/
│   ├── src/
│   │   ├── App.tsx          # 메인 레이아웃
│   │   ├── api/             # API 호출 함수
│   │   ├── components/      # UI 컴포넌트
│   │   ├── hooks/           # 커스텀 훅
│   │   └── types/           # TypeScript 타입
│   └── package.json
│
└── docs/                    # BMAD 문서
```

---

## API 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | /api/typhoons/years | 보유 연도 목록 |
| GET | /api/typhoons?year=2023 | 태풍 목록 (연도 필터) |
| GET | /api/typhoons/{id} | 태풍 상세 경로 |
| POST | /api/feedback | AI 피드백 생성 |
