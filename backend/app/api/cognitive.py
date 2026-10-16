"""인지활동 계획표: 수급자별 월 계획을 저장하고 인쇄용 활동지로 쓴다.

활동 목록은 일반적인 예시이며, 실제 내용은 센터의 사회복지사·요양보호사가 확인해서 쓴다.
공단 평가 기준이나 청구와는 연결되지 않는다."""
import json
import re
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import require_social_or_manager
from app.database import get_db
from app.models import CognitivePlan, Resident, User

router = APIRouter()
CATALOG = [
    {"code": "recall_talk", "label": "회상 대화 (옛날 사진·추억 이야기)"},
    {"code": "word_match", "label": "낱말·그림 맞추기"},
    {"code": "date_check", "label": "날짜·요일·날씨 확인하기"},
    {"code": "hand_exercise", "label": "손·손가락 운동 (쥐었다 펴기, 공 굴리기)"},
    {"code": "coloring", "label": "색칠하기·종이 접기"},
    {"code": "cooking_memory", "label": "요리 재료 이름 맞추기 (요리 기억)"},
    {"code": "music", "label": "노래 부르기·음악 듣기"},
    {"code": "walk", "label": "산책·바깥 바람 쐬기"},
]
LABELS = {c["code"]: c["label"] for c in CATALOG}
MAX_ITEMS = 8
MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


class PlanItem(BaseModel):
    code: str
    frequency_per_week: int = Field(..., ge=1, le=7)
    minutes: int = Field(..., ge=5, le=120)
    note: Optional[str] = Field(None, max_length=200)


class PlanIn(BaseModel):
    resident_id: int
    year_month: str
    items: List[PlanItem] = Field(..., max_length=MAX_ITEMS)


def _resident(db: Session, resident_id: int, center_id: Optional[int]) -> Resident:
    resident = db.query(Resident).filter(Resident.id == resident_id, Resident.center_id == center_id).first()
    if not resident:
        raise HTTPException(status_code=404, detail="이용자를 찾을 수 없습니다")
    return resident


@router.get("/catalog")
def catalog(actor: User = Depends(require_social_or_manager)):
    return {"status": "success", "data": CATALOG}


@router.get("/plan")
def get_plan(resident_id: int = Query(...), year_month: str = Query(...), db: Session = Depends(get_db),
             actor: User = Depends(require_social_or_manager)):
    if not MONTH.match(year_month):
        raise HTTPException(status_code=400, detail="월은 YYYY-MM 형식으로 적어 주세요")
    resident = _resident(db, resident_id, actor.center_id)
    row = db.query(CognitivePlan).filter(CognitivePlan.resident_id == resident.id, CognitivePlan.year_month == year_month).first()
    items = json.loads(row.items) if row else []
    for item in items:
        item["label"] = LABELS.get(item["code"], item["code"])
    return {"status": "success", "data": {"resident_name": resident.name, "year_month": year_month, "items": items}}


@router.put("/plan")
def save_plan(body: PlanIn, db: Session = Depends(get_db), actor: User = Depends(require_social_or_manager)):
    if not MONTH.match(body.year_month):
        raise HTTPException(status_code=400, detail="월은 YYYY-MM 형식으로 적어 주세요")
    codes = [i.code for i in body.items]
    if any(code not in LABELS for code in codes):
        raise HTTPException(status_code=400, detail="목록에 없는 활동이 있습니다")
    if len(set(codes)) != len(codes):
        raise HTTPException(status_code=400, detail="같은 활동은 한 번만 넣어 주세요")
    resident = _resident(db, body.resident_id, actor.center_id)
    payload = json.dumps([i.model_dump() for i in body.items], ensure_ascii=False)
    row = db.query(CognitivePlan).filter(CognitivePlan.resident_id == resident.id, CognitivePlan.year_month == body.year_month).first()
    if row:
        row.items, row.updated_by = payload, actor.id
    else:
        db.add(CognitivePlan(center_id=actor.center_id, resident_id=resident.id, year_month=body.year_month, items=payload, updated_by=actor.id))
    db.commit()
    return {"status": "success", "data": {"resident_id": resident.id, "year_month": body.year_month, "count": len(body.items)}}
