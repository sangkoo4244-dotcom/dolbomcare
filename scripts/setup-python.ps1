# Python & PostgreSQL 자동 설치 스크립트
# Windows Chocolatey를 사용하여 설치

Write-Host "=== Python 3.11 & PostgreSQL 15 자동 설치 ===" -ForegroundColor Green

# 1. Chocolatey 설치 여부 확인
Write-Host "`n1️⃣ Chocolatey 확인 중..." -ForegroundColor Yellow
$chocoInstalled = Get-Command choco -ErrorAction SilentlyContinue

if (-not $chocoInstalled) {
    Write-Host "Chocolatey 설치 중..." -ForegroundColor Cyan
    Set-ExecutionPolicy Bypass -Scope Process -Force
    [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
    iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
    Write-Host "✓ Chocolatey 설치 완료" -ForegroundColor Green
} else {
    Write-Host "✓ Chocolatey 이미 설치됨" -ForegroundColor Green
}

# 2. Python 설치
Write-Host "`n2️⃣ Python 3.11 설치 중..." -ForegroundColor Yellow
choco install python311 -y
Write-Host "✓ Python 설치 완료" -ForegroundColor Green

# 3. PostgreSQL 설치
Write-Host "`n3️⃣ PostgreSQL 15 설치 중..." -ForegroundColor Yellow
choco install postgresql15 -y --params='/Password:dolbomcare123'
Write-Host "✓ PostgreSQL 설치 완료" -ForegroundColor Green

# 4. PATH 업데이트 확인
Write-Host "`n4️⃣ PATH 확인 중..." -ForegroundColor Yellow
$pythonPath = python --version 2>$null
$psqlPath = psql --version 2>$null

if ($pythonPath) {
    Write-Host "✓ Python: $pythonPath"
} else {
    Write-Host "⚠️ Python PATH 업데이트 필요 (PowerShell 재시작 후 확인)"
}

if ($psqlPath) {
    Write-Host "✓ PostgreSQL: $psqlPath"
} else {
    Write-Host "⚠️ PostgreSQL PATH 업데이트 필요 (PowerShell 재시작 후 확인)"
}

Write-Host "`n✅ 설치 완료!" -ForegroundColor Green
Write-Host "PowerShell을 재시작한 후 다시 진행해주세요." -ForegroundColor Cyan
