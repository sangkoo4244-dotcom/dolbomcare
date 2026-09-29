# dolbomcare 데이터베이스 스키마

## 테이블 설계

### 1. Users (사용자)

```sql
CREATE TABLE users (
  id SERIAL PRIMARY KEY,
  email VARCHAR(255) UNIQUE NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  name VARCHAR(100) NOT NULL,
  role VARCHAR(50) NOT NULL, -- 'admin', 'caregiver', 'guardian'
  center_id INTEGER,
  is_active BOOLEAN DEFAULT true,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  
  FOREIGN KEY (center_id) REFERENCES centers(id)
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_center_id ON users(center_id);
```

**컬럼 설명:**
- `id`: 고유 식별자 (PK)
- `email`: 로그인 이메일 (유니크)
- `password_hash`: bcrypt 해시된 비밀번호
- `role`: 사용자 역할 (관리자/요양사/보호자)
- `center_id`: 소속 센터 (보호자는 NULL)
- `is_active`: 활성 여부 (소프트 삭제)

---

### 2. Centers (요양원/센터)

```sql
CREATE TABLE centers (
  id SERIAL PRIMARY KEY,
  name VARCHAR(200) NOT NULL,
  address VARCHAR(300),
  phone VARCHAR(20),
  owner_id INTEGER NOT NULL,
  capacity INTEGER,
  is_active BOOLEAN DEFAULT true,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  
  FOREIGN KEY (owner_id) REFERENCES users(id)
);

CREATE INDEX idx_centers_owner_id ON centers(owner_id);
```

---

### 3. Residents (입소자)

```sql
CREATE TABLE residents (
  id SERIAL PRIMARY KEY,
  center_id INTEGER NOT NULL,
  name VARCHAR(100) NOT NULL,
  birth_date DATE,
  gender VARCHAR(10), -- 'M', 'F'
  phone VARCHAR(20),
  address VARCHAR(300),
  medical_info TEXT, -- 질병 정보 (JSON 형식 권장)
  emergency_contact VARCHAR(100),
  emergency_phone VARCHAR(20),
  is_active BOOLEAN DEFAULT true,
  admitted_date DATE,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  
  FOREIGN KEY (center_id) REFERENCES centers(id)
);

CREATE INDEX idx_residents_center_id ON residents(center_id);
CREATE INDEX idx_residents_name ON residents(name);
```

---

### 4. Guardians (보호자)

```sql
CREATE TABLE guardians (
  id SERIAL PRIMARY KEY,
  resident_id INTEGER NOT NULL,
  user_id INTEGER NOT NULL,
  relation VARCHAR(50), -- '자녀', '배우자', '친구' 등
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  
  FOREIGN KEY (resident_id) REFERENCES residents(id) ON DELETE CASCADE,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX idx_guardians_resident_id ON guardians(resident_id);
CREATE INDEX idx_guardians_user_id ON guardians(user_id);
```

---

### 5. Records (일일 기록)

```sql
CREATE TABLE records (
  id SERIAL PRIMARY KEY,
  resident_id INTEGER NOT NULL,
  caregiver_id INTEGER NOT NULL,
  record_type VARCHAR(50) NOT NULL, -- 'meal', 'medicine', 'activity', 'memo'
  content TEXT,
  status VARCHAR(50), -- 'completed', 'pending', 'cancelled'
  recorded_time TIMESTAMP NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  
  FOREIGN KEY (resident_id) REFERENCES residents(id),
  FOREIGN KEY (caregiver_id) REFERENCES users(id)
);

CREATE INDEX idx_records_resident_id ON records(resident_id);
CREATE INDEX idx_records_caregiver_id ON records(caregiver_id);
CREATE INDEX idx_records_recorded_time ON records(recorded_time);
CREATE INDEX idx_records_record_type ON records(record_type);
```

**레코드 타입별 예시:**

**Meal (식사)**
```json
{
  "type": "meal",
  "content": {
    "time": "08:00",
    "type": "breakfast",
    "amount": "80%",
    "notes": "밥 조금 적게, 국 많이"
  }
}
```

**Medicine (약물)**
```json
{
  "type": "medicine",
  "content": {
    "time": "09:00",
    "medicines": ["고혈압약", "소화제"],
    "taken": true,
    "notes": "따뜻한 물과 함께"
  }
}
```

**Activity (활동)**
```json
{
  "type": "activity",
  "content": {
    "time": "14:00",
    "activity": "산책",
    "duration": "30분",
    "mood": "좋음",
    "notes": "날씨 좋아서 기분 좋았음"
  }
}
```

