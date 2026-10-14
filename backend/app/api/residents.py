from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional
from app.models import Resident, Center, User
from app.schemas import ResidentCreate
from app.database import get_db
from app.auth import get_current_user, require_manager, assert_self_or_manager
from datetime import datetime, date

class CareNotesUpdate(BaseModel):
    care_notes: str
    user_role: str = "caregiver"

class ResidentUpdate(BaseModel):
    name: str = None
    birth_date: str = None
    age: int = None
    care_grade: Optional[int] = None  # 필드를 아예 안 보내면 유지, None을 명시하면 인지지원등급으로 설정 (exclude_unset으로 구분)
    client_type: str = None
    health_status: str = None
    gender: str = None
    address: str = None
    recognition_number: str = None
    recognition_start: str = None
    recognition_end: str = None
    guardian_name: str = None
    guardian_phone: str = None
    primary_caregiver_id: Optional[int] = None  # exclude_unset으로 "안 보냄"과 "배정 해제(null)"를 구분
    user_role: str = "center_manager"

router = APIRouter()

# 더 구체적인 경로를 먼저 정의 (FastAPI 라우팅 우선순위)
@router.patch("/{resident_id}/care-notes")
async def update_care_notes(
    resident_id: int,
    update_data: CareNotesUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user)
):
    """요양 기록 편집 (요양사, 센터장 가능)"""
    # 권한 검증: caregiver, center_manager 가능
    if actor.role not in ["caregiver", "center_manager"]:
        raise HTTPException(status_code=403, detail="요양 기록 편집 권한이 없습니다")

    resident = db.query(Resident).filter(Resident.id == resident_id).first()
    if not resident:
        raise HTTPException(status_code=404, detail="Resident not found")

    try:
        resident.care_notes = update_data.care_notes
        db.commit()
        db.refresh(resident)

        return {
            "status": "success",
            "message": f"{resident.name}님의 요양 기록이 저장되었습니다",
            "data": {
                "id": resident.id,
                "name": resident.name,
                "care_notes": resident.care_notes
            }
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"요양 기록 저장 중 오류: {str(e)}")

@router.get("/")
async def get_residents(
    center_id: int = None,
    caregiver_id: int = None,
    db: Session = Depends(get_db)
):
    """이용자 목록 조회 (center_id, caregiver_id로 필터링 가능).
    caregiver_id는 담당 요양보호사(primary_caregiver_id)로 지정된 이용자만 걸러낸다."""
    query = db.query(Resident)

    if center_id:
        query = query.filter(Resident.center_id == center_id)

    if caregiver_id:
        query = query.filter(Resident.primary_caregiver_id == caregiver_id)

    residents = query.all()
    caregiver_names = {u.id: u.full_name for u in db.query(User).filter(User.role == "caregiver").all()}

    return {
        "total_residents": len(residents),
        "residents": [
            {
                "id": r.id,
                "center_id": r.center_id,
                "name": r.name,
                "birth_date": r.birth_date.isoformat() if r.birth_date else None,
                "age": r.age,
                "care_grade": r.care_grade,
                "client_type": r.client_type,
                "health_status": r.health_status,
                "admission_date": r.admission_date.isoformat() if r.admission_date else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "gender": r.gender,
                "address": r.address,
                "recognition_number": r.recognition_number,
                "recognition_start": r.recognition_start.isoformat() if r.recognition_start else None,
                "recognition_end": r.recognition_end.isoformat() if r.recognition_end else None,
                "guardian_name": r.guardian_name,
                "guardian_phone": r.guardian_phone,
                "primary_caregiver_id": r.primary_caregiver_id,
                "primary_caregiver_name": caregiver_names.get(r.primary_caregiver_id)
            }
            for r in residents
        ]
    }

@router.get("/center/{center_id}")
async def get_residents_by_center(
    center_id: int,
    db: Session = Depends(get_db)
):
    """센터 내 모든 이용자 조회"""
    residents = db.query(Resident).filter(Resident.center_id == center_id).all()

    return {
        "center_id": center_id,
        "total_residents": len(residents),
        "residents": [
            {
                "id": r.id,
                "name": r.name,
                "birth_date": r.birth_date.isoformat() if r.birth_date else None,
                "age": r.age,
                "care_grade": r.care_grade,
                "client_type": r.client_type,
                "health_status": r.health_status,
                "admission_date": r.admission_date.isoformat() if r.admission_date else None
            }
            for r in residents
        ]
    }

