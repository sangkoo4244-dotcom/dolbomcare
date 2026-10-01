from app.database import SessionLocal
from app.models import BillingRecord

db = SessionLocal()
records = db.query(BillingRecord).all()

print("전체 청부 기록:")
print(f"총 개수: {len(records)}건\n")

status_count = {}
for r in records:
    status = r.approval_status or "None"
    status_count[status] = status_count.get(status, 0) + 1
    print(f"ID: {r.id}, 상태: {r.approval_status}, 센터: {r.center_id}, 금액: {r.amount}")

print("\n상태별 집계:")
for status, count in sorted(status_count.items()):
    print(f"  {status}: {count}건")

db.close()
