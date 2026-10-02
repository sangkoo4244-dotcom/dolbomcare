# 돌봄케어 음성기록 시스템 전체 분석

## 1️⃣ 현재 시스템 흐름 분석

### 프론트엔드 흐름 (voice_record.html)
```
사용자 액션
    ↓
1. 페이지 로드 (DOMContentLoaded + load 이벤트)
    ├─ 인증 확인 (checkAuth, 줄 637)
    ├─ 메뉴 필터링 (filterMenuByRole)
    └─ 이용자 목록 로드 (loadResidents, 줄 655)
    ↓
2. 이용자 선택
    ├─ residentSelect 변경 이벤트 (줄 675)
    ├─ 이용자 상세 조회 API (/residents/{id})
    ├─ 청부액 정보 계산 및 표시
    │  ├─ CARE_GRADE_LIMITS (줄 567)
    │  ├─ PATIENT_PAY_RATE (줄 568)
    │  └─ 계산식: visitAmount = (monthlyLimit / 20) * insuranceRate
    └─ UI 업데이트 (gradeInfo, monthlyLimit, estimatedBilling, patientPayInfo)
    ↓
3. 서비스 유형 선택 (줄 714)
    └─ selectedServiceType 변수에 저장
    ↓
4. 메모 작성
    └─ notesInput textarea에 텍스트 입력
    ↓
5. 기록 저장 (saveRecord 함수, 줄 720)
    ├─ 유효성 검사
    │  ├─ residentId 필수 확인
    │  └─ selectedServiceType 필수 확인
    ├─ API 호출: POST /records/create
    │  └─ Body: { caregiver_id, resident_id, service_type, notes }
    ├─ 응답 처리
    │  ├─ 성공: 토스트 표시, 폼 초기화, 기록 새로고침
    │  └─ 실패: 에러 알림
    └─ 대시보드 새로고침 플래그 설정 (dashboardRefresh)
    ↓
6. 기록 조회
    ├─ 탭 선택 (오늘/7일/전체) - switchRecordTab (줄 781)
    ├─ API 호출:
    │  ├─ 오늘: GET /records/today
    │  ├─ 7일: GET /records/recent?days=7
    │  └─ 전체: GET /records/all
    ├─ renderRecords (줄 870)로 UI 렌더링
    │  ├─ 날짜별 그룹핑 (groupRecordsByDate, 줄 817)
    │  ├─ 권한 확인 (센터장/요양사)
    │  ├─ 선택 삭제 기능 UI 추가
    │  └─ 편집/삭제 버튼 표시
    └─ 청부액 합계 로드 (loadBillingAmount, 줄 934)
    ↓
7. 기록 편집 (openEditModal, 줄 997)
    ├─ 모달 열기
    ├─ 기존 값 표시 (서비스유형, 메모)
    ├─ 수정 저장 (saveRecordEdit, 줄 1012)
    │  └─ API: PATCH /records/{recordId}
    └─ 기록 목록 새로고침
    ↓
8. 기록 삭제
    ├─ 개별 삭제 (deleteRecord, 줄 1048)
    │  └─ DELETE /records/{recordId}?user_id&user_role
    └─ 일괄 삭제 (deleteSelectedRecords, 줄 974)
        └─ POST /records/batch-delete
           └─ Body: { record_ids, user_id, user_role }
```

### 백엔드 API 흐름 (records.py)

