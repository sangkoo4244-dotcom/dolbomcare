#!/usr/bin/env python3
"""
테스트 계정 생성 스크립트
요양사 및 센터장 테스트 계정을 생성합니다.
"""

from sqlalchemy.orm import Session
from datetime import datetime
from app.database import SessionLocal, engine, Base
from app.models import User, Center, Resident
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

    # 센터 생성
    existing_center = db.query(Center).filter(Center.name == "강남 요양원").first()
    if not existing_center:
        manager = db.query(User).filter(User.email == "manager@dolbomcare.com").first()
        center = Center(
            name="강남 요양원",
            address="서울시 강남구",
            phone="02-1234-5678",
            manager_id=manager.id,
            residents_count=10,
            caregivers_count=5
        )
        db.add(center)
        db.commit()
        db.refresh(center)
        print(f"✅ 센터 생성: {center.name}")
    else:
        center = existing_center
        print(f"✅ 센터 이미 존재: {center.name}")

    # 사용자에게 center_id 할당
    caregiver = db.query(User).filter(User.email == "caregiver@dolbomcare.com").first()
    manager = db.query(User).filter(User.email == "manager@dolbomcare.com").first()

    if caregiver and caregiver.center_id != center.id:
        caregiver.center_id = center.id
        db.commit()
        print(f"✅ 요양사에게 센터 할당: {center.name}")

    if manager and manager.center_id != center.id:
        manager.center_id = center.id
        db.commit()
        print(f"✅ 센터장에게 센터 할당: {center.name}")

    # 이용자 생성 (등급 정보 + 생년월일 + 건강상태 포함)
    resident_data = [
        {"name": "홍길동", "birth_date": "1950-03-15", "care_grade": 1, "client_type": "일반", "health_status": "stable"},
        {"name": "이순신", "birth_date": "1948-04-28", "care_grade": 2, "client_type": "차상위계층", "health_status": "warning"},
        {"name": "세종대왕", "birth_date": "1946-07-10", "care_grade": 3, "client_type": "기초생활보장", "health_status": "stable"},
        {"name": "이황", "birth_date": "1947-12-01", "care_grade": 4, "client_type": "의료급여", "health_status": "critical"}
    ]

    for idx, data in enumerate(resident_data):
        existing_resident = db.query(Resident).filter(Resident.name == data["name"]).first()
        if not existing_resident:
            from datetime import date
            birth_date = date.fromisoformat(data["birth_date"])
            resident = Resident(
                center_id=center.id,
                name=data["name"],
                birth_date=birth_date,
                age=75 + idx,
                admission_date=datetime.utcnow(),
                health_status=data.get("health_status", "stable"),
                guardian_id=None,
                care_grade=data["care_grade"],
                client_type=data["client_type"]
            )
            db.add(resident)
            db.commit()
            print(f"✅ 이용자 생성: {data['name']} ({data['birth_date']}) - {data['care_grade']}등급, {data['client_type']}, {data.get('health_status', 'stable')}")
        else:
            print(f"✅ 이용자 이미 존재: {data['name']}")

    db.close()
    print("\n📝 테스트 데이터 생성 완료!")

if __name__ == "__main__":
    create_test_accounts()
