from sqlalchemy import Column, Integer, String, DateTime, Float, Boolean, Text, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    full_name = Column(String)
    role = Column(String)  # 'center_manager', 'caregiver', 'guardian'
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Center(Base):
    __tablename__ = "centers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    address = Column(String)
    phone = Column(String)
    manager_id = Column(Integer, ForeignKey("users.id"))
    residents_count = Column(Integer)
    caregivers_count = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)

class Resident(Base):
    __tablename__ = "residents"

    id = Column(Integer, primary_key=True, index=True)
    center_id = Column(Integer, ForeignKey("centers.id"))
    name = Column(String, index=True)
    age = Column(Integer)
    admission_date = Column(DateTime)
    health_status = Column(String)  # 'stable', 'warning', 'critical'
    guardian_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)

class DailyRecord(Base):
    __tablename__ = "daily_records"

    id = Column(Integer, primary_key=True, index=True)
    resident_id = Column(Integer, ForeignKey("residents.id"))
    caregiver_id = Column(Integer, ForeignKey("users.id"))
    recorded_date = Column(DateTime, index=True)
    morning_care = Column(Boolean, default=False)
    meal_intake = Column(String)  # 'full', 'partial', 'none'
    medicine_given = Column(Boolean, default=False)
    notes = Column(Text)
    audio_file_url = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class HealthMetric(Base):
    __tablename__ = "health_metrics"

    id = Column(Integer, primary_key=True, index=True)
    resident_id = Column(Integer, ForeignKey("residents.id"))
    recorded_at = Column(DateTime, index=True)
    blood_pressure_sys = Column(Integer, nullable=True)
    blood_pressure_dia = Column(Integer, nullable=True)
    heart_rate = Column(Integer, nullable=True)
    temperature = Column(Float, nullable=True)
    oxygen_saturation = Column(Float, nullable=True)
    status = Column(String)  # 'normal', 'warning', 'critical'
    created_at = Column(DateTime, default=datetime.utcnow)

class Salary(Base):
    __tablename__ = "salaries"

    id = Column(Integer, primary_key=True, index=True)
    caregiver_id = Column(Integer, ForeignKey("users.id"))
    center_id = Column(Integer, ForeignKey("centers.id"))
    year_month = Column(String, index=True)  # 'YYYY-MM'
    base_salary = Column(Integer)
    bonus = Column(Integer, default=0)
    deductions = Column(Integer, default=0)
    total = Column(Integer)
    status = Column(String)  # 'pending', 'approved', 'paid'
    created_at = Column(DateTime, default=datetime.utcnow)
