# 돌봄케어 테스트 가이드 (2026-10-01)

## ✅ 완료된 수정사항

### 1. center_id 완전 해결
- **백엔드**: 로그인 API에서 center_id 반환 ✅
- **프론트엔드**: 임시 해결책 제거, center_id 자동 저장 ✅

### 2. 이용자 추가 기능 정상 작동
- **API 테스트**: 422 오류 없이 성공 ✅
- **권한 검증**: center_manager 역할 확인 ✅

---

## 🧪 테스트 항목 (웹 브라우저)

### 1단계: 브라우저 캐시 삭제
```
Ctrl + Shift + Delete
→ "모든 시간" 선택
→ "쿠키 및 기타 사이트 데이터" 체크
→ 캐시된 이미지 및 파일 체크
→ 데이터 삭제
```

### 2단계: 로그인 페이지 열기
```
브라우저: D:\dolbomcare\scratchpad\login.html 열기
또는: file:///D:/dolbomcare/scratchpad/login.html
```

### 3단계: 센터장 계정으로 로그인
```
이메일: manager@test.com
비밀번호: password123
```

### 4단계: F12 Console 확인
```
F12 → Console 탭
"✅ 저장된 user:" 메시지 확인
→ center_id: 1 포함되어 있는지 확인
```

예상 결과:
```javascript
{
  "id": 2,
  "email": "manager@test.com",
  "full_name": "센터장",
  "role": "center_manager",
  "center_id": 1,  // ← 이 부분이 있어야 함!
  "is_active": true,
  "created_at": "2026-09-29T..."
}
```

### 5단계: 이용자 관리 페이지 열기
```
D:\dolbomcare\scratchpad\resident_management.html
또는: file:///D:/dolbomcare/scratchpad/resident_management.html
```

### 6단계: 이용자 추가 테스트
```
1. [이용자 추가] 버튼 클릭
2. 다음 정보 입력:
   - 이름: 테스트_홍길동
   - 생년월일: 1950-05-15
   - 나이: 74 (자동 계산됨)
   - 등급: 3
   - 유형: 일반
   - 건강상태: 정상
3. [등록하기] 버튼 클릭
4. F12 Console 확인
```

예상 결과:
```
✅ 로그아웃 성공이 표시되고
테이블에 새 이용자가 추가됨
```

### 7단계: 요양사 계정 권한 확인
```
로그아웃
이메일: caregiver@test.com
비밀번호: password123
로그인

이용자 관리 페이지 열기
→ [이용자 추가] 버튼이 보이지 않아야 함
```

---

## 🐛 문제 발생 시

### 422 오류
- F12 → Network → POST /api/v1/residents 클릭
- Response 확인
- 필수 필드가 모두 입력되었는지 확인

### center_id가 없음
- 캐시 삭제 후 다시 로그인
- `Ctrl+Shift+Delete` 실행

### 로그인 실패
- 백엔드 실행 확인: `curl http://localhost:8000/`
- 이메일과 비밀번호 재확인

---

## 📋 주요 파일

| 파일 | 목적 | 상태 |
|------|------|------|
| backend/app/api/users.py | 로그인 API | ✅ center_id 반환 |
| scratchpad/login.html | 로그인 UI | ✅ 임시 해결책 제거 |
| scratchpad/resident_management.html | 이용자 관리 | ✅ center_id 사용 |

---

## 📞 다음 단계

1. **테스트 완료 후 보고**
2. **모바일 앱 연동** (필요시)
3. **다음 기능 구현** (예: 음성 녹음)