#### POST /records/create (줄 75)
```python
입력 검증
    ↓
Resident 조회 (줄 84, 91)
    ├─ resident.care_grade 확인
    └─ resident.center_id 확인
    ↓
청부액 계산 (줄 97-106)
    ├─ CARE_GRADE_LIMITS에서 월 인정급여액 조회
    ├─ PATIENT_PAY_RATE에서 본인부담율 조회
    ├─ 월 기준 방문 수: 20회 (줄 21)
    ├─ 공단청부액 = (월액 / 20) * (1 - 본인부담율)
    └─ amount = int(base_amount * insurance_rate)
    ↓
DailyRecord 생성 (줄 112-125)
    ├─ recorded_date = datetime.now() (로컬 시간)
    ├─ service_type 저장
    ├─ notes 저장
    └─ DB flush (id 획득)
    ↓
BillingRecord 자동 생성 (줄 130-141)
    ├─ daily_record_id 링크
    ├─ status = "draft" (미제출)
    ├─ approval_status = "draft"
    └─ DB commit
    ↓
응답: { status, message, data: { record_id, billing_id, billing_amount } }
```

#### GET /records/today (줄 442)
```python
오늘 날짜 범위 결정 (줄 455-457)
    ├─ today_start: 00:00:00
    └─ today_end: 23:59:59
    ↓
DailyRecord 조회
    └─ WHERE caregiver_id = ? AND recorded_date BETWEEN today_start AND today_end
    ↓
BillingRecord 매핑 (줄 471-485)
    ├─ daily_record_id별 청부액 조회
    ├─ service_type 및 approval_status 매핑
    └─ 요양사: submitted_to_nhis 제외 (줄 499-500)
    ↓
응답 구성 (줄 516-521)
    └─ { date, total_records, total_billing_amount, records[] }
```

#### DELETE /records/{record_id} (줄 665)
```python
권한 검증 (줄 684-688)
    ├─ 센터장: 모든 기록 삭제 가능
    └─ 요양사: 자신의 기록만 삭제 가능
    ↓
관련 BillingRecord 삭제 (줄 691-693)
    └─ WHERE daily_record_id = {record_id}
    ↓
DailyRecord 삭제 (줄 701)
    ↓
응답: { status: "success", message, record_id }
```

---

## 2️⃣ 버그 및 문제점 찾기

### 🔴 심각한 버그 (Blocker)

#### 1. SERVICE_TYPE_AMOUNTS 미정의 (줄 252)
**파일:** `backend/app/api/records.py:252`
**문제:** `upload_audio` 함수에서 `SERVICE_TYPE_AMOUNTS` 변수를 참조하지만, 정의는 줄 715 아래
**영향:** 음성 파일 업로드 시 KeyError 발생
```python
# ❌ 현재 (줄 252)
base_amount = SERVICE_TYPE_AMOUNTS.get(service_type, {}).get(care_grade, 78875)

# ✅ 해결책
# 줄 715 SERVICE_TYPE_AMOUNTS 정의를 줄 48 위로 이동
```

#### 2. upload_audio 함수의 변수 오류 (줄 252)
**파일:** `backend/app/api/records.py:252`
**문제:** 함수 파라미터에 `request: CreateRecordRequest` 없지만 `request.service_type` 참조 (줄 252)
```python
# ❌ 현재
service_type = request.service_type if hasattr(request, 'service_type') else "basic_care"

# ✅ 해결책
# service_type 파라미터는 함수 파라미터로 이미 전달됨 (줄 726)
service_type = request_service_type  # 파라미터명 확인
```

#### 3. 프론트엔드 주석 이스케이프 문제 (줄 906)
**파일:** `scratchpad/voice_record.html:906`
**문제:** notes 문자열이 마크업에 직접 삽입되어 XSS 취약점 및 따옴표 문제 발생
```html
<!-- ❌ 현재 -->
onclick="openEditModal(${record.id}, '${record.service_type}', '${(record.notes || '').replace(/'/g, "\\'")}')"

<!-- ✅ 해결책 -->
<!-- data 속성을 사용하고 JSON으로 encoding -->
data-record-id="${record.id}" data-record="${JSON.stringify(record)}"
```

### 🟡 중간 수준 버그 (Important)

