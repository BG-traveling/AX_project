# _archive — 구파일 보관 폴더

TyphoonPath 프로젝트에서 현재 사용하지 않는 파일들을 보관합니다.  
삭제하지 않고 보관하는 이유: 참고 또는 롤백 필요 시 복구 가능하도록.

---

## 폴더별 내용

### `root/`
루트에 있던 불필요한 파일들

| 파일 | 원래 위치 | 보관 이유 |
|------|-----------|-----------|
| `requirements.txt` | `/requirements.txt` | 루트에 잘못 생성된 pip freeze 전체 목록. 실제 의존성은 `backend/requirements.txt` 사용 |
| `test.py` | `/test.py` | 개발 초기 API 테스트 스크립트, 현재 불필요 |
| `typhoonpath_ui_architecture_diagram.svg` | `/typhoonpath_ui_architecture_diagram.svg` | 초기 UI 다이어그램 SVG. `docs/화면설계서.html` + `docs/typhoonpath_flowchart.drawio`로 대체됨 |
| `AX_자동화.zip` | `/AX_자동화.zip` | 원본 기획 zip 압축본 |

### `AX_Games/`
TyphoonPath와 별개인 "재난 가족 생존" 게임 프로젝트.  
TyphoonPath 프로젝트와 무관하므로 분리 보관.

### `frontend/`
App.tsx에서 더 이상 import하지 않는 프론트엔드 컴포넌트들.  
서비스 방향 전환(v1 드로잉 방식 → v2 AI 예측 방식) 과정에서 사용 중단.

| 파일 | 원래 위치 | 보관 이유 |
|------|-----------|-----------|
| `components/Controls/TyphoonSelector.tsx` | `frontend/src/components/Controls/` | v1 태풍 선택 UI — v2에서 지도 클릭으로 대체 |
| `components/Controls/VariablePanel.tsx` | `frontend/src/components/Controls/` | v1 변수 패널 — v2 App.tsx 인라인 슬라이더로 대체 |
| `components/Feedback/FeedbackPanel.tsx` | `frontend/src/components/Feedback/` | v1 피드백 패널 — v2에서 AI 해설 패널로 대체 |
| `hooks/useTyphoonData.ts` | `frontend/src/hooks/` | v1 데이터 훅 — v2에서 직접 API 호출 방식으로 변경 |

### `backend/`

#### `services/`
| 파일 | 보관 이유 |
|------|-----------|
| `analog_service.py` | 초기 유사 태풍 탐색 서비스. `blend_service.py`(Analog Blending)로 완전 대체됨 |

#### `scripts/`
데이터 변환/전처리 스크립트. 이미 1회 실행 완료 → `typhoons.json` 생성됨.  
재실행 필요 시 여기서 복구 가능.

| 파일 | 보관 이유 |
|------|-----------|
| `convert_data.py` | IBTrACS CSV → typhoons.json 변환 (완료) |
| `enhance_data.py` | wind_10min, diameter 필드 추가 (완료) |

#### `data/`
| 파일 | 크기 | 보관 이유 |
|------|------|-----------|
| `typhoons_sample.json` | 48KB | 개발 초기 샘플 데이터 |
| `typhoons_v2.json` | 39MB | 중간 변환 버전, `typhoons.json`으로 대체 |
| `ibtracs.WP.list.v04r01.csv` | 109MB | WP 원본 CSV — typhoons.json 변환 완료 |
| `ibtracs.ALL.list.v04r01.csv` | 316MB | 전체 지역 원본 CSV — WP만 사용하므로 불필요 |

### `docs/`
| 파일 | 보관 이유 |
|------|-----------|
| `diagram.html` | 초기 HTML 플로우차트. `typhoonpath_flowchart.drawio`로 대체됨 |

---

## 수동 삭제 권장 항목

샌드박스 권한 이슈로 자동 삭제되지 않은 항목들.  
Windows 탐색기에서 직접 삭제하거나, 정리 완료 후 `_archive` 전체 삭제 가능.

- `AX_Games/` 폴더 (루트) — `_archive/AX_Games/`에 복사 완료
- `frontend/src/components/Controls/` 빈 폴더
- `frontend/src/components/Feedback/` 빈 폴더
- `frontend/src/hooks/` 빈 폴더
