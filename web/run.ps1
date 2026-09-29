# 웹 개발 서버 실행 스크립트

Write-Host "🌐 웹 개발 서버 시작 중..." -ForegroundColor Cyan

# 패키지 설치 확인
Write-Host "📦 패키지 설치 확인 중..." -ForegroundColor Cyan
if (-not (Test-Path "node_modules")) {
    Write-Host "패키지 설치 중..." -ForegroundColor Yellow
    npm install
}

# 개발 서버 시작
Write-Host "🚀 개발 서버 시작 중..." -ForegroundColor Green
Write-Host "📍 웹 앱 URL: http://localhost:3000" -ForegroundColor Yellow
Write-Host "💡 Backend API: http://localhost:8000/api/v1" -ForegroundColor Yellow
npm run dev
