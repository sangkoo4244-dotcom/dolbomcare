# 🚀 dolbomcare 로그인 완성 - 실행 가이드

로그인 기능이 완성되었습니다! 이 가이드를 따라 Backend와 Mobile을 실행하세요.

---

## ✅ 준비 사항

- Python 3.11+ 설치
- Node.js 18+ 설치
- PostgreSQL 15 설치 (선택사항 - SQLite로 자동 생성됨)

---

## 🎯 1단계: Backend 실행

### PowerShell에서 Backend 폴더 열기

```powershell
cd D:\dolbomcare\backend
.\run.ps1
```

**자동으로 실행되는 작업:**
1. ✅ 가상환경 활성화
2. ✅ 패키지 설치 (requirements.txt)
3. ✅ 데이터베이스 테이블 생성
4. ✅ 테스트 계정 생성:
   - 이메일: `caregiver@dolbomcare.com`
   - 비밀번호: `password123`
   - 역할: 요양사

   - 이메일: `manager@dolbomcare.com`
   - 비밀번호: `password123`
   - 역할: 센터장

5. ✅ FastAPI 서버 시작

**서버가 실행되면:**
- 🌐 API 기본 URL: `http://localhost:8000/api/v1`
- 📖 Swagger API Docs: `http://localhost:8000/docs`
- ✔️ 로그인 엔드포인트: `POST http://localhost:8000/api/v1/auth/login`

---

## 📱 2단계: Mobile 실행

### 새 PowerShell 창에서 Mobile 폴더 열기

```powershell
cd D:\dolbomcare\mobile
.\run.ps1
```

**또는 수동으로:**

```powershell
npm install
npx expo start
```

**Expo 시작 후 키보드 입력:**
- `w` → 웹 브라우저에서 실행 (권장)
- `a` → Android Emulator에서 실행
- `i` → iOS Simulator에서 실행

---

## 🔐 3단계: 로그인 테스트

### 테스트 계정 1: 요양사 (Caregiver)

```
이메일: caregiver@dolbomcare.com
비밀번호: password123
역할: 요양사 (선택됨)
```

1. Mobile 앱에서 위 정보 입력
2. **로그인** 버튼 클릭
3. ✅ 성공하면 **대시보드**로 이동

### 테스트 계정 2: 센터장 (Manager)

```
이메일: manager@dolbomcare.com
비밀번호: password123
역할: 센터장 (선택)
```

1. 역할을 **센터장**으로 변경
2. Mobile 앱에서 위 정보 입력
3. **로그인** 버튼 클릭
4. ✅ 성공하면 **매니저 화면**으로 이동 (아직 구현 중)

---

## 🧪 4단계: Backend API 테스트 (선택사항)

Swagger UI를 통해 로그인 엔드포인트 테스트:

1. 브라우저 열기: `http://localhost:8000/docs`
2. **POST /api/v1/auth/login** 찾기
3. **Try it out** 클릭
4. 요청 본문 입력:

```json
{
  "email": "caregiver@dolbomcare.com",
  "password": "password123"
}
```

5. **Execute** 클릭
6. 응답에서 `access_token` 확인

---

## 📊 현재 상태

### ✅ 완료된 기능

- [x] Backend FastAPI 구조
- [x] SQLite 데이터베이스
- [x] User 모델 및 테이블
- [x] JWT 토큰 인증
- [x] 비밀번호 해싱 (bcrypt)
- [x] /auth/login 엔드포인트
- [x] /auth/register 엔드포인트
- [x] 테스트 계정 자동 생성
- [x] Mobile 로그인 화면
- [x] AsyncStorage 토큰 저장
- [x] 인증 기반 라우팅
- [x] 대시보드 화면
- [x] 로그아웃 기능

### 🔜 다음 단계 (Phase 2)

- [ ] 센터 관리 기능
- [ ] 이용자(Resident) 관리
- [ ] 음성 기록 기능 (음성-텍스트 변환)
- [ ] 일일 기록 저장 및 조회
- [ ] 건강 지표 추적
- [ ] 센터장 대시보드
- [ ] PostgreSQL 마이그레이션

---

## ⚠️ 문제 해결

### Backend 실행 오류
```
ModuleNotFoundError: No module named 'app'
```
**해결:** Backend 폴더 경로가 맞는지 확인하고, 가상환경이 활성화되었는지 확인

### Mobile 빌드 오류
```
expo: command not found
```
**해결:** `npm install -g expo-cli` 실행 후 다시 시도

### 로그인 실패
```
Network error
```
**해결:**
- Backend가 `http://localhost:8000`에서 실행 중인지 확인
- Firewall이 포트 8000을 차단하지 않는지 확인
- Mobile의 API_URL이 올바른지 확인

---

## 📝 파일 구조

```
D:\dolbomcare\
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── health.py      # 상태 확인 엔드포인트
│   │   │   └── users.py       # 로그인/회원가입 엔드포인트
│   │   ├── models.py          # SQLAlchemy 모델
│   │   ├── schemas.py         # Pydantic 스키마
│   │   └── database.py        # 데이터베이스 설정
│   ├── main.py                # FastAPI 앱 진입점
│   ├── requirements.txt        # Python 의존성
│   ├── create_test_accounts.py # 테스트 계정 생성
│   └── run.ps1               # Backend 실행 스크립트
│
└── mobile/
    ├── src/app/
    │   ├── _layout.tsx           # 루트 레이아웃 (인증 흐름)
    │   ├── index.tsx             # 로그인 화면
    │   └── (dashboard)/
    │       ├── _layout.tsx       # 대시보드 레이아웃
    │       ├── dashboard.tsx     # 요양사 대시보드
    │       └── manager.tsx       # 센터장 대시보드
    ├── package.json              # Node 의존성
    └── run.ps1                  # Mobile 실행 스크립트
```

---

## 🎉 성공 지표

로그인이 완성되면:

1. ✅ Backend가 포트 8000에서 실행
2. ✅ 테스트 계정 2개 생성됨
3. ✅ Mobile에서 로그인 가능
4. ✅ 로그인 후 대시보드 표시
5. ✅ 로그아웃 후 로그인 화면으로 돌아감
6. ✅ 잘못된 자격증명에서 오류 메시지 표시

---

## 🔗 다음 작업

로그인 테스트 완료 후:

```
1. PostgreSQL 연동 (선택사항)
2. 음성 기록 기능 구현
3. 데이터 조회 API 구현
4. 센터 관리 기능 추가
```

Happy coding! 🚀
