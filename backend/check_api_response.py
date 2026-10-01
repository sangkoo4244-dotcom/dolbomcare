#!/usr/bin/env python3
"""API 응답 직접 확인"""

import requests

caregiver_id = 2  # 요양사 ID

print('\n' + '=' * 80)
print('🔍 API 응답 직접 확인')
print('=' * 80)

# /records/today
try:
    resp = requests.get(f'http://127.0.0.1:8000/records/today?caregiver_id={caregiver_id}')
    data = resp.json()
    amount = data.get('total_billing_amount')
    print(f'\n📱 /records/today:')
    print(f'  total_billing_amount: ₩{amount:,}')
    print(f'  total_records: {data.get("total_records")}')
except Exception as e:
    print(f'  ❌ 오류: {e}')

# /records/recent
try:
    resp = requests.get(f'http://127.0.0.1:8000/records/recent?caregiver_id={caregiver_id}&days=7')
    data = resp.json()
    amount = data.get('total_billing_amount')
    print(f'\n📅 /records/recent:')
    print(f'  total_billing_amount: ₩{amount:,}')
    print(f'  total_records: {data.get("total_records")}')
except Exception as e:
    print(f'  ❌ 오류: {e}')

# /records/all
try:
    resp = requests.get(f'http://127.0.0.1:8000/records/all?caregiver_id={caregiver_id}')
    data = resp.json()
    amount = data.get('total_billing_amount')
    print(f'\n📋 /records/all:')
    print(f'  total_billing_amount: ₩{amount:,}')
    print(f'  total_records: {data.get("total_records")}')
except Exception as e:
    print(f'  ❌ 오류: {e}')

print('\n' + '=' * 80 + '\n')
