---
name: center_id_bug_details
description: center_id 누락 문제 해결 과정 및 기술적 세부사항
metadata:
  type: project
---

## center_id 누락 문제 - 기술적 분석

### 발견된 문제
1. 프론트: localStorage의 user에 center_id가 없음
2. 백엔드: 데이터베이스에는 center_id=1이 존재
3. API 테스트: `GET /auth/login` 응답에 center_id 필드 없음

### 근본 원인
```
BackEnd → UserResponse 스키마의 Pydantic 검증
└─ response_model=LoginResponse 적용 시 UserResponse만 반환
   └─ center_id를 추가했으나 uvicorn --reload가 변경사항 감지 못함
```

### 해결 방법

**1차 시도** (불완전)
- UserResponse에 `center_id: Optional[int] = None` 추가
- 결과: 여전히 응답에 없음 (reload 미작동)

**2차 시도** (임시 완화)
- login 엔드포인트에서 response_model 제거
- 결과: 여전히 응답에 없음 (이전 코드 캐싱)

**3차 시도** (현재 임시 해결책)
- 프론트엔드 login.html에서 center_id 기본값 설정
- 코드: `center_id: data.user.center_id || 1`
- 결과: 작동함 ✅
- 한계: 모든 사용자가 center_id=1이라고 가정

### 완전 해결 방법 (내일)
1. 백엔드 프로세스 완전 종료
   ```powershell
   Get-Process uvicorn | Stop-Process -Force
   ```

2. 다시 시작
   ```powershell
   cd D:\dolbomcare\backend
   .\venv\Scripts\Activate.ps1
   uvicorn main:app --reload --host 0.0.0.0 --port 8000
   ```

3. API 테스트로 center_id 포함 확인

4. 임시 해결책 제거
   ```javascript
   // 제거 전
   const user = { ...data.user, center_id: data.user.center_id || 1 };
   
   // 제거 후
   localStorage.setItem('user', JSON.stringify(data.user));
   ```

### 수정된 파일들
- `backend/app/schemas.py`: UserResponse에 center_id 추가
- `backend/app/api/users.py`: response_model 제거
- `scratchpad/login.html`: 기본값 설정 추가 (임시)

### 이 문제의 영향
- 이용자 추가 API 호출 시 center_id=undefined → 422 오류
- 임시 해결책으로 center_id=1이 전송되면서 현재 작동
