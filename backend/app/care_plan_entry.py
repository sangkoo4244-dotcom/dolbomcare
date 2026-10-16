"""공단 장기요양정보시스템 '급여제공계획서 전산 등록' 화면 순서(2026 급여제공계획서 가이드북 2-3)에 맞춘 입력 시트.

방문요양 센터는 계획서 엑셀 업로드를 쓸 수 없으므로(가이드북 Q9: 입소·단기보호·주야간보호만), 우리 계획서 내용을
공단 화면에 옮겨 적기 쉽게 탭 순서대로 나눠 보여 준다. 공단 시스템에 전송하거나 자동 입력하지 않는다.
"""

GUIDE = "2026 급여제공계획서 가이드북(26.6월) 2-3 급여제공계획서 전산 등록"


def _iso(d):
    return d.isoformat() if d else None


def entry_sheet(plan, resident) -> dict:
    """계획서 한 건을 공단 입력 탭 순서로 나눈다. 빠진 값은 warnings에 적는다."""
    warnings = []
    recognition = resident.recognition_number if resident else None
    if not recognition:
        warnings.append("장기요양인정번호가 없습니다 (화면 상단에서 수급자를 찾는 데 필요합니다)")
    if not plan.service_start_date:
        warnings.append("적용기간 시작일이 없습니다 (공단 화면의 적용기간)")
    if not (plan.needs or "").strip():
        warnings.append("필요내용이 비어 있습니다 (필요내용 작성 탭)")
    if not (plan.details or "").strip():
        warnings.append("세부제공내용이 비어 있습니다 (필요내용 작성 탭)")
    if not (plan.goals or "").strip():
        warnings.append("세부목표가 비어 있습니다 (목표주기 작성 탭, 그룹별 한 가지 이상)")
    if not (plan.frequency or "").strip():
        warnings.append("횟수가 비어 있습니다 (목표주기 작성 탭)")
    if not plan.duration_minutes:
        warnings.append("1회 제공시간이 비어 있습니다 (목표주기 작성 탭)")
    if plan.plan_type == "change" and not plan.change_reason:
        warnings.append("변경 계획서인데 변경 사유가 없습니다 (작성사유 선택)")
    if not (plan.opinion or "").strip():
        warnings.append("종합의견이 비어 있습니다 (통보 탭)")
    if not plan.guardian_signed_date:
        warnings.append("수급자(보호자) 동의일이 없습니다 (통보 탭: 동의자, 동의일자, 확인여부)")

    return {
        "guide": GUIDE,
        "note": "시간 합산은 참고용이라 서비스 제공시간과 반드시 맞출 필요는 없습니다. 공단 화면의 '이용계획서 번호'와 '적용기간 종료일'은 우리 계획서에 없어 직접 입력해야 합니다.",
        "warnings": warnings,
        "tabs": [
            {"tab": "등록 정보 (급여제공계획서 등록 화면)", "fields": [
                {"label": "수급자 장기요양인정번호", "value": recognition or ""},
                {"label": "적용기간 시작일", "value": _iso(plan.service_start_date) or ""},
                {"label": "적용기간 종료일 (공단 화면에서 입력)", "value": ""},
                {"label": "작성일자", "value": _iso(plan.written_date) or ""},
                {"label": "작성사유 (최초 계약자는 '최초급여계약', 그 외는 해당 사유 선택)", "value": plan.change_reason or ("변경" if plan.plan_type == "change" else "")},
                {"label": "급여종류", "value": plan.service_type or "방문요양"},
                {"label": "개인별장기요양이용계획서 번호 (공단 화면에서 입력)", "value": ""},
            ]},
            {"tab": "필요내용 작성", "fields": [
                {"label": "필요영역·필요내용 (공단 목록에서 선택)", "value": (plan.needs or "").strip()},
                {"label": "세부제공내용 (필요내용 선택 시 자동 선택, 직접 쓸 때 체크 후 입력)", "value": (plan.details or "").strip()},
            ]},
            {"tab": "목표주기 작성", "fields": [
                {"label": "횟수", "value": plan.frequency or ""},
                {"label": "1회 제공시간(분)", "value": str(plan.duration_minutes) if plan.duration_minutes else ""},
                {"label": "주기 (월·주·일·필요시 중 선택)", "value": ""},
                {"label": "세부목표 (그룹별 한 가지 이상)", "value": (plan.goals or "").strip()},
            ]},
            {"tab": "통보 (동의·종합의견)", "fields": [
                {"label": "종합의견", "value": (plan.opinion or "").strip()},
                {"label": "동의자 (수급자 또는 보호자)", "value": plan.guardian_signer or ""},
                {"label": "동의일자", "value": _iso(plan.guardian_signed_date) or ""},
                {"label": "수급자(보호자) 확인여부", "value": "예" if plan.guardian_signed_date else ""},
            ]},
        ],
    }