#### 4. DailyRecord 모델의 불일치
**파일:** `backend/app/models.py:51-64` vs `backend/app/api/records.py:112-122`
**문제:** voice_record.html과 DailyRecord 모델이 다른 필드 사용
```python
# 모델에는 있지만 API에서 사용 안 함:
morning_care, meal_intake, medicine_given

# API에서 설정:
morning_care = service_type == "basic_care"
meal_intake = "full" if service_type == "meal_service" else "partial"
medicine_given = service_type == "medical_care"

# 문제: service_type만으로는 정확한 health_status 파악 불가
```

#### 5. 청부액 계산 불일치
**파일:** `records.py:97-106` vs `records.py:715-720`
**문제:** 두 곳에서 다르게 계산

```python
# ❌ 문제 1: create_record에서는 VISIT_AMOUNTS_BY_GRADE 사용
amount = int(base_amount * insurance_rate)  # 줄 106

# ❌ 문제 2: voice record에서는 SERVICE_TYPE_AMOUNTS 사용
base_amount = SERVICE_TYPE_AMOUNTS[service_type].get(care_grade, 40000)  # 줄 752

# 차이:
# VISIT_AMOUNTS_BY_GRADE: 기본 요양 기준 (service_type 무시)
# SERVICE_TYPE_AMOUNTS: service_type별 다른 금액
```

#### 6. 시간대 불일치
**파일:** `records.py` 전체
**문제:** datetime.utcnow() vs datetime.now() 혼용
```python
# ❌ 줄 79, 217, 743, 764: utcnow() 사용
# ✅ 줄 111, 229, 264: now() 사용

# 한국 시간대와 UTC 혼용으로 데이터 일관성 문제 발생
```

#### 7. 권한 검증 불완전
**파일:** `records.py:682-688`
**문제:** delete_record는 권한 검증하지만, batch_delete는 미흡

```python
# ❌ batch_delete (줄 174-184)
is_manager = request.user_role == "center_manager"
if not (is_manager or is_own_record):
    continue  # 권한 없어도 조용히 스킵

# ✅ delete_record (줄 684-688)
if not (is_manager or is_own_record):
    raise HTTPException(status_code=403, detail="...")
```

#### 8. 청부액 필터링 논리 오류 (줄 391)
**파일:** `records.py:391`
**문제:** get_all_records에서 submitted_to_nhis 필터링이 중복

```python
# 줄 391: is_archived == False만 확인
billings = db.query(BillingRecord).filter(
    BillingRecord.caregiver_id == caregiver_id,
    BillingRecord.is_archived == False
).all()

# 하지만 줄 413-415에서 approval_status == 'submitted_to_nhis' 확인
# → submitted_to_nhis 상태면서 is_archived=False인 기록은?
```

### 🟢 경미한 문제 (Minor)

#### 9. 입력 검증 부족
- **파일:** `voice_record.html:720-726`
- **문제:** 메모(notes) 필드의 길이 제한 없음
- **영향:** DB에 매우 긴 텍스트 저장 가능
- **개선:** `textarea` 속성 추가
  ```html
  <textarea id="notesInput" maxlength="1000" placeholder="..."></textarea>
  ```

#### 10. 에러 메시지 모호
- **파일:** `voice_record.html:764-765`
- **문제:** 일반적인 에러 메시지만 제공
  ```javascript
  // ❌ 현재
  alert('기록 저장 중 오류가 발생했습니다');
  
  // ✅ 개선
  alert(`기록 저장 중 오류: ${error.message}`);
  ```

#### 11. 동시성 제어 부재
- **파일:** `records.py:167-202` (batch_delete)
- **문제:** 여러 사용자가 동시에 같은 기록 삭제 시 race condition 가능
- **해결책:** Transaction isolation level 상향 또는 optimistic locking

#### 12. 로딩 상태 UI 부족
- **파일:** `voice_record.html:888-889`
- **문제:** 대량 삭제(100개 이상) 시 UI 응답성 저하
- **개선:** 진행률 표시 또는 배치 처리

