import sys
sys.path.insert(0, '.')
from app.database import SessionLocal
from app.models import User

db = SessionLocal()

print("=== 데이터베이스에 저장된 사용자 ===\n")

users = db.query(User).all()
print(f"총 사용자: {len(users)}명\n")

for user in users:
    print(f"ID: {user.id}")
    print(f"  이메일: {user.email}")
    print(f"  이름: {user.full_name}")
    print(f"  역할: {user.role}")
    print(f"  활성: {user.is_active}")
    print(f"  비밀번호 해시: {user.hashed_password[:50]}...")
    print()

db.close()

print("\n=== 로그인 테스트 ===")
print("시도할 계정:")
print("- caregiver@dolbomcare.com / password123")
print("- manager@dolbomcare.com / password123")
