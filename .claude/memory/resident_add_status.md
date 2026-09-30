---
name: resident_add_feature_status
description: 이용자 추가 기능 진행 현황
metadata:
  type: project
---

## 이용자 추가 기능 - 현황

### ✅ 완료된 부분
1. **나이 자동 계산** - 생년월일 입력 시 자동으로 나이 계산됨
2. **422 오류 해결** - center_id 기본값 설정으로 해결
3. **디버깅 로그** - 상세한 console.log 추가됨

### 🔄 진행 중

**이용자 추가 API 흐름:**
```
Frontend (resident_management.html)
  ├─ 사용자 정보 입력
  ├─ calculateAge() - 생년월일 → 나이 자동 계산 ✅
  ├─ handleAddResident() - 폼 제출
  └─ POST /api/v1/residents/?user_role=center_manager
       └─ Backend (models.py + api/residents.py)
           ├─ 권한 검증 (center_manager만 가능) ✅
           ├─ center_id 유효성 확인 ✅
           ├─ 중복 확인 (name + birth_date)
           └─ 데이터베이스에 저장
```

### 📝 테스트 항목 (내일)

1. **센터장 계정 이용자 추가**
   - 계정: manager@test.com / password123
   - 역할: center_manager
   - 예상: 성공 ✅

2. **요양사 계정 이용자 추가 시도**
   - 계정: caregiver@test.com / password123
   - 역할: caregiver
   - 예상: 버튼 비표시 또는 403 오류 ✅

3. **입력값 검증**
   - 필수 필드: name, birth_date, age, care_grade, client_type, health_status
   - 선택 필드: guardian_id (optional)
   - 동일 이용자 중복 확인

### 🐛 알려진 문제

1. **center_id 임시 해결책** 
   - 현재: 모든 사용자에게 center_id=1 강제 설정
   - 해결: 백엔드 uvicorn 재시작 후 임시 해결책 제거

2. **오류 응답 상세**
   - 422 오류 시 detail이 Array로 반환됨
   - 사용자에게 명확한 오류 메시지 표시 필요할 수 있음

### 📋 내일 체크리스트

```
내일 처음 할 때:
1. 브라우저 캐시 완전 삭제 (Ctrl+Shift+Delete)
2. 백엔드 프로세스 완전 재시작 (Get-Process | Stop-Process -Force)
3. 로그아웃 후 다시 로그인
4. F12 Console 열어놓고 이용자 추가 시도
5. center_id 값이 제대로 전송되는지 확인
```

### 🔗 관련 파일
- Frontend: D:\dolbomcare\scratchpad\resident_management.html
- Backend Model: D:\dolbomcare\backend\app\models.py (Resident class)
- Backend API: D:\dolbomcare\backend\app\api\residents.py (create_resident 함수)
- Schema: D:\dolbomcare\backend\app\schemas.py (ResidentCreate)