#### 13. 세션/토큰 유효성 검사 없음
- **파일:** `voice_record.html:655`
- **문제:** API 호출 시 Authorization 헤더 전송 없음
- **현재:** fetch(`${API_URL}/residents/?center_id=${centerId}`)
- **개선:** headers에 Authorization 추가

#### 14. 메모리 누수 가능성
- **파일:** `voice_record.html:736-740`
- **문제:** selectedServiceType 전역 변수 계속 유지
- **개선:** 폼 상태를 객체로 관리

#### 15. 중복 API 호출
- **파일:** `voice_record.html:934-954`
- **문제:** loadBillingAmount에서 현재 탭에 따라 같은 데이터 다시 조회
- **개선:** renderRecords에서 이미 받은 total_billing_amount 사용

---

## 3️⃣ 현재 기능 분석

### ✅ 구현된 기능

| 기능 | 프론트엔드 | 백엔드 | 상태 |
|------|----------|--------|------|
| 기록 추가 | ✅ (줄 720) | ✅ (줄 75) | 정상 |
| 기록 조회 (오늘) | ✅ (줄 916) | ✅ (줄 442) | 정상 |
| 기록 조회 (7일) | ✅ (줄 838) | ✅ (줄 283) | 정상 |
| 기록 조회 (전체) | ✅ (줄 854) | ✅ (줄 369) | 정상 |
| 기록 편집 | ✅ (줄 997) | ✅ (줄 613) | 정상 |
| 개별 삭제 | ✅ (줄 1048) | ✅ (줄 665) | 정상 |
| 일괄 삭제 | ✅ (줄 974) | ✅ (줄 167) | 정상 |
| 권한별 필터링 | ✅ (줄 881) | ✅ (줄 684) | 정상 |
| 청부액 자동 계산 | ✅ (줄 694) | ✅ (줄 97) | 부분 |
| 음성 파일 업로드 | ⚠️ HTML 없음 | ⚠️ (줄 204, 버그) | 미완성 |

### ❌ 미구현 기능

| 기능 | 필요성 | 난이도 | 우선순위 |
|------|--------|--------|---------|
| 음성 인식 (STT) | 높음 | 높음 | Phase 2 |
| 자동 분류 (AI) | 중간 | 높음 | Phase 2 |
| 데이터 내보내기 (PDF/Excel) | 중간 | 중간 | Phase 2 |
| 캘린더 뷰 | 낮음 | 중간 | Phase 2 |
| 통계/분석 대시보드 | 높음 | 중간 | Phase 2 |
| 오프라인 기능 | 낮음 | 높음 | Phase 3 |

### 🎨 UX/UI 문제점

#### 1. 이용자 선택 인터페이스 (줄 465-466)
```html
<!-- ❌ 문제: 긴 텍스트로 인해 드롭다운이 넘침 -->
<option value="1">홍길동 (2024. 1. 15) - 3등급 (일반)</option>

<!-- ✅ 개선: 검색 기능 추가 또는 모달 선택 UI -->
<input type="text" id="residentFilter" placeholder="이용자 검색...">
```

#### 2. 청부액 정보 표시 위치 (줄 492-509)
- 현재: 기록 저장 전에 표시
- 문제: 중복된 정보, 스크롤 필요
- 개선: 이용자 선택 후 드롭다운 옆에 표시

#### 3. 기록 목록 로딩 상태 없음
```javascript
// ❌ 현재: 로딩 표시 없음
const data = await response.json();
renderRecords(data);

// ✅ 개선
showLoadingSpinner();
const data = await response.json();
renderRecords(data);
hideLoadingSpinner();
```

#### 4. 에러 복구 불가
- 문제: 네트워크 오류 시 재시도 버튼 없음
- 개선: 에러 상태 유지 + 재시도 버튼

#### 5. 편집 모달 UX (줄 997-1005)
- 현재: 모달이 별도 구조
- 문제: 레코드 ID를 전역 변수(window.editingRecordId)에 저장
- 개선: data 속성 또는 클로저 사용

---

## 4️⃣ 경쟁사 비교 분석

