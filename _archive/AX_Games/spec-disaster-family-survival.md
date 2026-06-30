---
title: '30일 재난 가족 생존 교육 게임'
type: 'feature'
created: '2026-06-30'
status: 'in-review'
baseline_commit: '8be3f4a19323d713f357e5ecdd151e2990b909c1'
context:
  - '{project-root}/frontend/package.json'
  - '{project-root}/frontend/vite.config.ts'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 기존 태풍 경로 예측 프로젝트를 변경하지 않고, 어린이가 가족과 함께 자연재해 안전 수칙을 배우며 30일을 생존하는 완성도 높은 미니게임이 필요하다.

**Approach:** 기존 React·TypeScript·Vite 실행 경험과 위험도 시각화 아이디어만 참고해 `AX_Games`에 React·TypeScript·Vite·Vitest 기반의 독립 브라우저 게임을 만든다. 코드 기반 2D 캐릭터·거실 배경, 데이터 주도 이벤트, 자원·상태·파밍·다중 엔딩을 하나의 플레이 루프로 연결한다.

## Boundaries & Constraints

**Always:** 구현 전에 `{project-root}/AX_Games` 존재 여부를 확인하며, 기존 내용이 있으면 요약 후 진행 방식을 확인받는다. 모든 생성 파일, 설정, 테스트, README와 수정은 `{project-root}/AX_Games` 내부로 제한한다. 가족은 1~3명을 선택하며 체력·배고픔·갈증과 고유 능력·표정 상태를 가진다. 게임은 태풍·집중호우·지진 중 하나를 선택해 1~30일 동안 진행하며, 매일 선택 결과와 교육 팁을 제공한다. 하루의 남은 3분을 카운트다운으로 보여주되 시간이 끝나도 자동 진행하지 않으며, 선택 결과 스토리와 행동 모션을 확인한 뒤 플레이어 행동으로 다음 날을 진행한다. 시작 자원은 인원수에 비례하고 3명 기준 빵 6, 물 6, 구급상자 3이다. UI, 주석, README, 테스트와 승인 기준 전체에서 “사망”, “전원 사망” 대신 “행동 불가”, “구조 대기” 등 어린이 친화적 문구를 사용한다. 반응형이며 키보드로 조작 가능해야 한다.

**Ask First:** 외부 API, 유료 에셋, 서버·데이터베이스, 기존 프로젝트 파일 변경이 필요해지는 경우.

**Never:** 기존 `AX_Games` 내용을 확인 없이 덮어쓰지 않는다. 기존 `frontend`, `backend`, `docs`, 루트 설정, 기존 데이터와 기타 원본 프로젝트 파일을 수정하거나 이동하지 않는다. 타이머 만료만으로 날짜를 자동 진행하는 방식, “사망” 및 “전원 사망” 용어, 잔혹·공포 표현, 개인정보 수집, 원격 쓰기, 원본 태풍 코드를 직접 의존하지 않는다.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 게임 시작 | 가족 1~3명과 재난 선택 | 인원 비례 자원으로 1일차 시작 | 미선택이면 안내하고 시작 버튼 비활성화 |
| 하루 진행 | 이벤트 선택 또는 파밍 결과 | 상태·자원·위험도·로그 갱신 후 다음 날 | 수치는 0~100, 아이템은 0 이상으로 제한 |
| 생존 소모 | 음식·물이 부족함 | 해당 수치 20 감소, 0이면 체력 50 감소 | 행동 불가 캐릭터는 이후 소모·파밍 대상에서 제외 |
| 게임 종료 | 30일 도달 또는 전원 체력 0 | 생존·구조 대기 상태와 구조 점수·대비 점수에 따른 엔딩 | 다시 시작으로 초기 상태 완전 복원 |
| 작은 화면 | 모바일·태블릿 | 패널이 읽기 좋은 단일 열로 재배치 | 가로 스크롤 없이 핵심 조작 유지 |

</frozen-after-approval>

## Code Map

- `AX_Games/src/data/gameData.ts` — 가족 능력, 재난, 이벤트, 파밍 결과의 데이터 정의
- `AX_Games/src/types/game.ts` — 상태와 이벤트 계약
- `AX_Games/src/game/engine.ts` — 순수 상태 전이, 자원 소모, 엔딩 판정
- `AX_Games/src/App.tsx` — 준비 화면과 30일 플레이 흐름
- `AX_Games/src/components/` — 캐릭터 카드, 재난형 거실, 상태·선택 UI
- `AX_Games/src/styles.css` — 코드 기반 2D 아트, 애니메이션, 반응형 레이아웃
- `AX_Games/package.json` — `dev`, `build`, `test` 스크립트와 React·Vite·TypeScript·Vitest 의존성
- `AX_Games/vite.config.ts` — Vite React 플러그인과 Vitest 환경 설정
- `AX_Games/tsconfig.json` — `tsc -b`를 위한 TypeScript 프로젝트 설정
- `AX_Games/src/game/engine.test.ts` — 핵심 생존 규칙 검증
- `AX_Games/README.md` — 실행법, 구조, 교육·발표 포인트

