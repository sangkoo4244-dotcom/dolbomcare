# Mobile 실행 스크립트

Write-Host "📱 Mobile 앱 시작 중..." -ForegroundColor Cyan

# npm 패키지 설치 (필요시)
Write-Host "📦 패키지 설치 확인 중..." -ForegroundColor Cyan
npm install

# Expo 시작 (웹 브라우저에서 실행)
Write-Host "🚀 Expo 시작 중..." -ForegroundColor Green
Write-Host "💡 팁: 'w'를 눌러 웹 브라우저에서 실행" -ForegroundColor Yellow
Write-Host "💡 팁: 'a'를 눌러 Android Emulator에서 실행" -ForegroundColor Yellow
Write-Host "💡 팁: 'i'를 눌러 iOS Simulator에서 실행" -ForegroundColor Yellow
npx expo start