---

### 6. MealSchedules (식사 시간표)

```sql
CREATE TABLE meal_schedules (
  id SERIAL PRIMARY KEY,
  resident_id INTEGER NOT NULL,
  meal_type VARCHAR(50), -- 'breakfast', 'lunch', 'dinner', 'snack'
  scheduled_time TIME NOT NULL,
  notes TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  
  FOREIGN KEY (resident_id) REFERENCES residents(id) ON DELETE CASCADE,
  UNIQUE(resident_id, meal_type)
);
```

---

### 7. MedicineSchedules (약물 시간표)

```sql
CREATE TABLE medicine_schedules (
  id SERIAL PRIMARY KEY,
  resident_id INTEGER NOT NULL,
  medicine_name VARCHAR(100) NOT NULL,
  dosage VARCHAR(100),
  frequency VARCHAR(100), -- '1일 3회', '1일 1회' 등
  scheduled_time TIME NOT NULL,
  start_date DATE,
  end_date DATE,
  notes TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  
  FOREIGN KEY (resident_id) REFERENCES residents(id) ON DELETE CASCADE
);

CREATE INDEX idx_medicine_schedules_resident_id ON medicine_schedules(resident_id);
```

---

### 8. Alerts (알림)

```sql
CREATE TABLE alerts (
  id SERIAL PRIMARY KEY,
  resident_id INTEGER NOT NULL,
  guardian_id INTEGER NOT NULL,
  alert_type VARCHAR(50), -- 'record_pending', 'health_change', 'schedule_reminder', 'custom'
  title VARCHAR(200),
  message TEXT,
  priority VARCHAR(20), -- 'low', 'medium', 'high'
  is_read BOOLEAN DEFAULT false,
  read_at TIMESTAMP,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  
  FOREIGN KEY (resident_id) REFERENCES residents(id),
  FOREIGN KEY (guardian_id) REFERENCES users(id)
);

CREATE INDEX idx_alerts_guardian_id ON alerts(guardian_id);
CREATE INDEX idx_alerts_resident_id ON alerts(resident_id);
CREATE INDEX idx_alerts_is_read ON alerts(is_read);
```

---

### 9. CaregiverPerformance (요양사 성과)

```sql
CREATE TABLE caregiver_performance (
  id SERIAL PRIMARY KEY,
  caregiver_id INTEGER NOT NULL,
  center_id INTEGER NOT NULL,
  performance_date DATE NOT NULL,
  total_records INTEGER, -- 기록 수
  attendance_status VARCHAR(50), -- 'present', 'absent', 'late'
  attendance_time TIMESTAMP,
  notes TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  
  FOREIGN KEY (caregiver_id) REFERENCES users(id),
  FOREIGN KEY (center_id) REFERENCES centers(id),
  UNIQUE(caregiver_id, performance_date)
);

CREATE INDEX idx_performance_caregiver_id ON caregiver_performance(caregiver_id);
CREATE INDEX idx_performance_performance_date ON caregiver_performance(performance_date);
```

---

### 10. MonthlyReports (월간 리포트)

```sql
CREATE TABLE monthly_reports (
  id SERIAL PRIMARY KEY,
  center_id INTEGER NOT NULL,
  report_month DATE NOT NULL, -- '2024-01-01'
  total_residents INTEGER,
  total_records INTEGER,
  average_records_per_resident DECIMAL(5, 2),
  caregiver_attendance_rate DECIMAL(5, 2),
  generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  pdf_url VARCHAR(500),
  
  FOREIGN KEY (center_id) REFERENCES centers(id),
  UNIQUE(center_id, report_month)
);
```

---

### 11. AuditLog (감시/감사 로그)

```sql
CREATE TABLE audit_log (
  id SERIAL PRIMARY KEY,
  user_id INTEGER,
  action VARCHAR(100), -- 'create', 'update', 'delete', 'login', 'logout'
  table_name VARCHAR(100),
  record_id INTEGER,
  old_values JSONB,
  new_values JSONB,
  ip_address VARCHAR(50),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  
  FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX idx_audit_log_user_id ON audit_log(user_id);
CREATE INDEX idx_audit_log_created_at ON audit_log(created_at);
```

---

## 데이터 관계도