@router.get("/{resident_id}")
async def get_resident(
    resident_id: int,
    db: Session = Depends(get_db)
):
    """이용자 상세 조회"""
    resident = db.query(Resident).filter(Resident.id == resident_id).first()
    if not resident:
        raise HTTPException(status_code=404, detail="Resident not found")

    return {
        "id": resident.id,
        "name": resident.name,
        "birth_date": resident.birth_date.isoformat() if resident.birth_date else None,
        "age": resident.age,
        "care_grade": resident.care_grade,
        "client_type": resident.client_type,
        "health_status": resident.health_status,
        "admission_date": resident.admission_date.isoformat() if resident.admission_date else None,
        "created_at": resident.created_at.isoformat() if resident.created_at else None,
        "gender": resident.gender,
        "address": resident.address,
        "recognition_number": resident.recognition_number,
        "recognition_start": resident.recognition_start.isoformat() if resident.recognition_start else None,
        "recognition_end": resident.recognition_end.isoformat() if resident.recognition_end else None,
        "guardian_name": resident.guardian_name,
        "guardian_phone": resident.guardian_phone,
        "primary_caregiver_id": resident.primary_caregiver_id
    }

@router.put("/{resident_id}/update-grade")
async def update_resident_grade(
    resident_id: int,
    client_type: str,
    care_grade: Optional[int] = None,  # None = 인지지원등급
    db: Session = Depends(get_db),
    _: User = Depends(require_manager)
):
    """이용자 등급 및 클라이언트 타입 수정"""
    resident = db.query(Resident).filter(Resident.id == resident_id).first()
    if not resident:
        raise HTTPException(status_code=404, detail="Resident not found")

    # 유효성 검증
    if care_grade is not None and care_grade not in [1, 2, 3, 4, 5]:
        raise HTTPException(status_code=400, detail="Invalid care grade")

    if client_type not in ["일반", "차상위계층", "기초생활보장", "의료급여"]:
        raise HTTPException(status_code=400, detail="Invalid client type")

    # 수정
    resident.care_grade = care_grade
    resident.client_type = client_type
    db.commit()
    db.refresh(resident)

    return {
        "status": "success",
        "message": f"{resident.name}의 등급이 업데이트되었습니다",
        "data": {
            "id": resident.id,
            "name": resident.name,
            "care_grade": resident.care_grade,
            "client_type": resident.client_type
        }
    }


def parse_recognition_dates(start: str | None, end: str | None):
    try:
        start_date = date.fromisoformat(start) if start else None
        end_date = date.fromisoformat(end) if end else None
    except ValueError:
        raise HTTPException(status_code=400, detail="인정 기간은 YYYY-MM-DD 형식으로 입력해 주세요")
    if start_date and end_date and end_date < start_date:
        raise HTTPException(status_code=400, detail="인정 종료일이 시작일보다 빠를 수 없습니다")
    return start_date, end_date

GRADE_WORDS = {"인지지원등급": None, "인지지원": None, "1등급": 1, "2등급": 2, "3등급": 3, "4등급": 4, "5등급": 5}
CLIENT_TYPES = ("일반", "차상위계층", "기초생활보장", "의료급여")


class ImportRows(BaseModel):
    rows: list[dict]
    dry_run: bool = True  # true면 검사만 하고 저장하지 않는다


def _clean_date(value):
    value = (value or "").strip().replace(".", "-").replace("/", "-")
    if value.isdigit() and len(value) == 8:
        value = f"{value[:4]}-{value[4:6]}-{value[6:]}"
    return value


