from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional, List

class UserBase(BaseModel):
    email: EmailStr
    full_name: str
    role: str

class UserCreate(UserBase):
    password: str

class UserResponse(UserBase):
    id: int
    center_id: Optional[int] = None
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse

class CenterBase(BaseModel):
    name: str
    address: str
    phone: str
    residents_count: int
    caregivers_count: int

class CenterCreate(CenterBase):
    manager_id: int

class CenterResponse(CenterBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True

class ResidentBase(BaseModel):
    name: str
    birth_date: Optional[str] = None  # YYYY-MM-DD
    age: int
    health_status: str

class ResidentCreate(ResidentBase):
    center_id: int
    guardian_id: Optional[int] = None
    primary_caregiver_id: Optional[int] = None
    care_grade: Optional[int] = 1  # 1~5등급, None=인지지원등급
    client_type: str = "일반"  # '일반', '차상위계층', '기초생활보장', '의료급여'
    gender: Optional[str] = None
    address: Optional[str] = None
    recognition_number: Optional[str] = None
    recognition_start: Optional[str] = None  # YYYY-MM-DD
    recognition_end: Optional[str] = None  # YYYY-MM-DD
    guardian_name: Optional[str] = None
    guardian_phone: Optional[str] = None

class ResidentResponse(ResidentBase):
    id: int
    birth_date: Optional[str] = None
    admission_date: datetime
    care_grade: Optional[int] = None
    client_type: str
    created_at: datetime

    class Config:
        from_attributes = True

class DailyRecordBase(BaseModel):
    recorded_date: datetime
    morning_care: bool
    meal_intake: str
    medicine_given: bool
    notes: Optional[str] = None

class DailyRecordCreate(DailyRecordBase):
    resident_id: int
    caregiver_id: int

class DailyRecordResponse(DailyRecordBase):
    id: int
    audio_file_url: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True

class HealthMetricBase(BaseModel):
    blood_pressure_sys: Optional[int] = None
    blood_pressure_dia: Optional[int] = None
    heart_rate: Optional[int] = None
    temperature: Optional[float] = None
    oxygen_saturation: Optional[float] = None

class HealthMetricCreate(HealthMetricBase):
    resident_id: int
    recorded_at: datetime

class HealthMetricResponse(HealthMetricBase):
    id: int
    status: str
    created_at: datetime

    class Config:
        from_attributes = True

class DashboardSummary(BaseModel):
    total_residents: int
    total_caregivers: int
    healthy_residents: int
    warning_residents: int
    critical_residents: int
    today_records_count: int

class CaregiverStats(BaseModel):
    caregiver_id: int
    name: str
    attendance_rate: float
    records_count: int
    last_record_date: Optional[datetime]

class BillingRecordCreate(BaseModel):
    caregiver_id: int
    resident_id: int
    recorded_date: datetime
    service_type: str  # 'basic_care', 'meal_service', 'medical_care', 'emergency'
    notes: Optional[str] = None

class BillingRecordResponse(BaseModel):
    id: int
    caregiver_id: int
    resident_id: int
    service_type: str
    amount: int
    status: str  # 'pending', 'submitted', 'paid'
    recorded_date: datetime
    created_at: datetime

    class Config:
        from_attributes = True

class BillingMonthlySummary(BaseModel):
    year_month: str
    total_records: int
    total_amount: int
    submitted_count: int
    paid_count: int
    pending_count: int
    approved_count: int = 0
    approved_amount: int = 0
    estimated_savings: int
