# Story: DAY 3 — AI 피드백 연동 및 최종 점검

**BMAD 단계:** Phase 4 - Development (Scrum Master)  
**목표:** AI 피드백 시스템 완성 + UX 개선 + 배포

---

## Story 3-1: AI 피드백 백엔드 구현

**As a** 개발자  
**I want to** 사용자 예측 경로와 실제 경로를 비교하고 Claude API로 피드백을 생성한다  
**So that** 사용자가 교육적 피드백을 받을 수 있다

### 작업 체크리스트
- [ ] `predict.py` — 예측 경로 저장 로직 (메모리 또는 간단한 dict)
- [ ] `feedback.py` — 예측 vs 실제 경로 거리 오차 계산 (Haversine 공식)
- [ ] `claude_service.py` — Anthropic SDK 연동
  - `anthropic.Anthropic()` 클라이언트 초기화
  - 피드백 프롬프트 조합 및 `messages.create()` 호출
- [ ] `POST /api/feedback` 라우터 구현
  - 입력: typhoon_id, user_track, user_variables
  - 출력: feedback text, actual_track, error_summary

**완료 기준:** POST 요청 시 Claude 피드백 텍스트 정상 반환

---

## Story 3-2: 프론트엔드 피드백 패널

**As a** 사용자  
**I want to** 제출 후 나의 예측 경로와 실제 경로를 지도에서 동시에 비교하고 AI 설명을 읽을 수 있다  
**So that** 내가 어디서 틀렸는지 이해할 수 있다

### 작업 체크리스트
- [ ] `FeedbackPanel.tsx` — AI 피드백 텍스트 표시 영역
- [ ] 지도에 실제 경로 + 사용자 예측 경로 동시 표시 (색상 구분)
- [ ] 오차 요약 표시 (평균 거리 오차, 방향 편향)
- [ ] 로딩 스피너 (Claude API 응답 대기 중)
- [ ] "다시 예측하기" 버튼 → 초기 화면으로 리셋

**완료 기준:** 피드백 화면에서 두 경로 비교 + AI 텍스트 표시

---

## Story 3-3: UI/UX 개선

**As a** 사용자  
**I want to** 서비스가 깔끔하고 직관적으로 보인다  
**So that** 사용 방법을 별도 설명 없이도 알 수 있다

### 작업 체크리스트
- [ ] 반응형 레이아웃 적용 (768px 이상)
- [ ] 각 단계별 안내 메시지 추가 ("태풍을 선택하세요", "경로를 그려주세요" 등)
- [ ] 에러 처리 UI (API 실패 시 친절한 에러 메시지)
- [ ] 로딩 상태 처리 (데이터 조회 중 스피너)
- [ ] 색상 팔레트 통일 및 기본 스타일 정리

**완료 기준:** 주요 사용자 흐름에서 에러/로딩 상태 정상 처리

---

## Story 3-4: 배포

**As a** 개발자  
**I want to** 서비스를 Vercel + Railway에 배포한다  
**So that** 외부에서 접근 가능하다

### 작업 체크리스트

**Backend (Railway)**
- [ ] `Dockerfile` 작성
- [ ] Railway 프로젝트 생성 및 GitHub 연결
- [ ] Redis 플러그인 추가
- [ ] 환경변수 설정 (ANTHROPIC_API_KEY, KMA_API_KEY 등)
- [ ] 배포 및 백엔드 URL 확인

**Frontend (Vercel)**
- [ ] `VITE_API_BASE_URL` 환경변수를 Railway 백엔드 URL로 설정
- [ ] Vercel 프로젝트 생성 및 GitHub 연결
- [ ] 배포 및 프론트엔드 URL 확인

**완료 기준:** 프론트엔드 URL 접속 시 전체 기능 정상 동작

---

## Story 3-5: 최종 테스트

**As a** 개발자  
**I want to** 전체 사용자 흐름을 테스트한다  
**So that** 릴리즈 전 버그를 발견하고 수정할 수 있다

### 테스트 시나리오
- [ ] TC-01: 연도/이름 필터 → 태풍 선택 → 경로 표시
- [ ] TC-02: 기압 슬라이더 조작 → 예상 경로 변화 확인
- [ ] TC-03: 지도 드로잉 → 경로 제출 → 피드백 화면 전환
- [ ] TC-04: AI 피드백 텍스트 정상 수신 및 표시
- [ ] TC-05: API 실패 시 에러 메시지 표시
- [ ] TC-06: 모바일 뷰포트(375px) 레이아웃 확인

**완료 기준:** 6개 시나리오 모두 통과

---

## DAY 3 완료 기준 요약

| 항목 | 상태 |
|------|------|
| Claude API 피드백 생성 | ⬜ |
| 예측/실제 경로 비교 화면 | ⬜ |
| UX 개선 및 에러 처리 | ⬜ |
| Railway 백엔드 배포 | ⬜ |
| Vercel 프론트엔드 배포 | ⬜ |
| 최종 테스트 완료 | ⬜ |
