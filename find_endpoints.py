import requests
import json

BASE_URL = "http://localhost:8000/api/v1"

# 로그인
print("로그인 중...")
caregiver = requests.post(
    f"{BASE_URL}/users/login",
    json={"email": "caregiver@dolbomcare.com", "password": "password123"}
).json()
token = caregiver['access_token']
caregiver_id = caregiver['user']['id']

# 청부 조회 엔드포인트 확인
print("청부 조회 엔드포인트 확인...\n")
endpoints = [
    "/billings",
    "/billing",
    "/billings/mine",
    "/records/billings",
    f"/billings?caregiver_id={caregiver_id}",
]

for endpoint in endpoints:
    try:
        resp = requests.get(
            f"{BASE_URL}{endpoint}",
            headers={"Authorization": f"Bearer {token}"}
        )
        print(f"🔍 {endpoint}")
        print(f"   상태: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, dict):
                print(f"   응답 구조: {list(data.keys())}")
                print(f"   상세: {json.dumps(data, indent=4, ensure_ascii=False)[:300]}")
            else:
                print(f"   응답: {str(data)[:300]}")
        else:
            print(f"   오류: {resp.text[:200]}")
    except Exception as e:
        print(f"🔍 {endpoint}")
        print(f"   예외: {e}")
    print()
