#!/usr/bin/env python3
"""
테스트 계정 생성 스크립트
요양사 및 센터장 테스트 계정을 생성합니다.
"""

from sqlalchemy.orm import Session
from app.database import SessionLocal, engine, Base
from app.models import User
from app.api.users import get_password_hash

def create_test_accounts():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    test_accounts = [
        {
            "email": "caregiver@dolbomcare.com",
            "password": "password123",
            "full_name": "김요양사",
            "role": "caregiver"
        },
        {
            "email": "manager@dolbomcare.com",
            "password": "password123",
            "full_name": "이센터장",
            "role": "center_manager"
        }
    ]

    for account in test_accounts:
        existing_user = db.query(User).filter(User.email == account["email"]).first()

        if existing_user:
            print(f"✅ 이미 존재: {account['email']}")
            continue

        hashed_password = get_password_hash(account["password"])
        new_user = User(
            email=account["email"],
            hashed_password=hashed_password,
            full_name=account["full_name"],
            role=account["role"],
            is_active=True
        )
        db.add(new_user)

        try:
            db.commit()
            db.refresh(new_user)
            print(f"✅ 생성 완료: {account['email']} ({account['role']})")
        except Exception as e:
            db.rollback()
            print(f"❌ 오류: {account['email']} - {str(e)}")

    db.close()
    print("\n📝 테스트 계정 생성 완료!")

if __name__ == "__main__":
    create_test_accounts()
