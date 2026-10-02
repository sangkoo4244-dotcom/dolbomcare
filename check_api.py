import requests
import json

BASE_URL = "http://localhost:8000/api/v1"

# 요양사 로그인
print("로그인 중...")
caregiver = requests.post(
    f"{BASE_URL}/users/login",
    json={"email": "caregiver@dolbomcare.com", "password": "password123"}
).json()

token = caregiver['access_token']
caregiver_id = caregiver['user']['id']
print(f"요양사 ID: {caregiver_id}")

# 음성 기록 생성 시도
print("\n🎤 음성 기록 생성 시도...")
response = requests.post(
    f"{BASE_URL}/records/create",
    headers={"Authorization": f"Bearer {token}"},
    json={
        "caregiver_id": caregiver_id,
        "resident_id": 1,
        "service_type": "basic_care",
        "notes": "테스트"
    }
)

print(f"상태 코드: {response.status_code}")
print(f"응답 내용:")
print(json.dumps(response.json(), indent=2, ensure_ascii=False))
