from app.database import SessionLocal
from app.models import DailyRecord
from sqlalchemy import func

db = SessionLocal()

print("=" * 70)
print("🎤 음성 기록 데이터 확인")
print("=" * 70)
print()

# 전체 음성 기록
all_records = db.query(DailyRecord).all()
print(f"📊 전체 음성 기록 수: {len(all_records)}")
print()

# 요양사별 음성 기록
print("📋 요양사별 음성 기록:")
caregiver_counts = db.query(DailyRecord.caregiver_id, func.count(DailyRecord.id)).group_by(DailyRecord.caregiver_id).all()
for caregiver_id, count in caregiver_counts:
    print(f"  - 요양사 {caregiver_id}: {count}개")
print()

# 센터별 음성 기록
print("🏥 센터별 음성 기록:")
center_counts = db.query(DailyRecord).filter(DailyRecord.center_id != None).all()
center_map = {}
for record in center_counts:
    center_id = record.center_id if record.center_id else "NULL"
    center_map[center_id] = center_map.get(center_id, 0) + 1

for center_id in sorted(center_map.keys()):
    print(f"  - 센터 {center_id}: {center_map[center_id]}개")
print()

# 상세 목록
print("📝 모든 음성 기록 상세:")
for record in sorted(all_records, key=lambda x: x.id):
    print(f"  - ID={record.id}, 요양사={record.caregiver_id}, 이용자={record.resident_id}, 센터={record.center_id}, 날짜={record.recorded_date}")
print()

print("=" * 70)
print("⚠️ 음성 기록이 센터 정보 없이 저장되고 있을 수 있습니다")
print("=" * 70)

db.close()
