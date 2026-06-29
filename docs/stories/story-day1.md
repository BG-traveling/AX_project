# Story: DAY 1 — 기초 구축 및 데이터 연동

**BMAD 단계:** Phase 4 - Development (Scrum Master)  
**목표:** 프로젝트 기본 환경 설정 + 실제 태풍 데이터 연동 가능한 기반 마련

---

## Story 1-1: 프론트엔드 환경 구축

**As a** 개발자  
**I want to** React + TypeScript + Vite 환경을 초기 구성한다  
**So that** 개발을 즉시 시작할 수 있다

### 작업 체크리스트
- [ ] `npm create vite@latest frontend -- --template react-ts`
- [ ] Leaflet.js 및 관련 타입 패키지 설치 (`leaflet`, `@types/leaflet`, `react-leaflet`)
- [ ] ESLint + Prettier 설정
- [ ] 기본 App.tsx 레이아웃 구성 (지도 영역 + 사이드 패널)
- [ ] 환경변수 파일 설정 (`.env.local`)

**완료 기준:** `npm run dev` 실행 시 기본 화면 정상 표시

---

## Story 1-2: 백엔드 환경 구축

**As a** 개발자  
**I want to** FastAPI 기반 백엔드를 초기 구성한다  
**So that** API 엔드포인트를 개발할 수 있다

### 작업 체크리스트
- [ ] 가상환경 생성 및 의존성 설치 (`fastapi`, `uvicorn`, `httpx`, `redis`, `python-dotenv`, `anthropic`)
- [ ] `main.py` CORS 설정 포함 기본 앱 구성
- [ ] `requirements.txt` 생성
- [ ] `.env` 파일 설정 (API 키 등)
- [ ] Health check 엔드포인트 추가 (`GET /health`)

**완료 기준:** `uvicorn app.main:app --reload` 실행 후 `/health` 200 응답 확인

---

## Story 1-3: 기상청 / 공공데이터 API 연동

**As a** 개발자  
**I want to** 1951~2024년 태풍 데이터를 외부 API에서 조회한다  
**So that** 실제 태풍 경로 데이터를 서비스에 활용할 수 있다

### 작업 체크리스트
- [ ] 기상청 기상자료개방포털 또는 공공데이터포털 API 키 발급
- [ ] API 응답 구조 파악 (태풍 목록, 경로 포인트 필드 확인)
- [ ] `typhoon_service.py` 작성 — 태풍 목록 조회 함수
- [ ] `typhoon_service.py` 작성 — 특정 태풍 경로 조회 함수
- [ ] 응답 데이터 → Pydantic 스키마 매핑
- [ ] `GET /api/typhoons` 라우터 구현 및 테스트

**완료 기준:** API 호출 시 태풍 목록 JSON 정상 반환

> **대안:** 공식 API 연동이 어려울 경우 IBTrACS (NOAA 국제 태풍 데이터셋) CSV 파일 로컬 저장 후 사용

---

## Story 1-4: Redis 캐싱 연동

**As a** 개발자  
**I want to** 태풍 데이터 응답을 Redis에 캐싱한다  
**So that** 반복 API 호출을 줄이고 응답 속도를 높인다

### 작업 체크리스트
- [ ] Redis 설치 및 `core/redis.py` 연결 모듈 작성
- [ ] `cache_service.py` — get/set/delete 유틸 함수
- [ ] 태풍 목록 캐싱 적용 (TTL: 1시간)
- [ ] 태풍 경로 캐싱 적용 (TTL: 1시간)

**완료 기준:** 2번째 API 호출 시 캐시 히트 로그 확인

---

## DAY 1 완료 기준 요약

| 항목 | 상태 |
|------|------|
| Frontend Vite 앱 구동 | ⬜ |
| Backend FastAPI 구동 | ⬜ |
| 태풍 목록 API 응답 | ⬜ |
| Redis 캐싱 동작 | ⬜ |
