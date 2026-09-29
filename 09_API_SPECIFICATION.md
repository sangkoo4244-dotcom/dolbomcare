# dolbomcare API 명세서

**Base URL:** `https://api.dolbomcare.com/v1`  
**인증:** JWT Bearer Token  
**응답 형식:** JSON

---

## 인증 (Authentication)

### POST /auth/register
사용자 회원가입

**Request:**
```json
{
  "email": "user@example.com",
  "password": "SecurePassword123!",
  "name": "김요양사",
  "role": "caregiver" // or "guardian"
}
```

**Response (201):**
```json
{
  "id": 1,
  "email": "user@example.com",
  "name": "김요양사",
  "role": "caregiver",
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer"
}
```

---

### POST /auth/login
사용자 로그인

**Request:**
```json
{
  "email": "user@example.com",
  "password": "SecurePassword123!"
}
```

**Response (200):**
```json
{
  "id": 1,
  "email": "user@example.com",
  "name": "김요양사",
  "role": "caregiver",
  "center_id": 1,
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

**Error (401):**
```json
{
  "detail": "Invalid email or password"
}
```

---

### POST /auth/refresh
토큰 갱신

**Header:**
```
Authorization: Bearer <refresh_token>
```

**Response (200):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

---

## 센터 (Centers)

### GET /centers/{center_id}
센터 정보 조회

**Header:**
```
Authorization: Bearer <access_token>
```

**Response (200):**
```json
{
  "id": 1,
  "name": "테스트 요양원",
  "address": "서울시 강남구",
  "phone": "02-1234-5678",
  "owner_id": 1,
  "capacity": 50,
  "current_residents": 45,
  "created_at": "2024-01-01T10:00:00Z"
}
```

---

### GET /centers/{center_id}/residents
센터의 입소자 목록

**Query Parameters:**
```
?skip=0&limit=50&is_active=true
```

**Response (200):**
```json
{
  "total": 45,
  "items": [
    {
      "id": 1,
      "name": "김할머니",
      "birth_date": "1940-01-01",
      "gender": "F",
      "admitted_date": "2023-06-01",
      "health_status": "stable"
    }
  ]
}
```

---

## 입소자 (Residents)

### GET /residents/{resident_id}
입소자 상세 정보

**Response (200):**
```json
{
  "id": 1,
  "name": "김할머니",
  "birth_date": "1940-01-01",
  "gender": "F",
  "phone": "010-1234-5678",
  "address": "서울시 강남구",
  "medical_info": {
    "diseases": ["고혈압", "당뇨병"],
    "allergies": ["페니실린"],
    "medications": ["고혈압약", "소화제"]
  },
  "emergency_contact": "김손자",
  "emergency_phone": "010-9876-5432",
  "admitted_date": "2023-06-01",
  "guardians": [
    {
      "id": 1,
      "user_id": 2,
      "name": "김손자",
      "relation": "자녀",
      "email": "grandson@example.com"
    }
  ]
}
```

---

### GET /residents/{resident_id}/records
입소자의 기록 조회

**Query Parameters:**
```
?start_date=2024-01-01&end_date=2024-01-31&record_type=meal&skip=0&limit=50
```

**Response (200):**
```json
{
  "total": 30,
  "items": [
    {
      "id": 1,
      "resident_id": 1,
      "caregiver_id": 5,
      "caregiver_name": "이요양사",
      "record_type": "meal",
      "content": {
        "time": "08:00",
        "type": "breakfast",
        "amount": "80%"
      },
      "status": "completed",
      "recorded_time": "2024-01-15T08:30:00Z",
      "created_at": "2024-01-15T08:31:00Z"
    }
  ]
}
```

---

## 기록 (Records)

### POST /records
새 기록 생성

**Request:**
```json
{
  "resident_id": 1,
  "record_type": "meal",
  "content": {
    "time": "08:00",
    "type": "breakfast",
    "amount": "80%",
    "notes": "밥 조금 적게"
  },
  "recorded_time": "2024-01-15T08:00:00Z"
}
```

**Response (201):**
```json
{
  "id": 1,
  "resident_id": 1,
  "caregiver_id": 5,
  "record_type": "meal",
  "content": {
    "time": "08:00",
    "type": "breakfast",
    "amount": "80%",
    "notes": "밥 조금 적게"
  },
  "status": "completed",
  "recorded_time": "2024-01-15T08:00:00Z",
  "created_at": "2024-01-15T08:31:00Z"
}
```

---

### PUT /records/{record_id}
기록 수정

**Request:**
```json
{
  "content": {
    "time": "08:00",
    "type": "breakfast",
    "amount": "70%",
    "notes": "밥 더 적게, 국 많이"
  },
  "status": "completed"
}
```

**Response (200):**
```json
{
  "id": 1,
  "resident_id": 1,
  "record_type": "meal",
  "content": {
    "time": "08:00",
    "type": "breakfast",
    "amount": "70%",
    "notes": "밥 더 적게, 국 많이"
  },
  "status": "completed",
  "updated_at": "2024-01-15T09:00:00Z"
}
```

---

### DELETE /records/{record_id}
기록 삭제

**Response (204):**
```
No Content
```

---

### POST /records/bulk
일괄 기록 생성

**Request:**
```json
{
  "records": [
    {
      "resident_id": 1,
      "record_type": "meal",
      "content": {...},
      "recorded_time": "2024-01-15T08:00:00Z"
    },
    {
      "resident_id": 1,
      "record_type": "medicine",
      "content": {...},
      "recorded_time": "2024-01-15T09:00:00Z"
    }
  ]
}
```

**Response (201):**
```json
{
  "created": 2,
  "failed": 0,
  "records": [...]
}
```

---

## 일정 (Schedules)

### GET /residents/{resident_id}/schedules
입소자의 일정 조회

**Response (200):**
```json
{
  "meals": [
    {
      "id": 1,
      "meal_type": "breakfast",
      "scheduled_time": "08:00",
      "notes": "밥 조금 적게"
    },
    {
      "id": 2,
      "meal_type": "lunch",
      "scheduled_time": "12:00"
    }
  ],
  "medicines": [
    {
      "id": 1,
      "medicine_name": "고혈압약",
      "dosage": "1정",
      "frequency": "1일 1회",
      "scheduled_time": "09:00",
      "start_date": "2024-01-01",
      "end_date": "2024-12-31"
    }
  ]
}
```

---

### POST /residents/{resident_id}/schedules/meals
식사 시간표 추가

**Request:**
```json
{
  "meal_type": "breakfast",
  "scheduled_time": "08:00",
  "notes": "밥 조금 적게"
}
```

---

### POST /residents/{resident_id}/schedules/medicines
약물 시간표 추가

**Request:**
```json
{
  "medicine_name": "고혈압약",
  "dosage": "1정",
  "frequency": "1일 1회",
  "scheduled_time": "09:00",
  "start_date": "2024-01-01",
  "end_date": "2024-12-31"
}
```

---

## 통계 (Statistics)

### GET /centers/{center_id}/statistics
센터 통계

**Query Parameters:**
```
?start_date=2024-01-01&end_date=2024-01-31
```

**Response (200):**
```json
{
  "period": {
    "start_date": "2024-01-01",
    "end_date": "2024-01-31"
  },
  "total_residents": 45,
  "total_records": 1350,
  "average_records_per_resident": 30,
  "records_by_type": {
    "meal": 450,
    "medicine": 450,
    "activity": 300,
    "memo": 150
  },
  "caregiver_performance": [
    {
      "caregiver_id": 5,
      "caregiver_name": "이요양사",
      "records_count": 150,
      "attendance_rate": "95%"
    }
  ]
}
```

---

### GET /residents/{resident_id}/statistics
입소자 통계

**Response (200):**
```json
{
  "resident_id": 1,
  "name": "김할머니",
  "period": "2024-01",
  "meals_completion_rate": "92%",
  "medicines_completion_rate": "98%",
  "activity_frequency": "5 times per week",
  "mood_trend": "improving"
}
```

---

## 리포트 (Reports)

### GET /centers/{center_id}/reports/monthly
월간 리포트

**Query Parameters:**
```
?year=2024&month=1
```

**Response (200):**
```json
{
  "id": 1,
  "center_id": 1,
  "report_month": "2024-01",
  "total_residents": 45,
  "total_records": 1350,
  "average_records_per_resident": 30,
  "caregiver_attendance_rate": "94%",
  "generated_at": "2024-02-01T10:00:00Z",
  "pdf_url": "https://s3.amazonaws.com/reports/2024-01-report.pdf"
}
```

---

### POST /centers/{center_id}/reports/export
리포트 내보내기

**Request:**
```json
{
  "format": "pdf", // or "csv"
  "start_date": "2024-01-01",
  "end_date": "2024-01-31"
}
```

**Response (200):**
```json
{
  "download_url": "https://s3.amazonaws.com/exports/report_2024_01.pdf",
  "expires_in": 3600
}
```

---

## 알림 (Alerts)

### GET /users/me/alerts
내 알림 조회

**Query Parameters:**
```
?is_read=false&skip=0&limit=20
```

**Response (200):**
```json
{
  "total": 5,
  "unread": 3,
  "items": [
    {
      "id": 1,
      "resident_id": 1,
      "resident_name": "김할머니",
      "alert_type": "record_pending",
      "title": "점심 식사 기록 미입력",
      "message": "김할머니의 점심 식사 기록이 아직 입력되지 않았습니다.",
      "priority": "medium",
      "is_read": false,
      "created_at": "2024-01-15T12:30:00Z"
    }
  ]
}
```

---

### PUT /alerts/{alert_id}/mark-as-read
알림 읽음 표시

**Response (200):**
```json
{
  "id": 1,
  "is_read": true,
  "read_at": "2024-01-15T12:35:00Z"
}
```

---

### POST /alerts/mark-all-read
모든 알림 읽음 표시

**Response (200):**
```json
{
  "marked": 3
}
```

---

## 요양사 (Caregivers)

### GET /caregivers
요양사 목록 (센터장만)

**Response (200):**
```json
{
  "total": 10,
  "items": [
    {
      "id": 5,
      "name": "이요양사",
      "email": "caregiver@example.com",
      "phone": "010-1234-5678",
      "hired_date": "2023-06-01",
      "is_active": true,
      "current_assignments": 5,
      "this_month_records": 150
    }
  ]
}
```

---

### GET /caregivers/{caregiver_id}/performance
요양사 성과

**Query Parameters:**
```
?start_date=2024-01-01&end_date=2024-01-31
```

**Response (200):**
```json
{
  "caregiver_id": 5,
  "name": "이요양사",
  "period": "2024-01",
  "total_records": 150,
  "attendance_rate": "95%",
  "daily_performance": [
    {
      "date": "2024-01-01",
      "records": 5,
      "status": "present",
      "time_in": "08:00"
    }
  ]
}
```

---

## 보호자 (Guardians)

### GET /residents/{resident_id}/guardians
입소자의 보호자 목록

**Response (200):**
```json
{
  "total": 2,
  "items": [
    {
      "id": 1,
      "user_id": 2,
      "name": "김손자",
      "email": "grandson@example.com",
      "phone": "010-9876-5432",
      "relation": "자녀",
      "created_at": "2023-06-01T10:00:00Z"
    }
  ]
}
```

---

### POST /residents/{resident_id}/guardians
보호자 추가

**Request:**
```json
{
  "user_id": 2,
  "relation": "자녀"
}
```

---

### DELETE /residents/{resident_id}/guardians/{guardian_id}
보호자 제거

**Response (204):**
```
No Content
```

---

## 에러 응답

**400 Bad Request:**
```json
{
  "detail": "Invalid input",
  "errors": [
    {
      "field": "email",
      "message": "Invalid email format"
    }
  ]
}
```

**401 Unauthorized:**
```json
{
  "detail": "Not authenticated"
}
```

**403 Forbidden:**
```json
{
  "detail": "Not enough permissions"
}
```

**404 Not Found:**
```json
{
  "detail": "Resource not found"
}
```

**500 Internal Server Error:**
```json
{
  "detail": "Internal server error",
  "request_id": "abc123"
}
```

---

## 페이지네이션

모든 목록 API는 페이지네이션을 지원합니다:

**Query Parameters:**
```
?skip=0&limit=50
```

**Response Meta:**
```json
{
  "total": 100,
  "skip": 0,
  "limit": 50,
  "items": [...]
}
```

---

## 필터링 & 검색

**예시 쿼리:**
```
GET /centers/1/residents?name=김&gender=F&admitted_after=2023-06-01
GET /records?record_type=meal&status=completed&start_date=2024-01-01
GET /alerts?priority=high&is_read=false
```

---

## Rate Limiting

```
Rate Limit: 100 requests per minute per IP
Header: X-RateLimit-Remaining: 95
Header: X-RateLimit-Reset: 1234567890
```

---

## 다음 단계

- [ ] FastAPI 라우터 구현
- [ ] Pydantic 스키마 정의
- [ ] 각 엔드포인트 테스트
- [ ] Swagger 문서 자동 생성