```
Users (1) ──┬── (N) Centers (요양원 운영자)
            ├── (N) Records (요양사)
            └── (N) CaregiverPerformance

Centers (1) ──┬── (N) Residents
              └── (N) CaregiverPerformance

Residents (1) ──┬── (N) Records
                ├── (N) Guardians
                ├── (N) MealSchedules
                ├── (N) MedicineSchedules
                └── (N) Alerts

Guardians (N) ──┬── (1) Residents
                └── (1) Users (보호자)

Records (N) ──┬── (1) Residents
              └── (1) Users (요양사)

Alerts (N) ──┬── (1) Residents
             └── (1) Users (보호자)
```

---

## 마이그레이션 전략 (Alembic)

### 초기 마이그레이션 생성

```bash
# Alembic 초기화
alembic init alembic

# 모델 정의 후 마이그레이션 생성
alembic revision --autogenerate -m "Create initial schema"

# 마이그레이션 적용
alembic upgrade head
```

### 버전 관리

```
alembic/versions/
├── 001_create_initial_schema.py
├── 002_add_meal_schedules.py
├── 003_add_audit_log.py
└── 004_add_indexes.py
```

---

## 인덱싱 전략

**꼭 필요한 인덱스:**
- `users.email` - 로그인 성능
- `residents.center_id` - 센터별 조회
- `records.resident_id` - 입소자별 기록 조회
- `records.recorded_time` - 시간 범위 검색
- `alerts.guardian_id` - 보호자 알림 조회
- `caregiver_performance.performance_date` - 일일 성과 조회

**선택적 인덱스 (필요시):**
- `records.record_type` - 기록 타입별 집계
- `audit_log.created_at` - 감사 로그 시간 조회

---

## 백업 및 복구 전략

### Daily Backup
```bash
# AWS RDS 자동 백업 (7일)
# 또는
pg_dump -U postgres -d dolbomcare -F c > backup_$(date +%Y%m%d).dump

# 복구
pg_restore -U postgres -d dolbomcare backup_20240101.dump
```

### Weekly Snapshot
- AWS RDS 수동 스냅샷 (매주 일요일)
- S3에 백업 복사

---

## 초기 데이터

### 테스트 데이터 (Seeding)

```python
# seeds.py
def seed_database():
    # 테스트 센터
    center = Center(
        name="테스트 요양원",
        address="서울시 강남구",
        phone="02-1234-5678",
        capacity=50
    )
    
    # 테스트 입소자
    resident = Resident(
        center_id=center.id,
        name="김할머니",
        birth_date="1940-01-01",
        medical_info="고혈압, 당뇨병"
    )
    
    # 테스트 요양사
    caregiver = User(
        email="caregiver@test.com",
        password_hash=hash_password("password"),
        name="이요양사",
        role="caregiver",
        center_id=center.id
    )
    
    db.session.add_all([center, resident, caregiver])
    db.session.commit()
```

**실행:**
```bash
python -c "from seeds import seed_database; seed_database()"
```

---

## 성능 고려사항

### 쿼리 최적화
```sql
-- ❌ 느린 쿼리 (N+1 문제)
SELECT * FROM residents WHERE center_id = 1;
-- 각 resident의 records를 별도로 조회

-- ✅ 최적화된 쿼리 (JOIN)
SELECT r.*, COUNT(rec.id) as record_count
FROM residents r
LEFT JOIN records rec ON r.id = rec.resident_id
WHERE r.center_id = 1
GROUP BY r.id;
```

### 캐싱 전략
```
Redis 캐시:
- user:{user_id} - 사용자 정보
- residents:{center_id} - 센터 입소자 목록
- performance:{date} - 일일 성과 통계
```

### 파티셔닝 (대규모 데이터)
```sql
-- records 테이블 월별 파티셔닝 (예: 1년 후)
CREATE TABLE records_2024_01 PARTITION OF records
  FOR VALUES FROM ('2024-01-01') TO ('2024-02-01');
```

---

## 보안

### 민감한 데이터 암호화
```python
# password_hash: bcrypt (자동)
# 의료 정보: AES-256 암호화 (필요시)

from cryptography.fernet import Fernet

cipher = Fernet(settings.ENCRYPTION_KEY)
encrypted_medical_info = cipher.encrypt(medical_info.encode())
```

### 권한 관리
```python
# 요양사: 자신의 센터 데이터만
# 센터장: 자신의 센터 모든 데이터
# 보호자: 자신의 부모님 데이터만
```

---

## 다음 단계

- [ ] SQLAlchemy 모델 구현
- [ ] Alembic 마이그레이션 작성
- [ ] 초기 데이터 시딩
- [ ] 데이터베이스 연결 테스트
