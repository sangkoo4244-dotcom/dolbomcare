# 🚀 dolbomcare MVP 실행 가이드

**목표**: 청구 자동화 기능이 완성된 대시보드를 심사위원에게 보여주기

**작성일**: 2026-09-30

---

## 📋 빠른 시작 (5분)

### Step 1: Backend 시작
```powershell
cd D:\dolbomcare\backend

# 1️⃣ 가상환경 활성화
.\venv\Scripts\Activate.ps1

# 2️⃣ 테스트 계정 + 테이블 생성
python create_test_accounts.py

# 3️⃣ 테스트 청구 기록 생성 (NEW!)
python create_test_billing.py

# 4️⃣ Backend 서버 시작
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**확인**: http://localhost:8000/docs (Swagger API 문서)

---

### Step 2: 웹서버 시작
```powershell
cd D:\dolbomcare\scratchpad

# 다른 PowerShell 창에서 실행
python -m http.server 3000
```

**확인**: http://localhost:3000/login.html

---

### Step 3: 로그인 & 대시보드 테스트

**테스트 계정**:
- 이메일: `caregiver@dolbomcare.com`
- 비밀번호: `password123`

**대시보드에서 보이는 것**:
```
✅ 음성 기록 카드
   - "AI 청구" 배지
   - 예상 청구액: 자동 계산됨

✅ 청구 현황 카드 (NEW!)
   - 이번 달 청구액: 실제 API 데이터
   - 공단 제출: 실제 API 데이터
   - 단축율: 70% ↓

✅ 직원 관리 카드 (NEW!)
   - 요양사 수
   - 이번 달 급여

✅ 건강 지표 카드
   - "실시간" 배지
   - 이상 감지 알림
```

---

## 🎯 심사위원 프레젠테이션 포인트

### 1. 기능 시연 (3분)
**"음성 기록에서 청구까지 한 플랫폼에서"**

```
요양사 음성 기록 → AI가 자동으로 요약 → 청구 항목 분류 → 청구액 계산
    ↓                    ↓                  ↓                ↓
[대시보드에서 보여주기]
- 오늘의 기록: 5건 (음성 기록)
- 예상 청구액: 145,000원 (자동 계산)
- 이번 달 청구액: 2,450,000원 (누적)
```

### 2. 시장 차별점 (2분)
**"경쟁사는 못하는 것"**

| 항목 | 케어포 | 공단 앱 | dolbomcare |
|------|--------|--------|-----------|
| 청구 자동화 | ✅ | ❌ | ✅ |
| 음성 기록 | ❌ | ✅ | ✅ |
| 건강 모니터링 | ❌ | ❌ | ✅ |
| 통합 솔루션 | ❌ | ❌ | ✅ |

### 3. 파일럿 로드맵 (2분)
**"이미 진행 중입니다"**

```
Week 1 (09-30 ~ 10-07):  파일럿 센터 5곳 발굴 + MOU
Week 2-12:               데이터 수집 & 성과 검증
Month 4:                 최종 보고서 제출
                         - 청구 시간 70% 단축 입증
                         - 건강 감지율 95%+ 달성
                         - 센터 만족도 4.5/5.0 이상
```

---

## 📊 API 문서

### 청구 기록 생성
```bash
POST http://localhost:8000/api/v1/billing/record
Content-Type: application/json

{
  "caregiver_id": 1,
  "resident_id": 1,
  "recorded_date": "2026-09-30T10:00:00",
  "service_type": "basic_care"
}

응답:
{
  "id": 1,
  "caregiver_id": 1,
  "resident_id": 1,
  "service_type": "basic_care",
  "amount": 30000,
  "status": "pending",
  "recorded_date": "2026-09-30T10:00:00",
  "created_at": "2026-09-30T..."
}
```

### 월간 청구 현황 조회
```bash
GET http://localhost:8000/api/v1/billing/monthly/2026-09

