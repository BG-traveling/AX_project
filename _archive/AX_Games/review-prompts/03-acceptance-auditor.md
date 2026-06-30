# Acceptance Auditor Review

`spec-disaster-family-survival.md`와 아래 구현을 함께 읽고 승인 기준을 감사해 주세요.

- `package.json`, `vite.config.ts`, `tsconfig.json`
- `src/**/*`
- `README.md`

다음을 확인하세요.

- 모든 쓰기와 생성물이 `AX_Games` 내부인지
- React, TypeScript, Vite, Vitest와 정확한 스크립트
- 1~3명 선택과 3명 기준 빵 6·물 6·구급상자 3
- 세 재난, 30일 행동 기반 진행, 이벤트, 파밍, 엔딩
- 가족별 외형·능력·상태 변화
- 어린이 친화적 용어가 UI·주석·README·테스트·승인 기준에 사용되는지
- 반응형과 키보드 접근성
- `npm test -- --run`, `npm run build` 통과 여부

각 기준을 통과/실패/부분 통과로 표시하고, 실패는 파일·줄과 수정 방향을 제시하세요.
