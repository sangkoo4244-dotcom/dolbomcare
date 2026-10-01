---
name: voice_billing_auto_link_complete
description: 2026-10-01 음성기록 ↔ 청부 자동 연결 완성
metadata:
  type: project
---

## ✅ 음성기록 ↔ 청부 자동 연결 완성

### 🎯 구현 내용

**1️⃣ Backend 모델 수정**
- VoiceRecord에 `service_type`, `billing_record_id` 필드 추가
- VoiceRecord 생성 시 자동으로 BillingRecord 생성

**2️⃣ API 엔드포인트: POST /voice/create**
```
요청:
{
  caregiver_id: 2,
  resident_id: 1,
  service_type: "basic_care",
  transcription: "오늘 목욕 지원..."
}

응답:
{
  status: "success",
  voice_record_id: 5,
  billing_record_id: 12,
  amount: 78875
}
```

**3️⃣ service_type별 청부액 (1등급 기준)**
| 서비스유형 | 청부액 |
|-----------|-------|
| basic_care (기본요양) | ₩78,875 |
| meal_service (식사지원) | ₩39,437 |
| medical_care (의료) | ₩118,312 |
| emergency (응급) | ₩157,750 |

**4️⃣ 청부 상태 정확화**
| 상태 | 필드 | 의미 | 표시 |
|------|------|------|------|
| draft | status | 제출 대기 | 📋 제출대기 |
| pending | approval_status | 승인 대기 | ⏳ 승인대기 |
| approved | approval_status | 승인됨 | ✅ 승인됨 |
| rejected | approval_status | 거절됨 | ❌ 거절됨 |
| submitted | status | 제출됨 | 📤 제출됨 |
| paid | status | 완료 | ✔️ 완료 |

---

## 📋 업무 흐름

```
1. 요양사 음성기록 생성
   ↓
2. VoiceRecord 저장 + service_type 입력
   ↓
3. 자동으로 BillingRecord 생성 (draft 상태)
   ↓
4. 등급별 청부액 자동 계산
   ↓
5. 센터장이 승인 (approval_status = pending)
   ↓
6. 승인 후 건강보험공단 청구 제출
   ↓
7. 완료/환급 (status = paid)
```

---

## 🔧 기술 스택

**Backend:**
- FastAPI (Python)
- POST `/api/v1/records/voice/create` 엔드포인트
- SQLAlchemy ORM

**Frontend:**
- caregiver_billing.html
- 상태별 라벨 표시 (emoji + 한글)

**Database:**
- VoiceRecord ↔ BillingRecord 양방향 링크

---

## ✅ 완성된 커밋

| 커밋 | 설명 |
|------|------|
| e5b4074 | feat: Auto-link VoiceRecord → BillingRecord on creation |
| 97fc05d | fix: Fix encoding issue in records.py |
| 20ba550 | fix: Change Korean docstring to English |
| 2ece8e3 | fix: Show approval_status or status for billing records |
| aa02620 | fix: Change draft status label from '작성 중' to '초안' |
| 5917bd3 | fix: Change draft status label to '제출대기' |

---

## 🎓 학습 내용

### 상태 설계 원칙
- **approval_status**: 승인 프로세스 (센터장 승인 여부)
- **status**: 청부 진행 상황 (제출 여부)
- 두 상태를 명확히 분리해야 혼동이 없음

### 용어 정확성
- "초안" ❌ → "제출대기" ✅
- "작성 중" ❌ → "제출대기" ✅
- 비즈니스 컨텍스트에 맞는 용어 선택 중요

---

## 🚀 다음 단계

1. **API 테스트** - POST /voice/create 실제 호출 확인
2. **모바일 통합** - React Native에서 이 API 호출
3. **대시보드 개선** - 음성기록 + 청부 통합 뷰
4. **Phase 2** - 규칙 기반 건강상태 제안 추가