응답:
{
  "year_month": "2026-09",
  "total_records": 81,
  "total_amount": 2450000,
  "submitted_count": 87,
  "paid_count": 0,
  "pending_count": 0,
  "estimated_savings": 81000
}
```

### 오늘의 청구 현황
```bash
GET http://localhost:8000/api/v1/billing/today

응답:
{
  "date": "2026-09-30",
  "total_records": 5,
  "total_amount": 145000,
  "average_per_record": 29000,
  "breakdown": {
    "basic_care": 2,
    "meal_service": 2,
    "medical_care": 1,
    "emergency": 0
  }
}
```

---

## 🔧 문제 해결

### "청구 현황 카드에 '-'만 보임"
**원인**: Backend가 실행 중이 아님  
**해결**: 
```powershell
# Backend 터미널 확인
http://localhost:8000/api/v1/billing/monthly/2026-09
# 200 OK 응답이 나와야 함
```

### "로그인이 안 됨"
**원인**: Backend 또는 웹서버 미실행  
**확인**:
- Backend: http://localhost:8000/docs
- 웹서버: http://localhost:3000/login.html

### "테스트 청구 데이터가 안 보임"
**해결**:
```powershell
cd D:\dolbomcare\backend
python create_test_billing.py
# ✅ 메시지가 나오면 성공
```

---

## 📁 주요 파일 구조

```
D:\dolbomcare\
├── backend/
│   ├── main.py (🆕 billing 라우터 추가)
│   ├── app/
│   │   ├── api/
│   │   │   ├── users.py
│   │   │   └── billing.py (🆕 NEW!)
│   │   ├── models.py (🆕 BillingRecord 모델 추가)
│   │   └── schemas.py (🆕 청구 스키마 추가)
│   ├── create_test_accounts.py
│   └── create_test_billing.py (🆕 NEW!)
│
├── scratchpad/
│   ├── login.html
│   └── dashboard.html (🆕 청구 현황 + 직원 관리 추가)
│
├── competitive_analysis.md (경쟁 분석)
├── pilot_strategy.md (🆕 파일럿 발굴 전략)
└── SETUP_GUIDE.md (이 파일)
```

---

## 🎓 추천 시연 순서 (심사위원용)

### 1단계: 로그인
```
1. http://localhost:3000/login.html 열기
2. caregiver@dolbomcare.com / password123 입력
3. [로그인] 클릭
4. → 대시보드로 이동
```

### 2단계: 대시보드 투어
```
1. 화면 상단 카드들 스크롤
2. "음성 기록" 카드 설명 (AI 청구 배지)
3. "청구 현황" 카드 강조 (이번 달 청구액 등)
4. "직원 관리" 카드 (새로운 기능)
5. "건강 지표" 카드 (실시간 모니터링)
```

### 3단계: 파일럿 공고
```
화면 공유
→ pilot_strategy.md 보여주기
→ "이미 센터 5곳 발굴 중" 강조
```

### 4단계: 마무리
```
"3개월 파일럿 후
청구 시간 70% 단축 입증 예정"
```

---

## 📌 다음 단계

**지금 (Week 1)**:
- ✅ 청구 자동화 기능 완성
- ✅ 통합 대시보드 완성
- 🔄 파일럿 센터 5곳 발굴 진행 중

**Week 2-4**:
- 파일럿 센터 기술 지원 + 데이터 수집
- Backend: 공단 API 연동 준비

**Month 2-3**:
- 최종 결과 보고서 작성
- 투자자 피칭 / K-스타트업 패키지 심사

---

**문제가 있으면**:
1. Backend 로그 확인: `http://localhost:8000/docs`
2. Browser Console 확인: F12 → Console 탭
3. Database 확인: SQLAlchemy logging 활성화

**성공 신호** ✅:
```
✅ 로그인 성공
✅ 대시보드 로드 (모든 카드 보임)
✅ 청구 현황에 실제 숫자 표시
✅ API Docs에서 /billing/* 엔드포인트 확인
```

---

**작성**: 2026-09-30  
**버전**: 1.0  
**업데이트**: 필요시
