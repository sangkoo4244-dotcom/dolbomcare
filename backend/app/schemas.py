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
    age: int
    health_status: str

class ResidentCreate(ResidentBase):
    center_id: int
    guardian_id: Optional[int] = None

class ResidentResponse(ResidentBase):
    id: int
    admission_date: datetime
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
