#!/usr/bin/env python3
import requests
import json
import sys

BASE_URL = "http://localhost:8000/api/v1"

print("=" * 60)
print("🔍 요양사 ↔ 센터장 데이터 일치성 확인")
print("=" * 60)
print()

# 1. 요양사 로그인
print("1️⃣ 요양사 로그인")
print("-" * 60)
caregiver_response = requests.post(
    f"{BASE_URL}/users/login",
    json={"email": "caregiver@dolbomcare.com", "password": "password123"}
)
if caregiver_response.status_code != 200:
    print(f"❌ 로그인 실패: {caregiver_response.text}")
    sys.exit(1)

caregiver_data = caregiver_response.json()
caregiver_token = caregiver_data.get('access_token')
caregiver_id = caregiver_data.get('user', {}).get('id')
caregiver_center = caregiver_data.get('user', {}).get('center_id')
print(f"✅ 요양사 로그인 성공")
print(f"   - 요양사 ID: {caregiver_id}")
print(f"   - 센터 ID: {caregiver_center}")
print()

# 2. 센터장 로그인
print("2️⃣ 센터장 로그인")
print("-" * 60)
manager_response = requests.post(
    f"{BASE_URL}/users/login",
    json={"email": "manager@dolbomcare.com", "password": "password123"}
)
if manager_response.status_code != 200:
    print(f"❌ 로그인 실패: {manager_response.text}")
    sys.exit(1)

manager_data = manager_response.json()
manager_token = manager_data.get('access_token')
manager_id = manager_data.get('user', {}).get('id')
manager_center = manager_data.get('user', {}).get('center_id')
print(f"✅ 센터장 로그인 성공")
print(f"   - 센터장 ID: {manager_id}")
print(f"   - 센터 ID: {manager_center}")
print()

# 3. 센터 확인
if caregiver_center != manager_center:
    print(f"⚠️ 경고: 센터 ID가 다릅니다! (요양사: {caregiver_center}, 센터장: {manager_center})")
else:
    print(f"✅ 같은 센터: {caregiver_center}")
print()

# 4. 요양사가 음성 기록 생성
print("3️⃣ 요양사가 음성 기록 생성")
print("-" * 60)
record_response = requests.post(
    f"{BASE_URL}/records/create",
    headers={"Authorization": f"Bearer {caregiver_token}"},
    json={
        "caregiver_id": caregiver_id,
        "resident_id": 1,
        "service_type": "basic_care",
        "notes": "테스트: 아침 기본 요양 - 2026-10-02"
    }
)
if record_response.status_code != 200:
    print(f"❌ 기록 생성 실패: {record_response.text}")
    sys.exit(1)

record_data = record_response.json()
data = record_data.get('data', {})
record_id = data.get('record_id')
billing_id = data.get('billing_id')
billing_amount = data.get('billing_amount')
print(f"✅ 음성 기록 생성 성공")
print(f"   - 음성 기록 ID: {record_id}")
print(f"   - 자동 생성된 청부 ID: {billing_id}")
print(f"   - 청부액: ₩{billing_amount:,}")
print()

# 5. 요양사 관점에서 청부 조회
print("4️⃣ 요양사 관점: 자신의 청부 조회")
print("-" * 60)
caregiver_billing = requests.get(
    f"{BASE_URL}/billing/?caregiver_id={caregiver_id}",
    headers={"Authorization": f"Bearer {caregiver_token}"}
)
if caregiver_billing.status_code != 200:
    print(f"❌ 조회 실패: {caregiver_billing.text}")
    sys.exit(1)

caregiver_response_data = caregiver_billing.json()
caregiver_bills = caregiver_response_data if isinstance(caregiver_response_data, list) else caregiver_response_data.get('billings', caregiver_response_data.get('data', []))
found = False
for bill in caregiver_bills:
    if bill['id'] == billing_id:
        print(f"✅ 청부 찾음: ID={bill['id']}, 상태={bill['status']}, 액: ₩{bill['amount']:,}")
        found = True
        break
if not found:
    print(f"❌ 청부를 찾을 수 없습니다!")
print(f"   (총 {len(caregiver_bills)}개 청부 중)")
print()

# 6. 센터장 관점에서 모든 청부 조회
print("5️⃣ 센터장 관점: 센터 전체 청부 조회")
print("-" * 60)
manager_billing = requests.get(
    f"{BASE_URL}/billing/?center_id={caregiver_center}",
    headers={"Authorization": f"Bearer {manager_token}"}
)
if manager_billing.status_code != 200:
    print(f"❌ 조회 실패: {manager_billing.text}")
    sys.exit(1)

manager_response_data = manager_billing.json()
all_bills = manager_response_data if isinstance(manager_response_data, list) else manager_response_data.get('billings', manager_response_data.get('data', []))
print(f"📊 전체 청부 수: {len(all_bills)}")
print()

# 7. 새로 생성된 청부가 센터장에게 보이는지 확인
print("6️⃣ 데이터 일치성 검증")
print("-" * 60)
manager_found = False
for bill in all_bills:
    if bill['id'] == billing_id:
        manager_found = True
        print(f"✅ 센터장이 청부를 볼 수 있습니다!")
        print(f"   - 청부 ID: {bill['id']}")
        print(f"   - 요양사 ID: {bill.get('caregiver_id')} (생성자 ID: {caregiver_id})")
        print(f"   - 이용자 ID: {bill.get('resident_id')}")
        print(f"   - 상태: {bill['status']}")
        print(f"   - 금액: ₩{bill['amount']:,}")
        print(f"   - 서비스 유형: {bill.get('service_type')}")

        # 금액 일치성 확인
        if bill['amount'] == billing_amount:
            print(f"   ✅ 금액 일치: ₩{billing_amount:,}")
        else:
            print(f"   ❌ 금액 불일치: 생성={billing_amount}, 조회={bill['amount']}")
        break

if not manager_found:
    print(f"❌ 센터장이 청부를 볼 수 없습니다!")
    print(f"   - 생성된 청부 ID: {billing_id}")
    print(f"   - 센터장이 조회한 청부 ID들: {[b['id'] for b in all_bills[:5]]}...")

print()
print("=" * 60)
print("✨ 테스트 완료")
print("=" * 60)

# Save test data
with open('test_data.json', 'w', encoding='utf-8') as f:
    json.dump({
        'caregiver_id': caregiver_id,
        'manager_id': manager_id,
        'center_id': caregiver_center,
        'record_id': record_id,
        'billing_id': billing_id,
        'billing_amount': billing_amount,
        'caregiver_token': caregiver_token,
        'manager_token': manager_token,
    }, f, ensure_ascii=False, indent=2)
