import requests
import json

BASE_URL = "http://localhost:8000/api/v1"

# 로그인
caregiver = requests.post(
    f"{BASE_URL}/users/login",
    json={"email": "caregiver@dolbomcare.com", "password": "password123"}
).json()
caregiver_token = caregiver['access_token']
caregiver_id = caregiver['user']['id']

manager = requests.post(
    f"{BASE_URL}/users/login",
    json={"email": "manager@dolbomcare.com", "password": "password123"}
).json()
manager_token = manager['access_token']
manager_center = manager['user']['center_id']

print("=" * 70)
print("🎤 음성 기록 API 비교")
print("=" * 70)
print()

# 요양사 관점
print(f"1️⃣ 요양사 ID={caregiver_id} 관점")
resp = requests.get(
    f"{BASE_URL}/records/today?caregiver_id={caregiver_id}",
    headers={"Authorization": f"Bearer {caregiver_token}"}
)
if resp.status_code == 200:
    data = resp.json()
    count = data.get('total_records', 0)
    records = data.get('records', [])
    print(f"   GET /records/today?caregiver_id={caregiver_id}")
    print(f"   개수: {count}")
    print(f"   기록:")
    for r in records[:3]:
        print(f"      - ID={r.get('id')}, 이용자={r.get('resident_id')}, 요양사={r.get('caregiver_id')}")
    if len(records) > 3:
        print(f"      ... 외 {len(records)-3}개")
else:
    print(f"   오류: {resp.status_code}")
print()

# 센터장 관점
print(f"2️⃣ 센터장 (센터 ID={manager_center}) 관점")
resp = requests.get(
    f"{BASE_URL}/records/today/center?center_id={manager_center}",
    headers={"Authorization": f"Bearer {manager_token}"}
)
if resp.status_code == 200:
    data = resp.json()
    count = data.get('total_records', 0)
    records = data.get('records', [])
    print(f"   GET /records/today/center?center_id={manager_center}")
    print(f"   개수: {count}")
    print(f"   기록:")
    for r in records[:5]:
        print(f"      - ID={r.get('id')}, 이용자={r.get('resident_id')}, 요양사={r.get('caregiver_id')}")
    if len(records) > 5:
        print(f"      ... 외 {len(records)-5}개")
else:
    print(f"   오류: {resp.status_code}")
print()

print("=" * 70)
print("분석:")
print("=" * 70)
print("요양사는 1개만 보는데 (caregiver_id=1인 오늘 기록)")
print("센터장은 7개를 보는 이유:")
print("  → 센터 1의 모든 이용자 중에 오늘 6명이 기록을 가짐")
print("  → 또는 과거 기록이 섞여 있음 (시간 필터링 문제)")
print("=" * 70)