### 주요 경쟁사의 음성기록 기능

#### 나이스케어 (NiceCare)
- ✅ 음성 녹음 → 자동 STT
- ✅ 키워드 자동 분류
- ✅ 클라우드 저장
- ✅ 검색 기능
- ❌ 청부액 자동 계산 (별도 모듈)

#### 돌봄마켓 (DolBom Market)
- ✅ 이미지 첨부
- ✅ 위치 기반 기록
- ✅ 시간 기록 자동
- ✅ 팀 공유
- ❌ 음성 기능

#### 케어네비 (CareNavi)
- ✅ 템플릿 기반 빠른 기록
- ✅ 일정 관리와 통합
- ✅ 가족 알림
- ❌ 음성 기능

#### 돌봄케어 (dolbomcare)
- ✅ 청부액 자동 계산 (차별화)
- ✅ 권한별 필터링
- ✅ 일괄 관리
- ❌ 음성 인식 (아직)
- ❌ 이미지 첨부

### 돌봄케어의 강점
1. **청부액 자동 계산**: 요양사가 청부액을 즉시 확인 가능 (매우 차별화)
2. **권한별 필터링**: 센터장/요양사 역할에 맞춘 UI
3. **드래프트 상태 관리**: 미제출 기록 자유롭게 수정 가능

### 돌봄케어의 약점
1. **음성 인식 없음**: 타이핑 부담 (경쟁사 대비 10-15분 더 소요)
2. **자동 분류 없음**: 서비스 유형을 수동으로 선택해야 함
3. **데이터 내보내기 없음**: 분석/보고용 데이터 추출 불가
4. **모바일 최적화 미흡**: 반응형 설계 있지만 터치 UX 개선 필요
5. **검색 기능 없음**: 과거 기록 찾기 어려움

---

## 5️⃣ 개선 및 추가 사항

### Phase 1 (MVP 안정화) - 2주

#### 1. 긴급 버그 수정 (1일)
```python
# ❌ 문제 1: SERVICE_TYPE_AMOUNTS 위치
# 줄 48 위로 이동
SERVICE_TYPE_AMOUNTS = {
    "basic_care": {1: 78875, 2: 69975, 3: 59650, 4: 54125, 5: 11750},
    "meal_service": {1: 39437, 2: 34987, 3: 29825, 4: 27062, 5: 5875},
    "medical_care": {1: 118312, 2: 104962, 3: 89475, 4: 81187, 5: 17625},
    "emergency": {1: 157750, 2: 139950, 3: 119300, 4: 108250, 5: 23500}
}

# ❌ 문제 2: 시간대 통일
# datetime.utcnow() → datetime.now() (한국 시간)
# 또는 전역으로 KST 타임존 설정
from datetime import datetime, timezone, timedelta
kst = timezone(timedelta(hours=9))
datetime.now(kst)

# ❌ 문제 3: XSS 취약점 (줄 906)
# JSON stringify + data 속성 사용
```

#### 2. 입력 검증 강화 (2일)
```python
# backend/app/api/records.py
from pydantic import Field

class CreateRecordRequest(BaseModel):
    caregiver_id: int = Field(..., gt=0)
    resident_id: int = Field(..., gt=0)
    service_type: str = Field(..., min_length=1, max_length=20)
    notes: str = Field(default="", max_length=1000)
    
# 검증 로직 추가
if not isinstance(caregiver_id, int) or caregiver_id <= 0:
    raise HTTPException(status_code=400, detail="Invalid caregiver_id")
```

#### 3. Authorization 헤더 추가 (1일)
```javascript
// voice_record.html: 모든 fetch 호출에 토큰 추가
const token = localStorage.getItem('access_token');
const response = await fetch(url, {
    headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
    }
});
```

