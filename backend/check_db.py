from app.database import SessionLocal
from app.models import Resident, User, Center

db = SessionLocal()

# 센터 확인
centers = db.query(Center).all()
print(f"✅ 센터 수: {len(centers)}")
for c in centers:
    print(f"  - ID: {c.id}, 이름: {c.name}")

# 사용자 확인
users = db.query(User).all()
print(f"\n✅ 사용자 수: {len(users)}")
for u in users:
    print(f"  - ID: {u.id}, 이름: {u.full_name}, 역할: {u.role}, center_id: {u.center_id}")

# 이용자 확인
residents = db.query(Resident).all()
print(f"\n✅ 이용자 수: {len(residents)}")
for r in residents:
    print(f"  - ID: {r.id}, 이름: {r.name}, center_id: {r.center_id}, 등급: {r.care_grade}")

db.close()
