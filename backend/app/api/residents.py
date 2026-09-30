from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from app.models import Resident, Center
from app.schemas import ResidentCreate
from app.database import get_db
from datetime import datetime, date

router = APIRouter()

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
    """이용자 생성 (센터장만 가능)"""
    # 권한 검증: center_manager만 생성 가능
    if user_role not in ["center_manager"]:
        raise HTTPException(status_code=403, detail="이용자 추가 권한이 없습니다 (센터장만 추가 가능)")

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
    name: str = None,
    birth_date: str = None,
    age: int = None,
    care_grade: int = None,
    client_type: str = None,
    health_status: str = None,
    db: Session = Depends(get_db)
):
    """이용자 정보 수정 (이름, 생년월일, 나이, 요양등급, 클라이언트 타입, 건강상태)"""
    resident = db.query(Resident).filter(Resident.id == resident_id).first()
    if not resident:
        raise HTTPException(status_code=404, detail="Resident not found")

    try:
        # 선택적 업데이트
        if name is not None:
            resident.name = name
        if birth_date is not None:
            resident.birth_date = date.fromisoformat(birth_date)
        if age is not None:
            resident.age = age
        if care_grade is not None:
            if care_grade not in [1, 2, 3, 4, 5]:
                raise HTTPException(status_code=400, detail="Invalid care grade")
            resident.care_grade = care_grade
        if client_type is not None:
            if client_type not in ["일반", "차상위계층", "기초생활보장", "의료급여"]:
                raise HTTPException(status_code=400, detail="Invalid client type")
            resident.client_type = client_type
        if health_status is not None:
            if health_status not in ["stable", "warning", "critical"]:
                raise HTTPException(status_code=400, detail="Invalid health status")
            resident.health_status = health_status

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

@router.get("/")
async def list_all_residents(db: Session = Depends(get_db)):
    """전체 이용자 목록 조회"""
    residents = db.query(Resident).all()

    return {
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
                "center_id": r.center_id
            }
            for r in residents
        ]
    }
