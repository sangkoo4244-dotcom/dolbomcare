import requests
import json

BASE_URL = "http://localhost:8000/api/v1"

# 요양사 1 로그인
caregiver = requests.post(
    f"{BASE_URL}/users/login",
    json={"email": "caregiver@dolbomcare.com", "password": "password123"}
).json()

caregiver_token = caregiver['access_token']
caregiver_id = caregiver['user']['id']

print("=" * 70)
print(f"🧑‍⚕️ 요양사 ID={caregiver_id} 상세 데이터")
print("=" * 70)
print()

# 음성 기록 조회
print("1️⃣ 음성 기록 조회")
resp = requests.get(
    f"{BASE_URL}/records/today?caregiver_id={caregiver_id}",
    headers={"Authorization": f"Bearer {caregiver_token}"}
)

if resp.status_code == 200:
    data = resp.json()
    print(f"   총 기록: {data.get('total_records')}개")
    print(f"   합계 정산액: ₩{data.get('total_billing_amount'):,}")
    print()
    print("   상세 기록:")
    for r in data.get('records', []):
        print(f"      - ID={r['id']}, 이용자={r['resident_id']}, 금액=₩{r.get('billing_amount', 0):,}")
else:
    print(f"   오류: {resp.status_code}")
print()

# 청부 기록 조회
print("2️⃣ 청부 기록 조회")
resp = requests.get(
    f"{BASE_URL}/billing/?caregiver_id={caregiver_id}",
    headers={"Authorization": f"Bearer {caregiver_token}"}
)

if resp.status_code == 200:
    data = resp.json()
    if isinstance(data, list):
        billings = data
    else:
        billings = data.get('billings', data.get('data', []))

    print(f"   총 청부: {len(billings)}개")
    total = sum(b.get('amount', 0) for b in billings)
    print(f"   합계: ₩{total:,}")
else:
    print(f"   오류: {resp.status_code}")