#### 4. 에러 처리 개선 (2일)
```javascript
// 네트워크 에러 감지 + 재시도
async function fetchWithRetry(url, options, maxRetries = 3) {
    for (let i = 0; i < maxRetries; i++) {
        try {
            return await fetch(url, options);
        } catch (e) {
            if (i === maxRetries - 1) throw e;
            await new Promise(r => setTimeout(r, 1000 * Math.pow(2, i)));
        }
    }
}
```

#### 5. 일관성 테스트 추가 (3일)
```python
# backend/tests/test_records.py
def test_billing_consistency():
    """음성 기록 vs 일반 기록 청부액 계산 일치 확인"""
    # 1. POST /records/create → billing_amount
    # 2. POST /voice/create → billing_amount
    # → 같은 service_type이면 같은 금액이어야 함
```

### Phase 2 (기능 확장) - 4주

#### 1. 음성 인식 통합 (Whisper API)
```python
# backend/app/api/records.py
import openai

@router.post("/voice/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """음성 파일 STT 변환"""
    audio_content = await file.read()
    
    # Whisper API 호출
    transcript = openai.Audio.transcribe(
        model="whisper-1",
        file=audio_content,
        language="ko"
    )
    
    return {"text": transcript["text"]}
```

#### 2. 자동 분류 (주요 키워드 추출)
```python
# backend/app/services/classification.py
import re
from collections import Counter

CARE_KEYWORDS = {
    "basic_care": ["목욕", "배변", "이동"],
    "meal_service": ["식사", "간식", "물"],
    "medical_care": ["약", "주사", "혈압"]
}

def classify_service_type(transcription: str) -> str:
    """텍스트에서 서비스 유형 추론"""
    for service, keywords in CARE_KEYWORDS.items():
        if any(kw in transcription for kw in keywords):
            return service
    return "basic_care"  # 기본값
```

#### 3. 검색 기능
```python
# backend/app/api/records.py
@router.get("/search")
async def search_records(
    caregiver_id: int,
    q: str,  # 검색어
    db: Session = Depends(get_db)
):
    """메모/주민명으로 기록 검색"""
    records = db.query(DailyRecord).filter(
        DailyRecord.caregiver_id == caregiver_id,
        DailyRecord.notes.ilike(f"%{q}%")
    ).all()
    return {"records": records, "total": len(records)}
```

#### 4. 데이터 내보내기 (PDF)
```python
# backend/app/api/reports.py
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table

@router.get("/export/pdf")
async def export_records_pdf(
    caregiver_id: int,
    date_from: str,
    date_to: str,
    db: Session = Depends(get_db)
):
    """기록을 PDF로 내보내기"""
    records = db.query(DailyRecord).filter(
        DailyRecord.caregiver_id == caregiver_id,
        DailyRecord.recorded_date.between(date_from, date_to)
    ).all()
    
    # PDF 생성
    pdf_buffer = BytesIO()
    doc = SimpleDocTemplate(pdf_buffer, pagesize=A4)
    # ... 테이블 구성
    doc.build(elements)
    
    return StreamingResponse(pdf_buffer, media_type="application/pdf")
```

#### 5. 캘린더 뷰
```html
<!-- scratchpad/voice_record.html에 추가 -->
<div id="calendarView" style="display: none;">
    <div id="calendar"></div>
</div>

<!-- JavaScript: FullCalendar 라이브러리 사용 -->
<script src="https://cdn.jsdelivr.net/npm/fullcalendar@6.1.0"></script>
```

### Phase 3 (고급 기능) - 8주

#### 1. 통계 대시보드
- 월별 청부액 추이
- 서비스 유형별 비율
- 이용자별 방문 빈도

#### 2. 오프라인 모드 (SQLite + Sync)
```javascript
// IndexedDB 사용
const db = await idb.open('dolbomcare', 1, {
    upgrade(db) {
        db.createObjectStore('records', { keyPath: 'id' });
    }
});

// 오프라인 저장
await db.add('records', { id: 1, resident_id: 1, ... });

// 온라인 시 동기화
if (navigator.onLine) {
    const records = await db.getAll('records');
    for (const record of records) {
        await fetch('/api/records', { method: 'POST', body: JSON.stringify(record) });
    }
}
```

