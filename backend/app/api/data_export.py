"""센터 데이터 내보내기: 센터장이 자기 센터의 이용자와 제공 기록을 기간별로 받는다.
해지나 이전 때 데이터를 가져갈 수 있어야 하므로 센터장만 쓸 수 있고, 다른 센터 자료는 절대 섞이지 않는다.
비밀번호·인증 정보는 포함하지 않는다."""
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import require_manager
from app.database import get_db
from app.models import DailyRecord, Resident, User

router = APIRouter()

MAX_DAYS = 366


@router.get("/center")
def export_center_data(
    start: date = Query(...),
    end: date = Query(...),
    db: Session = Depends(get_db),
    actor: User = Depends(require_manager),
):
    if end < start:
        raise HTTPException(status_code=400, detail="종료일이 시작일보다 빠릅니다")
    if (end - start).days > MAX_DAYS:
        raise HTTPException(status_code=400, detail="한 번에 최대 1년까지 내보낼 수 있습니다. 기간을 나누어 받아 주세요")

    residents = db.query(Resident).filter(Resident.center_id == actor.center_id).order_by(Resident.id).all()
    resident_ids = [r.id for r in residents]
    names = {r.id: r.name for r in residents}
    caregivers = {u.id: u.full_name for u in db.query(User).filter(User.center_id == actor.center_id).all()}

    records = []
    if resident_ids:
        start_dt = datetime.combine(start, datetime.min.time())
        end_dt = datetime.combine(end + timedelta(days=1), datetime.min.time())
        rows = (
            db.query(DailyRecord)
            .filter(DailyRecord.resident_id.in_(resident_ids),
                    DailyRecord.recorded_date >= start_dt, DailyRecord.recorded_date < end_dt)
            .order_by(DailyRecord.recorded_date, DailyRecord.id)
            .all()
        )
        records = [
            {
                "id": r.id,
                "resident_id": r.resident_id,
                "resident_name": names.get(r.resident_id, ""),
                "caregiver_name": caregivers.get(r.caregiver_id, ""),
                "recorded_at": r.recorded_date.isoformat() if r.recorded_date else None,
                "service_type": r.service_type,
                "duration_minutes": r.duration_minutes,
                "care_items": r.care_items,
                "condition": r.condition,
                "notes": r.notes,
            }
            for r in rows
        ]

    return {
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "residents": [
            {
                "id": r.id, "name": r.name, "age": r.age, "gender": r.gender, "care_grade": r.care_grade,
                "client_type": r.client_type, "admission_date": r.admission_date.isoformat() if r.admission_date else None,
                "address": r.address,
            }
            for r in residents
        ],
        "daily_records": records,
    }
