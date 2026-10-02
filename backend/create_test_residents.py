#!/usr/bin/env python3
"""
테스트 이용자(Resident) 데이터 생성 스크립트
RUflo 자동화 테스트에 필요한 이용자 데이터를 생성합니다.
"""

import sys
sys.path.insert(0, '.')
from app.database import SessionLocal
from app.models import User, Center, Resident
from datetime import datetime, timedelta

def create_test_residents():
    db = SessionLocal()

    try:
        # 1. 센터 확인 (create_test_accounts.py에서 생성됨)
        center = db.query(Center).first()
        if not center:
            print("❌ 센터이 없습니다. create_test_accounts.py를 먼저 실행하세요.")
            return

        print(f"✅ 센터 확인: {center.name} (ID: {center.id})")

        # 2. 보호자 사용자 확인 (없으면 생성)
        guardian = db.query(User).filter(
            User.role == "guardian",
            User.email == "guardian@dolbomcare.com"
        ).first()

        if not guardian:
            from passlib.context import CryptContext
            pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

            guardian = User(
                email="guardian@dolbomcare.com",
                hashed_password=pwd_context.hash("password123"),
                full_name="김은희 (보호자)",
                role="guardian",
                phone="010-9999-9999",
                is_active=True
            )
            db.add(guardian)
            db.commit()
            print(f"✅ 보호자 사용자 생성: {guardian.email}")
        else:
            print(f"✅ 보호자 사용자 확인: {guardian.email}")

        # 3. 테스트 이용자 생성
        test_residents = [
            {
                "name": "이순신",
                "birth_date": "1970-05-15",
                "age": 53,
                "health_status": "stable",
                "care_grade": 1,
                "client_type": "일반"
            },
            {
                "name": "정선미",
                "birth_date": "1965-08-22",
                "age": 58,
                "health_status": "stable",
                "care_grade": 2,
                "client_type": "기초생활보장"
            },
            {
                "name": "박영희",
                "birth_date": "1960-03-10",
                "age": 63,
                "health_status": "warning",
                "care_grade": 3,
                "client_type": "의료급여"
            },
            {
                "name": "김민재",
                "birth_date": "1968-11-28",
                "age": 55,
                "health_status": "stable",
                "care_grade": 1,
                "client_type": "일반"
            },
            {
                "name": "이영순",
                "birth_date": "1962-06-14",
                "age": 61,
                "health_status": "critical",
                "care_grade": 4,
                "client_type": "차상위계층"
            }
        ]

        created_count = 0
        for resident_data in test_residents:
            # 이미 존재하는지 확인
            existing = db.query(Resident).filter(
                Resident.center_id == center.id,
                Resident.name == resident_data["name"]
            ).first()

            if not existing:
                resident = Resident(
                    center_id=center.id,
                    name=resident_data["name"],
                    birth_date=datetime.strptime(resident_data["birth_date"], "%Y-%m-%d").date(),
                    age=resident_data["age"],
                    admission_date=datetime.now() - timedelta(days=30),
                    health_status=resident_data["health_status"],
                    guardian_id=guardian.id,
                    care_grade=resident_data["care_grade"],
                    client_type=resident_data["client_type"],
                    care_notes=f"{resident_data['name']} 기본 요양 기록"
                )
                db.add(resident)
                created_count += 1

        db.commit()

        # 4. 결과 출력
        print(f"\n✅ 이용자 {created_count}명 생성 완료")

        # 5. 생성된 이용자 목록 출력
        all_residents = db.query(Resident).filter(Resident.center_id == center.id).all()
        print(f"\n📋 {center.name}의 이용자 목록 ({len(all_residents)}명):")
        print("-" * 60)
        print(f"{'ID':<3} | {'이름':<10} | {'나이':<3} | {'등급':<2} | {'상태':<10}")
        print("-" * 60)
        for r in all_residents:
            print(f"{r.id:<3} | {r.name:<10} | {r.age:<3} | {r.care_grade:<2} | {r.health_status:<10}")

        print(f"\n✨ RUflo 테스트 준비 완료!")
        print(f"   - 음성 기록 테스트 가능")
        print(f"   - 청부 자동화 테스트 가능")

    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    create_test_residents()