def _check_import_row(raw: dict):
    """한 줄을 검사해 (저장할 값, 오류 문구)를 돌려준다."""
    get = lambda k: str(raw.get(k, "") or "").strip()
    name = get("이름")
    if not name:
        return None, "이름이 없습니다"
    gender = get("성별")
    if gender and gender not in ("남", "여"):
        return None, "성별은 남 또는 여로 적어 주세요"
    birth = _clean_date(get("생년월일"))
    birth_date = None
    if birth:
        try:
            birth_date = date.fromisoformat(birth)
        except ValueError:
            return None, "생년월일은 2020-01-31 형식으로 적어 주세요"
    age = None
    if birth_date:
        today = date.today()
        age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
    elif get("나이").isdigit():
        age = int(get("나이"))
    if age is None:
        return None, "생년월일 또는 나이가 필요합니다"
    grade_text = get("요양등급")
    if grade_text.isdigit():
        grade_text += "등급"
    if grade_text not in GRADE_WORDS:
        return None, "요양등급은 1~5등급 또는 인지지원등급으로 적어 주세요"
    client_type = get("소득분류") or "일반"
    if client_type not in CLIENT_TYPES:
        return None, "소득분류는 일반, 차상위계층, 기초생활보장, 의료급여 중 하나로 적어 주세요"
    start, end = get("인정시작"), get("인정종료")
    period = get("인정기간")
    if period and "~" in period and not (start or end):
        start, end = [p.strip() for p in period.split("~", 1)]
    try:
        recognition_start, recognition_end = parse_recognition_dates(_clean_date(start) or None, _clean_date(end) or None)
    except HTTPException as e:
        return None, e.detail
    return {
        "name": name, "gender": gender or None, "birth_date": birth_date, "age": age, "care_grade": GRADE_WORDS[grade_text],
        "client_type": client_type, "recognition_number": get("인정번호") or None,
        "recognition_start": recognition_start, "recognition_end": recognition_end, "address": get("주소") or None,
        "guardian_name": get("보호자") or None, "guardian_phone": get("보호자연락처") or None,
    }, None


@router.post("/import")
def import_residents(body: ImportRows, db: Session = Depends(get_db), manager: User = Depends(require_manager)):
    """이용자를 한꺼번에 등록한다 (센터장). 먼저 dry_run으로 검사해 줄마다 문제를 알려 주고,
    문제가 하나도 없을 때만 저장한다 (일부만 저장되어 다시 올리면 중복되는 일을 막는다)."""
    if not body.rows:
        raise HTTPException(status_code=400, detail="올릴 이용자가 없습니다")
    if len(body.rows) > 500:
        raise HTTPException(status_code=400, detail="한 번에 500명까지 올릴 수 있습니다")
    existing = {(r.name, r.birth_date) for r in db.query(Resident).filter(Resident.center_id == manager.center_id).all()}
    seen, ok, errors = set(), [], []
    for i, raw in enumerate(body.rows, start=2):  # 엑셀 줄 번호(1줄은 제목)
        data, error = _check_import_row(raw)
        if not error:
            key = (data["name"], data["birth_date"])
            if key in existing:
                error = "이미 등록된 이용자입니다 (이름·생년월일 동일)"
            elif key in seen:
                error = "파일 안에 같은 이용자가 두 번 있습니다"
            seen.add(key)
        if error:
            errors.append({"row": i, "name": str(raw.get("이름", "") or ""), "message": error})
        else:
            ok.append(data)
    if errors or body.dry_run:
        return {"status": "checked" if not errors else "has_errors", "ok_count": len(ok), "errors": errors, "saved": False}
    for data in ok:
        db.add(Resident(center_id=manager.center_id, admission_date=datetime.now(), health_status="stable", **data))
    db.commit()
    return {"status": "saved", "ok_count": len(ok), "errors": [], "saved": True}


@router.post("/")
async def create_resident(
    resident_data: ResidentCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user)
):
    """이용자 생성 (센터장, 요양사 가능)"""
    # 권한 검증: center_manager, caregiver 가능
    if actor.role not in ["center_manager", "caregiver"]:
        raise HTTPException(status_code=403, detail="이용자 추가 권한이 없습니다")

    # 자기 센터에만 등록할 수 있다
    if resident_data.center_id != actor.center_id:
        raise HTTPException(status_code=403, detail="다른 센터에는 이용자를 등록할 수 없습니다")
    center = db.query(Center).filter(Center.id == resident_data.center_id).first()
    if not center:
        raise HTTPException(status_code=404, detail="센터를 찾을 수 없습니다")

    # 같은 센터 안에서 동일 이름/생년월일 중복 확인 (다른 센터의 같은 이름과는 무관하다)
    existing = db.query(Resident).filter(
        Resident.center_id == actor.center_id,
        Resident.name == resident_data.name,
        Resident.birth_date == (date.fromisoformat(resident_data.birth_date) if resident_data.birth_date else None)
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="동일한 이용자가 이미 등록되어 있습니다")
    recognition_start, recognition_end = parse_recognition_dates(resident_data.recognition_start, resident_data.recognition_end)

    try:
        birth_date = date.fromisoformat(resident_data.birth_date) if resident_data.birth_date else None


        new_resident = Resident(
            center_id=resident_data.center_id,
            name=resident_data.name,
            birth_date=birth_date,
            age=resident_data.age,
            admission_date=datetime.now(),
            health_status=resident_data.health_status,
            care_grade=resident_data.care_grade,
            client_type=resident_data.client_type,
            guardian_id=resident_data.guardian_id,
            primary_caregiver_id=resident_data.primary_caregiver_id,
            gender=resident_data.gender,
            address=resident_data.address,
            recognition_number=resident_data.recognition_number,
            recognition_start=recognition_start,
            recognition_end=recognition_end,
            guardian_name=resident_data.guardian_name,
            guardian_phone=resident_data.guardian_phone
        )
        db.add(new_resident)
        db.commit()
        db.refresh(new_resident)

        return {
            "status": "success",
            "message": f"{resident_data.name}님이 등록되었습니다",
            "data": {
                "id": new_resident.id,
                "name": new_resident.name,
                "birth_date": new_resident.birth_date.isoformat() if new_resident.birth_date else None,
                "age": new_resident.age,
                "care_grade": new_resident.care_grade,
                "client_type": new_resident.client_type,
                "health_status": new_resident.health_status
            }
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"이용자 등록 중 오류: {str(e)}")