#### 3. AI 기반 요양 조언
```python
# backend/app/services/ai_assistant.py
import anthropic

def get_care_advice(resident_health: dict) -> str:
    """건강 상태를 분석하고 요양 조언 제공"""
    client = anthropic.Anthropic()
    message = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": f"이용자 건강 상태: {json.dumps(resident_health)}\n요양 조언을 한글로 제공해주세요."
            }
        ]
    )
    return message.content[0].text
```

---

## 6️⃣ 코드 위치 맵

### 프론트엔드 주요 함수

| 함수 | 줄 | 설명 |
|------|-----|------|
| `checkAuth()` | 637 | 인증 확인 |
| `loadResidents()` | 655 | 이용자 목록 로드 |
| `saveRecord()` | 720 | 기록 저장 |
| `switchRecordTab()` | 781 | 탭 전환 |
| `loadTodayRecords()` | 916 | 오늘 기록 로드 |
| `loadRecentRecords()` | 838 | 7일 기록 로드 |
| `loadAllRecords()` | 854 | 전체 기록 로드 |
| `renderRecords()` | 870 | 기록 UI 렌더링 |
| `deleteRecord()` | 1048 | 개별 삭제 |
| `deleteSelectedRecords()` | 974 | 일괄 삭제 |

### 백엔드 주요 엔드포인트

| 엔드포인트 | 줄 | 설명 |
|-----------|-----|------|
| `POST /create` | 75 | 기록 생성 + 청부 계산 |
| `POST /batch-delete` | 167 | 일괄 삭제 |
| `POST /upload-audio` | 204 | 음성 파일 업로드 |
| `GET /recent` | 283 | 7일 기록 |
| `GET /all` | 369 | 전체 기록 |
| `GET /today` | 442 | 오늘 기록 |
| `GET /{record_id}` | 574 | 상세 조회 |
| `PATCH /{record_id}` | 613 | 기록 수정 |
| `DELETE /{record_id}` | 665 | 기록 삭제 |

---

## 7️⃣ 테스트 체크리스트

### 프론트엔드 테스트
- [ ] 이용자 선택 → 청부액 자동 계산 표시
- [ ] 메모 작성 후 저장 → 성공 토스트
- [ ] 오늘/7일/전체 탭 전환 → 데이터 새로고침
- [ ] 기록 편집 → PATCH 요청 + UI 업데이트
- [ ] 개별 삭제 → DELETE 요청
- [ ] 일괄 삭제 → POST batch-delete
- [ ] 로그아웃 → login.html 이동
- [ ] 권한 없는 기록 삭제 시도 → 에러 표시

### 백엔드 테스트
- [ ] POST /create: 청부액 계산 정확성 (service_type별)
- [ ] GET /today: 00:00~23:59 범위만 조회
- [ ] GET /recent: 정확히 N일 기록
- [ ] DELETE: 권한 검증 + 관련 BillingRecord 함께 삭제
- [ ] 동시 삭제: Race condition 없음
- [ ] 잘못된 resident_id: 404 응답

---

## 결론

### 🎯 현재 상태 (MVP 수준)
- ✅ 기본 기능 구현됨
- ⚠️ 여러 중간 수준 버그 존재
- ❌ 음성 인식, 자동 분류 없음

### 📋 다음 단계
1. **즉시** (1주): 버그 수정 + 입력 검증
2. **단기** (2주): 에러 처리 개선 + 테스트
3. **중기** (4주): 음성 인식 + 자동 분류
4. **장기** (8주): 통계 대시보드 + 오프라인

### 💡 차별화 포인트
- 청부액 자동 계산이 가장 큰 경쟁 우위
- 음성 인식을 추가하면 타이핑 부담 대폭 감소
- 데이터 내보내기로 행정 업무 자동화 가능
