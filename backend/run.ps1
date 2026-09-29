# Backend 실행 스크립트

# 1. 가상환경 활성화
Write-Host "🐍 가상환경 활성화 중..." -ForegroundColor Cyan
.\venv\Scripts\Activate.ps1

# 2. 패키지 설치
Write-Host "📦 패키지 설치 중..." -ForegroundColor Cyan
pip install -r requirements.txt --quiet

# 3. 데이터베이스 초기화 및 테스트 계정 생성
Write-Host "💾 데이터베이스 테이블 생성 및 테스트 계정 생성 중..." -ForegroundColor Cyan
python create_test_accounts.py

# 4. Backend 서버 시작
Write-Host "`n🚀 Backend 서버 시작 중..." -ForegroundColor Green
Write-Host "📍 API Docs: http://localhost:8000/docs" -ForegroundColor Yellow
Write-Host "🔗 API 기본 URL: http://localhost:8000/api/v1" -ForegroundColor Yellow
uvicorn main:app --reload --host 0.0.0.0 --port 8000
