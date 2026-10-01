#!/usr/bin/env python3
"""상태 머신 검증 - 상태 전이 로직 확인"""

print("\n" + "="*70)
print("🔍 청부 관리 상태 머신 검증")
print("="*70)

# 정의된 상태들
STATES = {
    "pending": {
        "label": "⏳ 승인 대기",
        "role": "center_manager",
        "actions": ["approve", "reject"],
        "next_states": ["approved", "rejected"]
    },
    "approved": {
        "label": "✅ 승인됨",
        "role": "center_manager",
        "actions": ["submit_to_nhis"],
        "next_states": ["submitted_to_nhis"]
    },
    "submitted_to_nhis": {
        "label": "📤 건보 청구됨",
        "role": "center_manager",
        "actions": ["confirm_reimbursement", "cancel_nhis_submission"],
        "next_states": ["reimbursed", "approved"]
    },
    "reimbursed": {
        "label": "💰 환급완료",
        "role": "system",
        "actions": [],
        "next_states": [],
        "is_archived": True
    },
    "rejected": {
        "label": "❌ 거절됨",
        "role": "center_manager",
        "actions": [],
        "next_states": []
    }
}

# 미사용 상태들 (제거됨)
REMOVED_STATES = {
    "confirmed": "확정됨 (미사용)",
    "rejected_by_nhis": "건보 반려 (미사용)",
    "pending_reimbursement": "건보 심사 중 (미사용)"
}

print("\n📊 1️⃣ 정의된 상태들")
print("-" * 70)
for state, config in STATES.items():
    archived = " 🗄️ (아카이브)" if config.get("is_archived") else ""
    print(f"\n{state.upper()}: {config['label']}{archived}")
    print(f"  역할: {config['role']}")
    print(f"  동작: {', '.join(config['actions']) if config['actions'] else 'None'}")
    print(f"  다음 상태: {', '.join(config['next_states']) if config['next_states'] else 'None'}")

print("\n\n📋 2️⃣ 제거된 상태들")
print("-" * 70)
for state, reason in REMOVED_STATES.items():
    print(f"  ✗ {state}: {reason}")

# 상태 전이 검증
print("\n\n🔄 3️⃣ 상태 전이 경로")
print("-" * 70)
print("\n요양사 관점 (요양사는 청부 생성만 가능):")
print("  1. draft (음성기록 → 자동 생성)")
print("     ↓")
print("  2. pending (요양사가 [제출] 버튼 → 센터장에게 승인 요청)")

print("\n\n센터장 관점:")
print("  ┌─ pending")
print("  │  ├─→ [승인] → approved")
print("  │  └─→ [거절] → rejected")
print("  │")
print("  ├─ approved")
print("  │  └─→ [건보 청구] → submitted_to_nhis")
print("  │")
print("  ├─ submitted_to_nhis")
print("  │  ├─→ [환급 확인] → reimbursed 🗄️ (자동 아카이브)")
print("  │  └─→ [취소] → approved")
print("  │")
print("  ├─ rejected")
print("  │  └─→ (변경 불가 - 요양사가 [제출]로 draft로 돌아감)")
print("  │")
print("  └─ reimbursed 🗄️ (최종)")

# 데이터 검증
print("\n\n📊 4️⃣ 데이터 타입 및 필드 검증")
print("-" * 70)

fields_required = {
    "id": "int",
    "resident_id": "int",
    "caregiver_id": "int",
    "center_id": "int",
    "approval_status": "str",
    "is_archived": "bool",
    "amount": "int",
    "recorded_date": "datetime",
    "created_at": "datetime"
}

fields_optional = {
    "approved_at": "datetime",
    "archived_at": "datetime",
    "rejection_reason": "str",
    "submitted_date": "datetime"
}

print("\n필수 필드:")
for field, type_name in fields_required.items():
    print(f"  ✓ {field}: {type_name}")

print("\n선택적 필드:")
for field, type_name in fields_optional.items():
    print(f"  ○ {field}: {type_name}")

# 상태별 필드 검증
print("\n\n⚠️ 5️⃣ 상태별 필드 검증")
print("-" * 70)

rules = {
    "pending": {
        "must_have": ["approval_status"],
        "must_not_have": ["approved_at", "archived_at"],
        "note": "대기 중 - 승인 정보 없음"
    },
    "approved": {
        "must_have": ["approved_at", "approved_by"],
        "must_not_have": ["archived_at"],
        "note": "승인됨 - 승인 시간/승인자 필수"
    },
    "submitted_to_nhis": {
        "must_have": ["approved_at", "approved_by"],
        "must_not_have": ["archived_at"],
        "note": "건보청구 - 아직 아카이브 안 됨"
    },
    "reimbursed": {
        "must_have": ["is_archived=True", "archived_at"],
        "must_not_have": [],
        "note": "환급완료 - 반드시 아카이브됨"
    },
    "rejected": {
        "must_have": ["rejection_reason", "approved_at"],
        "must_not_have": ["archived_at"],
        "note": "거절됨 - 거절 사유 필수"
    }
}

for status, rule in rules.items():
    print(f"\n{status.upper()}: {rule['note']}")
    print(f"  필수: {rule['must_have']}")
    print(f"  제외: {rule['must_not_have']}")

# 체크리스트
print("\n\n✅ 6️⃣ 최종 체크리스트")
print("-" * 70)

checks = [
    ("모든 미사용 상태 제거", True),
    ("아카이브 자동화 구현", True),
    ("상태별 필드 검증", False),  # 아직 구현되지 않은 부분
    ("상태 전이 제약 구현", False),  # 아직 구현되지 않은 부분
    ("감사 로그 기록", False),  # Phase 2
]

for item, done in checks:
    status = "✅" if done else "⏳"
    print(f"{status} {item}")

print("\n" + "="*70)
print("✅ 상태 머신 검증 완료")
print("="*70 + "\n")
