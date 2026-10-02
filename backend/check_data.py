import sys
sys.path.insert(0, '.')
from app.database import SessionLocal
from app.models import User, Center, Resident

db = SessionLocal()

# 현재 데이터 조회
centers = db.query(Center).all()
residents = db.query(Resident).all()
users = db.query(User).all()

print("=== 현재 데이터 현황 ===\n")
print(f"센터: {len(centers)}개")
for c in centers:
    print(f"  - ID {c.id}: {c.name}")

print(f"\n이용자: {len(residents)}개")

print(f"\n사용자: {len(users)}개")
for u in users[:5]:
    print(f"  - ID {u.id}: {u.email} ({u.role})")

db.close()
