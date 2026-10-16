"""센터 내부 점검 기록: 차량, 욕조, 간호 용품. 공단 공식 서식이 아니며 센터가 점검 사실을 남기는 대장이다."""
import json
from datetime import date
from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_manager
from app.database import get_db
from app.models import InspectionLog, User

router = APIRouter()
ITEMS = {
    "vehicle": ["차량 외관·타이어", "리프트·휠체어 고정장치 작동", "안전벨트", "차량 소독", "응급 키트", "차량 보험 서류 비치"],
    "bath_tub": ["욕조 세척·소독", "배수 상태", "손잡이 고정", "미끄럼 방지 장치", "온도 조절 확인", "이동식 욕조 장비 상태"],
    "nursing_kit": ["혈압계·체온계 작동", "의료폐기물 용기", "소독약·거즈 재고", "응급약 유통기한", "장갑·마스크 재고"],
}
LABELS = {"vehicle": "차량", "bath_tub": "욕조", "nursing_kit": "간호 용품"}
VALUES = ("ok", "fail", "na")


class InspectionBody(BaseModel):
    kind: str
    check_date: date
    results: Dict[str, str]
    note: Optional[str] = None


def _to_dict(row: InspectionLog, names: dict) -> dict:
    return {"id": row.id, "kind": row.kind, "kind_label": LABELS.get(row.kind, row.kind),
            "check_date": row.check_date.isoformat(), "inspector": names.get(row.inspector_id, ""),
            "results": json.loads(row.results or "{}"), "note": row.note}


@router.get("/items")
def items(actor: User = Depends(get_current_user)):
    return {"status": "success", "data": {k: {"label": LABELS[k], "items": v} for k, v in ITEMS.items()}}


@router.post("")
def create(body: InspectionBody, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    if actor.role not in ("center_manager", "caregiver") or not actor.center_id:
        raise HTTPException(status_code=403, detail="센터장 또는 요양보호사만 점검 기록을 남길 수 있습니다")
    if body.kind not in ITEMS:
        raise HTTPException(status_code=400, detail="점검 종류는 차량, 욕조, 간호 용품 중에서 골라 주세요")
    allowed = set(ITEMS[body.kind])
    if any(k not in allowed for k in body.results) or any(v not in VALUES for v in body.results.values()):
        raise HTTPException(status_code=400, detail="점검 항목 값이 올바르지 않습니다")
    row = InspectionLog(center_id=actor.center_id, kind=body.kind, check_date=body.check_date, inspector_id=actor.id,
                        results=json.dumps(body.results, ensure_ascii=False), note=(body.note or "").strip() or None)
    db.add(row)
    db.commit()
    return {"status": "success", "data": {"id": row.id}}


@router.get("")
def list_logs(kind: Optional[str] = Query(None), db: Session = Depends(get_db), actor: User = Depends(require_manager)):
    q = db.query(InspectionLog).filter(InspectionLog.center_id == actor.center_id)
    if kind:
        q = q.filter(InspectionLog.kind == kind)
    rows = q.order_by(InspectionLog.check_date.desc(), InspectionLog.id.desc()).limit(200).all()
    names = {u.id: u.full_name for u in db.query(User).filter(User.center_id == actor.center_id).all()}
    return {"status": "success", "data": [_to_dict(r, names) for r in rows]}
