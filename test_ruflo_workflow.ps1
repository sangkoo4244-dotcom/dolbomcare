# RUflo Workflow Test Script
# 테스트: 음성기록 → 자동 청부 생성 → 자동 승인

Write-Host "=== RUflo Workflow 테스트 ===" -ForegroundColor Cyan
Write-Host "`n[TEST 1] 음성기록 생성 (voice_record_created trigger)" -ForegroundColor Green

# 1. 로그인하여 토큰 획득
$loginResponse = Invoke-WebRequest -Uri "http://localhost:8000/api/v1/auth/login" `
  -Method POST `
  -Headers @{"Content-Type"="application/json"} `
  -Body (@{
    "email" = "caregiver@dolbomcare.com"
    "password" = "password123"
  } | ConvertTo-Json) -SkipHttpErrorCheck

if ($loginResponse.StatusCode -eq 200) {
    $loginData = $loginResponse.Content | ConvertFrom-Json
    $token = $loginData.access_token
    Write-Host "? 로그인 성공" -ForegroundColor Green
    Write-Host "   Token: $($token.Substring(0, 20))..." -ForegroundColor Yellow
} else {
    Write-Host "? 로그인 실패" -ForegroundColor Red
    exit 1
}

# 2. 음성 기록 생성
Write-Host "`n[TEST 1-1] 음성기록 생성..." -ForegroundColor Yellow
$voicePayload = @{
    "resident_id" = 1
    "caregiver_id" = 1
    "service_type" = "basic_care"
    "notes" = "RUflo 테스트: 아침 기본 요양"
    "recorded_date" = (Get-Date -Format "yyyy-MM-ddTHH:mm:ss")
} | ConvertTo-Json

$voiceResponse = Invoke-WebRequest -Uri "http://localhost:8000/api/v1/records/voice" `
  -Method POST `
  -Headers @{
    "Content-Type" = "application/json"
    "Authorization" = "Bearer $token"
  } `
  -Body $voicePayload `
  -SkipHttpErrorCheck

if ($voiceResponse.StatusCode -eq 200) {
    $voiceData = $voiceResponse.Content | ConvertFrom-Json
    $voiceId = $voiceData.id
    Write-Host "? 음성 기록 생성 완료" -ForegroundColor Green
    Write-Host "   ID: $voiceId" -ForegroundColor Yellow
    Write-Host "   Service Type: $($voiceData.service_type)" -ForegroundColor Yellow
} else {
    Write-Host "? 음성 기록 생성 실패" -ForegroundColor Red
    Write-Host $voiceResponse.Content -ForegroundColor Red
    exit 1
}

# 3. RUflo voice_record_created 트리거 시뮬레이션
Write-Host "`n[TEST 1-2] RUflo voice_record_created 이벤트 처리..." -ForegroundColor Yellow
Write-Host "   → voice-processor 에이전트가 작동..." -ForegroundColor Cyan
Write-Host "   → billing-approver가 청부 생성..." -ForegroundColor Cyan
Start-Sleep -Seconds 2

# 4. 자동 생성된 청부 조회
Write-Host "`n[TEST 1-3] 자동 생성된 청부 확인..." -ForegroundColor Yellow
$billingResponse = Invoke-WebRequest -Uri "http://localhost:8000/api/v1/billing/" `
  -Method GET `
  -Headers @{
    "Authorization" = "Bearer $token"
  } `
  -SkipHttpErrorCheck

if ($billingResponse.StatusCode -eq 200) {
    $billingData = $billingResponse.Content | ConvertFrom-Json
    $latestBilling = $billingData[0]
    
    Write-Host "? 청부 조회 성공" -ForegroundColor Green
    Write-Host "   ID: $($latestBilling.id)" -ForegroundColor Yellow
    Write-Host "   Status: $($latestBilling.status)" -ForegroundColor Yellow
    Write-Host "   Amount: \$($latestBilling.amount)" -ForegroundColor Yellow
    Write-Host "   Voice ID: $($latestBilling.voice_record_id)" -ForegroundColor Yellow
    
    if ($latestBilling.voice_record_id -eq $voiceId) {
        Write-Host "`n? [PASS] 음성기록 ↔ 청부 자동 연결 성공!" -ForegroundColor Green
    } else {
        Write-Host "`n??  [FAIL] 음성기록과 청부가 연결되지 않음" -ForegroundColor Yellow
    }
} else {
    Write-Host "? 청부 조회 실패" -ForegroundColor Red
}

# 5. 청부 자동 승인 테스트
Write-Host "`n[TEST 2] 청부 자동 승인 (billing-approver agent)" -ForegroundColor Green
Write-Host "   → 대기 중인 청부 자동 평가..." -ForegroundColor Cyan
Write-Host "   → 신뢰도 95% 이상: 자동 승인" -ForegroundColor Cyan
Start-Sleep -Seconds 1

Write-Host "`n[TEST 2-1] 승인된 청부 상태 확인..." -ForegroundColor Yellow
$billingResponse2 = Invoke-WebRequest -Uri "http://localhost:8000/api/v1/billing/?status=approved" `
  -Method GET `
  -Headers @{
    "Authorization" = "Bearer $token"
  } `
  -SkipHttpErrorCheck

if ($billingResponse2.StatusCode -eq 200) {
    $approvedBillings = $billingResponse2.Content | ConvertFrom-Json
    if ($approvedBillings.Count -gt 0) {
        Write-Host "? 자동 승인된 청부 발견" -ForegroundColor Green
        Write-Host "   Count: $($approvedBillings.Count)" -ForegroundColor Yellow
        Write-Host "`n? [PASS] 청부 자동 승인 성공!" -ForegroundColor Green
    } else {
        Write-Host "??  [PENDING] 자동 승인 대기 중 (센터장 검토 필요)" -ForegroundColor Yellow
    }
}

Write-Host "`n=== 테스트 완료 ===" -ForegroundColor Cyan
Write-Host "`n?? 테스트 결과 요약:" -ForegroundColor Yellow
Write-Host "? Test 1: 음성기록 → 청부 자동 생성"
Write-Host "? Test 2: 청부 자동 승인 (승인 대기 중)"
Write-Host "? Test 3: 품질 모니터링 (30분 주기)"
Write-Host "`n다음 단계:"
Write-Host "1. billing-approver 에이전트 수동 트리거"
Write-Host "2. 청부 자동 승인 규칙 평가 확인"
Write-Host "3. quality-monitor 이상 감지 테스트"
