import requests
import json

BASE_URL = "http://localhost:8000/api/v1"

# 로그인
caregiver = requests.post(
    f"{BASE_URL}/users/login",
    json={"email": "caregiver@dolbomcare.com", "password": "password123"}
).json()
token = caregiver['access_token']

# 청부 조회 엔드포인트 테스트
print("청부 조회 엔드포인트 테스트:")
print()

# 1. 기본 조회
resp = requests.get(
    f"{BASE_URL}/billing/",
    headers={"Authorization": f"Bearer {token}"}
)
print(f"1. GET /api/v1/billing/")
print(f"   상태: {resp.status_code}")
print(f"   응답 타입: {type(resp.json())}")
if resp.status_code == 200:
    data = resp.json()
    if isinstance(data, list):
        print(f"   개수: {len(data)}")
        if data:
            print(f"   첫 항목: {json.dumps(data[0], indent=2, ensure_ascii=False)[:300]}")
    else:
        print(f"   전체 응답: {json.dumps(data, indent=2, ensure_ascii=False)[:500]}")
else:
    print(f"   오류: {resp.text}")
print()

# 2. caregiver_id로 조회
resp = requests.get(
    f"{BASE_URL}/billing/?caregiver_id=1",
    headers={"Authorization": f"Bearer {token}"}
)
print(f"2. GET /api/v1/billing/?caregiver_id=1")
print(f"   상태: {resp.status_code}")
if resp.status_code == 200:
    data = resp.json()
    if isinstance(data, list):
        print(f"   개수: {len(data)}")
    else:
        print(f"   응답 구조: {list(data.keys()) if isinstance(data, dict) else 'list'}")
        print(f"   상세: {json.dumps(data, indent=2, ensure_ascii=False)[:300]}")
else:
    print(f"   오류: {resp.text}")
print()

# 3. center_id로 조회
resp = requests.get(
    f"{BASE_URL}/billing/?center_id=1",
    headers={"Authorization": f"Bearer {token}"}
)
print(f"3. GET /api/v1/billing/?center_id=1")
print(f"   상태: {resp.status_code}")
if resp.status_code == 200:
    data = resp.json()
    if isinstance(data, list):
        print(f"   개수: {len(data)}")
    else:
        print(f"   응답 구조: {list(data.keys()) if isinstance(data, dict) else 'list'}")
        print(f"   상세: {json.dumps(data, indent=2, ensure_ascii=False)[:300]}")
else:
    print(f"   오류: {resp.text}")