## Tasks & Acceptance

**Execution:**
- [x] `AX_Games/package.json`, `AX_Games/vite.config.ts`, `AX_Games/tsconfig.json` — 각각 `dev: vite`, `build: tsc -b && vite build`, `test: vitest`를 제공하는 독립 React·TypeScript·Vite·Vitest 환경 구성
- [x] `AX_Games/src/types/game.ts`, `AX_Games/src/data/gameData.ts` — 확장 가능한 가족·재난·이벤트·파밍 데이터 작성
- [x] `AX_Games/src/game/engine.ts` — 30일 상태 전이, 능력 보정, 자원 소모, 피해, 엔딩 구현
- [x] `AX_Games/src/App.tsx`, `AX_Games/src/components/` — 가족/재난 선택, 게임 HUD, 이벤트 선택, 파밍, 로그, 엔딩 구현
- [x] `AX_Games/src/styles.css` — 가족별 실루엣·표정과 위험도에 반응하는 거실 배경 구현
- [x] `AX_Games/src/game/engine.test.ts` — 인원별 자원, 수치 경계, 행동 불가, 30일 엔딩 테스트
- [x] `AX_Games/README.md` — 실행법, 구현 기능, 확장 아이디어, 해커톤 발표 포인트 정리

**Acceptance Criteria:**
- Given 가족 선택 화면, when 4번째 가족을 선택하려 하면, then 최대 3명 안내가 표시되고 기존 선택은 유지된다.
- Given 3명과 재난을 선택, when 게임을 시작하면, then 빵 6·물 6·구급상자 3과 각 상태 100으로 1일차가 열린다.
- Given 플레이 중, when 이벤트 선택 또는 파밍을 수행하면, then 캐릭터 능력이 결과에 반영되고 상태·아이템·표정·로그·배경 위험 표현이 함께 갱신된다.
- Given 플레이어가 하루 행동을 마치면, when 식량과 물이 소비되면, then 실제 타이머 없이 부족 규칙과 0 도달 체력 피해가 적용되고 다음 날 새 이벤트가 표시된다.
- Given 30일 도달 또는 모든 가족이 행동 불가 상태, when 종료 조건을 충족하면, then 조건에 맞는 엔딩과 교육 요약 및 재시작 동작이 제공된다.
- Given `npm run build`와 `npm test`, when 실행하면, then TypeScript 빌드와 핵심 규칙 테스트가 성공한다.

## Spec Change Log

- 2026-06-30: 플레이테스트에서 남은 시간과 선택 결과가 불명확하고 행동이 정적으로 보인다는 피드백을 반영했다. 3분 안내 카운트다운, 결과 스토리 단계, 상태 변화 요약, 캐릭터 행동 모션을 추가하되 타이머 자동 진행은 금지해 시연 안정성을 유지한다.
- 2026-06-30: 단순 생존을 넘어 지속적인 학습 동기와 성찰을 제공하도록 콤보 XP, 안전 등급, 디지털 배지, 선택 기록, 경험-성찰-전략 루프, 개인화 학습 리포트와 복합 재난 시나리오 메타데이터를 추가했다.
- 2026-06-30: 파밍 물품 획득이 지나치게 어렵다는 플레이 피드백에 따라 물품 획득 시도를 성공 50%, 미획득 50%로 판정하고 두 결과를 스토리와 로그에 구분해 표시하도록 변경했다.
- 2026-06-30: 파밍 성공 보상이 같은 날 자원 소비에 즉시 차감되어 비상 물품에 보이지 않던 문제를 수정했다. 파밍 날은 기존 비축분을 먼저 소비한 뒤 성공 보상인 빵 4개·물 3개를 저장한다.
- 2026-06-30: 음식과 물의 회복량을 각각 30으로 높였다. 파밍 사건을 6개 장소로 확장해 구급상자 획득을 포함하고, 출발 시 사건을 무작위 선택하도록 변경했다. 성찰 후 전략은 10개 풀에서 중복 없는 3개를 무작위로 제시한다.

## Design Notes

백엔드가 필요 없는 로컬 상태 기반 구조로 해커톤 시연 안정성을 높인다. 이벤트와 캐릭터는 데이터 배열로 분리해 교사가 문구·수치를 쉽게 추가할 수 있게 한다. 하루는 약 3분 분량의 서사 단위만 의도하고, v1은 실제 타이머 없이 선택과 “다음 날” 행동으로 진행한다.

## Verification

**Commands:**
- `cd AX_Games; npm install` — 의존성 설치 성공
- `npm test -- --run` — 생존 엔진 테스트 전체 통과
- `npm run build` — 타입 검사와 프로덕션 빌드 성공
- `npm run dev` — 브라우저에서 준비·플레이·엔딩 화면 동작
