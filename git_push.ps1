# TyphoonPath GitHub Push Script
# 실행: 이 파일을 우클릭 → "PowerShell로 실행"

$ErrorActionPreference = "Stop"
$projectPath = "C:\kdh\AX_project"

Set-Location $projectPath
Write-Host "📁 경로: $projectPath" -ForegroundColor Cyan

# lock 파일 제거
$lockFile = ".git\index.lock"
if (Test-Path $lockFile) {
    Remove-Item $lockFile -Force
    Write-Host "🔓 index.lock 제거 완료" -ForegroundColor Yellow
}

# git 설정
git config user.email "onthegroundplay403@gmail.com"
git config user.name "김동현"
Write-Host "⚙️  git 사용자 설정 완료" -ForegroundColor Green

# 스테이징
Write-Host "`n📦 파일 추가 중..." -ForegroundColor Cyan
git add .gitignore
git add backend/
git add frontend/
git add docs/
git add SRS.md
git add START.md
git add AGENTS.md
git add requirements.txt
git add typhoonpath_ui_architecture_diagram.svg

# PDF, 참고문서 (존재하는 경우)
if (Test-Path "김동현_AX자동화_기획안.pdf") {
    git add "김동현_AX자동화_기획안.pdf"
}
if (Test-Path "참고용 문서") {
    git add "참고용 문서/"
}

# 상태 확인
Write-Host "`n📋 스테이징 현황:" -ForegroundColor Cyan
git status --short

# 커밋 메시지
$commitMsg = @"
feat: DAY 3 완료 - ML/딥러닝 예측 모델 구축 및 경로 품질 개선

[DAY 1] 기초 구축
- React 18 + TypeScript + Vite + Leaflet.js 프론트엔드
- FastAPI 백엔드 (8파일 구조)
- IBTrACS WP CSV → typhoons.json 변환 (2,645개 태풍, 16.5MB)
- Redis 캐싱 연동

[DAY 2] 서비스 전환 및 핵심 기능
- 물리 모델 기반 태풍 경로 예측 서비스로 전환
- Analog Blending 예측 엔진 (유사 태풍 10개 가중평균)
- Claude Haiku AI 기상 해설 연동
- 3단계 UX 플로우 (시작점 선택 → 조건 설정 → 결과 확인)

[DAY 3] ML·딥러닝 고도화
- 새 입력 파라미터: 1분풍속 / 10분풍속 / 최대직경 슬라이더
- IBTrACS 데이터 강화 (typhoons_v2.json, 39MB)
- GBM ML 모델: GradientBoosting 3개 (dlat/dlng/dpres)
- LSTM Seq2Seq+Attention 앙상블 (hidden=48/64/96)
- 4단계 폴백 체인: LSTM→GBM→Analog→Physics
- 현실적 생애주기 기압 모델 (STY→TY→TS→TD→소멸)
- 예측 최대 240h(10일) 확장
- 지도 강도별 색상 구간 + 24h 레이블 + 팝업
- 사이드바 강도 타임라인 바

[BUG FIX]
- STY 강도 무한 지속 버그 수정
- lru_cache None 캐시 버그 수정 (ML 핫로드)
- train_model.py 복소수 오류 수정
- schemas.py 파일 손상 버그 수정
"@

# 커밋
Write-Host "`n💾 커밋 중..." -ForegroundColor Cyan
git commit -m $commitMsg

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ 커밋 완료!" -ForegroundColor Green
} else {
    Write-Host "⚠️  커밋할 변경사항이 없거나 오류 발생" -ForegroundColor Yellow
}

# 푸시
Write-Host "`n🚀 GitHub에 push 중..." -ForegroundColor Cyan
git push -u origin main

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n✅ GitHub push 완료!" -ForegroundColor Green
    Write-Host "🔗 https://github.com/BG-traveling/AX_project" -ForegroundColor Cyan
} else {
    Write-Host "`n❌ push 실패 — GitHub 인증 확인 필요" -ForegroundColor Red
    Write-Host "해결: GitHub CLI(gh auth login) 또는 Personal Access Token 설정" -ForegroundColor Yellow
}

Write-Host "`n아무 키나 누르면 종료..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
