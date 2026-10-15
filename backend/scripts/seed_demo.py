"""
가입 없이 체험할 수 있는 데모 계정을 만든다 (login.html의 "둘러보기" 버튼이 사용).

재실행하면 기존 데모 데이터를 전부 지우고 새로 만든다 - 즉, 이 스크립트를 다시 실행하는 것이
데모 데이터 초기화(reset) 방법이다. 실제 센터/이용자 데이터는 건드리지 않는다.
운영 서버에서는 운영자 콘솔의 "데모 체험 계정" 버튼이 같은 일을 한다 (로직은 app/demo_seed.py).

실행:
    cd backend && venv/Scripts/python.exe scripts/seed_demo.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.database import SessionLocal
from app.demo_seed import DEMO_PASSWORD, seed_demo

db = SessionLocal()
try:
    result = seed_demo(db)
    print(f"데모 센터 {result['center_id']}: 이용자 {result['residents']}명, 청구 {result['bills']}건, 예정 일정 {result['schedules']}건 ({'초기화 후 ' if result['reset'] else ''}생성 완료)")
    print("\n=== 데모 계정 정보 (login.html 버튼이 이 값을 그대로 사용) ===")
    for email in result["accounts"]:
        print(f"{email} / {DEMO_PASSWORD}")
finally:
    db.close()
