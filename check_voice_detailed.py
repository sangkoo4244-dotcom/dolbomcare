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
print("🎤 음성 기록 API 상세 비교")
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
    print(json.dumps(data, indent=2, ensure_ascii=False)[:1000])
else:
    print(f"오류: {resp.status_code} - {resp.text[:500]}")
print()

# 센터장 관점
print(f"2️⃣ 센터장 (센터 ID={manager_center}) 관점")
resp = requests.get(
    f"{BASE_URL}/records/today/center?center_id={manager_center}",
    headers={"Authorization": f"Bearer {manager_token}"}
)
if resp.status_code == 200:
    data = resp.json()
    print(json.dumps(data, indent=2, ensure_ascii=False)[:1000])
else:
    print(f"오류: {resp.status_code} - {resp.text[:500]}")
