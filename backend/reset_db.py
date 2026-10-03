#!/usr/bin/env python3
"""데이터베이스 완전 초기화"""

from app.database import engine, SessionLocal, Base
from app.models import User, Center, Resident, BillingRecord, DailyRecord, Schedule

# 모든 테이블 삭제
print("🗑️  모든 테이블 삭제 중...")
Base.metadata.drop_all(bind=engine)

# 모든 테이블 다시 생성
print("🔨 모든 테이블 다시 생성 중...")
Base.metadata.create_all(bind=engine)

print("✅ 데이터베이스 초기화 완료!")