@router.put("/{resident_id}")
async def update_resident(
    resident_id: int,
    update_data: ResidentUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user)
):
    """이용자 정보 수정 (JSON Body)
    - 센터장: 모든 필드 수정 가능
    - 요양사: 건강상태, 주소, 보호자 정보만 수정 가능 (등급·소득분류·인정·이름·생년월일은 변경 요청으로)
    """
    resident = db.query(Resident).filter(Resident.id == resident_id).first()
    if not resident:
        raise HTTPException(status_code=404, detail="Resident not found")

    try:
        # care_grade는 None 자체가 유효한 값(인지지원등급)이라, "값을 안 보냄"과 "null로 보냄"을 구분해야 한다
        provided = update_data.model_dump(exclude_unset=True)

        # 요양사는 건강상태 외에는 수정할 수 없다 (청구 금액에 영향을 주는 정보 보호)
        caregiver_locked = [
            name for name in ("name", "birth_date", "age", "care_grade", "client_type", "gender",
                              "recognition_number", "recognition_start", "recognition_end", "primary_caregiver_id")
            if (name in provided if name in ("care_grade", "primary_caregiver_id") else getattr(update_data, name) is not None)
        ]
        if actor.role == "caregiver" and caregiver_locked:
            raise HTTPException(status_code=403, detail="요양사는 이 항목을 직접 수정할 수 없습니다. 센터장에게 변경을 요청하세요")

        # 선택적 업데이트
        if update_data.name is not None:
            resident.name = update_data.name
        if update_data.birth_date is not None:
            resident.birth_date = date.fromisoformat(update_data.birth_date)
        if update_data.age is not None:
            resident.age = update_data.age
        if "care_grade" in provided:
            if provided["care_grade"] is not None and provided["care_grade"] not in [1, 2, 3, 4, 5]:
                raise HTTPException(status_code=400, detail="Invalid care grade")
            resident.care_grade = provided["care_grade"]  # None = 인지지원등급
        caregiver_change = None
        if "primary_caregiver_id" in provided:
            previous_caregiver_id = resident.primary_caregiver_id
            resident.primary_caregiver_id = provided["primary_caregiver_id"]  # None = 배정 해제
            if provided["primary_caregiver_id"] and provided["primary_caregiver_id"] != previous_caregiver_id:
                caregiver_change = {"previous_caregiver_id": previous_caregiver_id, "new_caregiver_id": provided["primary_caregiver_id"]}
        if update_data.client_type is not None:
            if update_data.client_type not in ["일반", "차상위계층", "기초생활보장", "의료급여"]:
                raise HTTPException(status_code=400, detail="Invalid client type")
            resident.client_type = update_data.client_type
        if update_data.health_status is not None:
            if update_data.health_status not in ["stable", "warning", "critical"]:
                raise HTTPException(status_code=400, detail="Invalid health status")
            resident.health_status = update_data.health_status
        if update_data.gender is not None:
            resident.gender = update_data.gender
        if update_data.address is not None:
            resident.address = update_data.address
        if update_data.recognition_number is not None:
            resident.recognition_number = update_data.recognition_number
        new_start, new_end = parse_recognition_dates(
            update_data.recognition_start if update_data.recognition_start is not None else (resident.recognition_start.isoformat() if resident.recognition_start else None),
            update_data.recognition_end if update_data.recognition_end is not None else (resident.recognition_end.isoformat() if resident.recognition_end else None),
        )
        resident.recognition_start = new_start
        resident.recognition_end = new_end
        if update_data.guardian_name is not None:
            resident.guardian_name = update_data.guardian_name
        if update_data.guardian_phone is not None:
            resident.guardian_phone = update_data.guardian_phone

        db.commit()
        db.refresh(resident)

        return {
            "status": "success",
            "message": f"{resident.name}의 정보가 업데이트되었습니다",
            "data": {
                "id": resident.id,
                "name": resident.name,
                "birth_date": resident.birth_date.isoformat() if resident.birth_date else None,
                "age": resident.age,
                "care_grade": resident.care_grade,
                "client_type": resident.client_type,
                "health_status": resident.health_status
            },
            "caregiver_change": caregiver_change
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"이용자 수정 중 오류: {str(e)}")

