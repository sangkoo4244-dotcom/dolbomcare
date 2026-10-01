from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.models import Resident, Center
from app.schemas import ResidentCreate
from app.database import get_db
from datetime import datetime, date

class CareNotesUpdate(BaseModel):
    care_notes: str
    user_role: str = "caregiver"

class ResidentUpdate(BaseModel):
    name: str = None
    birth_date: str = None
    age: int = None
    care_grade: int = None
    client_type: str = None
    health_status: str = None
    user_role: str = "center_manager"

router = APIRouter()

# 더 구체적인 경로를 먼저 정의 (FastAPI 라우팅 우선순위)
@router.patch("/{resident_id}/care-notes")
async def update_care_notes(
    resident_id: int,
    update_data: CareNotesUpdate,
    db: Session = Depends(get_db)
):
    """요양 기록 편집 (요양사, 센터장 가능)"""
    # 권한 검증: caregiver, center_manager 가능
    if update_data.user_role not in ["caregiver", "center_manager"]:
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
    db: Session = Depends(get_db)
):
    """이용자 목록 조회 (center_id로 필터링 가능)"""
    query = db.query(Resident)

    if center_id:
        query = query.filter(Resident.center_id == center_id)

    residents = query.all()

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
                "created_at": r.created_at.isoformat() if r.created_at else None
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
        "created_at": resident.created_at.isoformat() if resident.created_at else None
    }

@router.put("/{resident_id}/update-grade")
async def update_resident_grade(
    resident_id: int,
    care_grade: int,
    client_type: str,
    db: Session = Depends(get_db)
):
    """이용자 등급 및 클라이언트 타입 수정"""
    resident = db.query(Resident).filter(Resident.id == resident_id).first()
    if not resident:
        raise HTTPException(status_code=404, detail="Resident not found")

    # 유효성 검증
    if care_grade not in [1, 2, 3, 4, 5]:
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

@router.post("/")
async def create_resident(
    resident_data: ResidentCreate,
    user_role: str,
    db: Session = Depends(get_db)
):
    """이용자 생성 (센터장, 요양사 가능)"""
    # 권한 검증: center_manager, caregiver 가능
    if user_role not in ["center_manager", "caregiver"]:
        raise HTTPException(status_code=403, detail="이용자 추가 권한이 없습니다")

    # 센터 존재 여부 확인
    center = db.query(Center).filter(Center.id == resident_data.center_id).first()
    if not center:
        raise HTTPException(status_code=404, detail="센터를 찾을 수 없습니다")

    # 동일 이름/생년월일 중복 확인
    existing = db.query(Resident).filter(
        Resident.name == resident_data.name,
        Resident.birth_date == (date.fromisoformat(resident_data.birth_date) if resident_data.birth_date else None)
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="동일한 이용자가 이미 등록되어 있습니다")

    try:
        birth_date = date.fromisoformat(resident_data.birth_date) if resident_data.birth_date else None

        new_resident = Resident(
            center_id=resident_data.center_id,
            name=resident_data.name,
            birth_date=birth_date,
            age=resident_data.age,
            admission_date=datetime.utcnow(),
            health_status=resident_data.health_status,
            care_grade=resident_data.care_grade,
            client_type=resident_data.client_type,
            guardian_id=resident_data.guardian_id
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
    db: Session = Depends(get_db)
):
    """이용자 정보 수정 (JSON Body)
    - 센터장: 모든 필드 수정 가능 (이름, 생년월일 포함)
    - 요양사: 나이, 요양등급, 클라이언트 타입, 건강상태만 수정 가능
    """
    resident = db.query(Resident).filter(Resident.id == resident_id).first()
    if not resident:
        raise HTTPException(status_code=404, detail="Resident not found")

    try:
        # 요양사는 이름/생년월일 수정 불가
        if update_data.user_role == "caregiver" and (update_data.name is not None or update_data.birth_date is not None):
            raise HTTPException(status_code=403, detail="요양사는 이용자의 기본정보(이름, 생년월일)를 수정할 수 없습니다")

        # 선택적 업데이트
        if update_data.name is not None:
            resident.name = update_data.name
        if update_data.birth_date is not None:
            resident.birth_date = date.fromisoformat(update_data.birth_date)
        if update_data.age is not None:
            resident.age = update_data.age
        if update_data.care_grade is not None:
            if update_data.care_grade not in [1, 2, 3, 4, 5]:
                raise HTTPException(status_code=400, detail="Invalid care grade")
            resident.care_grade = update_data.care_grade
        if update_data.client_type is not None:
            if update_data.client_type not in ["일반", "차상위계층", "기초생활보장", "의료급여"]:
                raise HTTPException(status_code=400, detail="Invalid client type")
            resident.client_type = update_data.client_type
        if update_data.health_status is not None:
            if update_data.health_status not in ["stable", "warning", "critical"]:
                raise HTTPException(status_code=400, detail="Invalid health status")
            resident.health_status = update_data.health_status

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
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"이용자 수정 중 오류: {str(e)}")

@router.delete("/{resident_id}")
async def delete_resident(
    resident_id: int,
    user_role: str,
    db: Session = Depends(get_db)
):
    """이용자 삭제 (센터장만 가능)"""
    # 권한 검증
    if user_role not in ["center_manager"]:
        raise HTTPException(status_code=403, detail="이용자 삭제 권한이 없습니다 (센터장만 삭제 가능)")

    resident = db.query(Resident).filter(Resident.id == resident_id).first()
    if not resident:
        raise HTTPException(status_code=404, detail="Resident not found")

    try:
        resident_name = resident.name
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