# 이용자에 딸린 기록을 건수로 알려 줄 때 쓰는 이름 (없는 테이블은 "기타 기록"으로 묶는다)
RELATED_LABELS = {
    "daily_records": "방문 기록", "billing_records": "청구", "schedules": "방문 일정", "resident_messages": "보호자 메시지",
    "resident_media": "사진첩", "care_plans": "급여제공계획", "counselings": "상담 기록", "needs_assessments": "욕구사정",
    "risk_assessments": "낙상·욕창·인지 평가", "copay_invoices": "본인부담금", "incident_reports": "사고·응급 보고",
    "handover_notes": "인수인계", "service_evaluations": "결과평가", "case_conferences": "사례회의",
    "resident_notices": "이용자 안내", "health_metrics": "건강 지표",
}


def _resident_related_tables():
    from app.database import Base
    # 자식 테이블부터 지워야 PostgreSQL의 외래키(FK) 제약을 어기지 않는다
    return [t for t in reversed(Base.metadata.sorted_tables) if "resident_id" in t.columns and t.name != "residents"]


def _count_related(db: Session, resident_id: int) -> dict:
    counts = {}
    for t in _resident_related_tables():
        n = db.query(t).filter(t.c.resident_id == resident_id).count()
        if n:
            counts[t.name] = n
    return counts


def _describe(counts: dict) -> str:
    parts, other = [], 0
    for name, n in counts.items():
        if name in RELATED_LABELS:
            parts.append(f"{RELATED_LABELS[name]} {n}건")
        else:
            other += n
    if other:
        parts.append(f"기타 기록 {other}건")
    return ", ".join(parts)


@router.delete("/{resident_id}")
async def delete_resident(
    resident_id: int,
    force: bool = False,
    db: Session = Depends(get_db),
    manager: User = Depends(require_manager)
):
    """이용자 삭제 (센터장만 가능, 자기 센터 이용자만).
    방문 기록·청구 등 딸린 기록이 있으면 기본적으로 삭제하지 않고 무엇이 있는지 알려 준다(409).
    force=true일 때만 딸린 기록까지 함께 지운다 (복구 불가)."""
    resident = db.query(Resident).filter(Resident.id == resident_id, Resident.center_id == manager.center_id).first()
    if not resident:
        raise HTTPException(status_code=404, detail="이용자를 찾을 수 없습니다")

    counts = _count_related(db, resident_id)
    if counts and not force:
        raise HTTPException(status_code=409, detail={"message": f"이 이용자에게 {_describe(counts)}이 있습니다", "related": counts})

    try:
        resident_name = resident.name
        from app.models import CarePlan, CarePlanAck
        plan_ids = [p for (p,) in db.query(CarePlan.id).filter(CarePlan.resident_id == resident_id).all()]
        if plan_ids:
            db.query(CarePlanAck).filter(CarePlanAck.plan_id.in_(plan_ids)).delete(synchronize_session=False)
        for t in _resident_related_tables():
            db.execute(t.delete().where(t.c.resident_id == resident_id))
        db.delete(resident)
        db.commit()

        return {
            "status": "success",
            "message": f"{resident_name}님이 삭제되었습니다",
            "resident_id": resident_id
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"이용자 삭제 중 오류: {str(e)}")
