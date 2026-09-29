# 🚀 dolbomcare 웹 버전 - 실행 가이드

웹 버전(Next.js)으로 완전히 전환되었습니다! Backend와 웹 앱을 실행하세요.

---

## ✅ 준비 사항

- Python 3.11+ (Backend 실행용)
- Node.js 18+ (웹 앱 실행용)
- PostgreSQL 15 (선택사항 - SQLite로 자동 생성됨)

---

## 🎯 1단계: Backend 실행

### PowerShell에서 Backend 폴더 열기

```powershell
cd D:\dolbomcare\backend
.\run.ps1
```

**자동으로 실행되는 작업:**
- ✅ 가상환경 활성화
- ✅ 패키지 설치
- ✅ 데이터베이스 테이블 생성
- ✅ 테스트 계정 자동 생성
- ✅ FastAPI 서버 시작 (포트 8000)

**테스트 계정:**
- 요양사: `caregiver@dolbomcare.com` / `password123`
- 센터장: `manager@dolbomcare.com` / `password123`

---

## 🌐 2단계: 웹 앱 실행

### 새 PowerShell 창에서 웹 폴더 열기

```powershell
cd D:\dolbomcare\web
.\run.ps1
```

**또는 수동으로:**

```powershell
npm install
npm run dev
```

**웹 앱이 실행되면:**
- 🌐 웹 앱 URL: `http://localhost:3000`
- 🔗 자동으로 브라우저 열림

---

## 🔐 3단계: 로그인 테스트

### 테스트 계정 1: 요양사

```
이메일: caregiver@dolbomcare.com
비밀번호: password123
역할: 요양사
```

1. 웹 앱에서 위 정보 입력
2. **로그인** 버튼 클릭
3. ✅ 대시보드로 이동

### 테스트 계정 2: 센터장

```
이메일: manager@dolbomcare.com
비밀번호: password123
역할: 센터장 (로그인 페이지에서 선택 - 아직 구현 중)
```

---

## 📊 구조

```
D:\dolbomcare\
├── backend/          (FastAPI 백엔드)
│   ├── app/
│   ├── main.py
│   ├── run.ps1
│   └── create_test_accounts.py
│
├── web/             (Next.js 웹 프론트엔드) ← NEW!
│   ├── app/
│   │   ├── page.tsx           (라우팅 로직)
│   │   ├── layout.tsx         (루트 레이아웃)
│   │   ├── login/             (로그인 페이지)
│   │   └── dashboard/         (대시보드 페이지)
│   ├── lib/
│   │   ├── api.ts             (API 클라이언트)
│   │   └── auth-context.tsx   (인증 상태 관리)
│   ├── package.json
│   ├── .env.local             (API URL)
│   └── run.ps1
│
└── mobile/          (React Native - 보관용, 현재 사용 안 함)
```

---

## ⚙️ 기술 스택

### Backend
- **Framework:** FastAPI
- **Database:** SQLite (개발용) / PostgreSQL 15 (프로덕션)
- **Auth:** JWT + bcrypt
- **ORM:** SQLAlchemy

### Web Frontend
- **Framework:** Next.js 16 (App Router)
- **Styling:** Tailwind CSS
- **State Management:** Context API
- **HTTP Client:** Axios
- **Storage:** LocalStorage (토큰)

---

## 🧪 API 테스트 (선택사항)

### Swagger UI로 테스트
1. `http://localhost:8000/docs` 열기
2. `POST /api/v1/auth/login` 클릭
3. 요청 본문:
```json
{
  "email": "caregiver@dolbomcare.com",
  "password": "password123"
}
```
4. **Execute** 클릭 → 응답에서 `access_token` 확인

---

## 🚀 배포 준비

### Vercel로 배포 (웹)

```bash
# 1. 최상위 폴더를 Git 저장소로 설정
cd D:\dolbomcare
git add .
git commit -m "Web version with Next.js"
git push origin main

# 2. Vercel CLI 설치
npm i -g vercel

# 3. 배포
cd web
vercel
```

**Vercel 배포 후:**
- 웹 앱은 `https://dolbomcare.vercel.app` (예시)에서 접근 가능
- Backend API URL을 프로덕션 서버로 변경
- 환경 변수 설정: `NEXT_PUBLIC_API_URL=https://your-backend.com/api/v1`

---

## 📊 현재 상태

### ✅ 웹 버전 완성

- [x] Next.js 프로젝트 설정
- [x] 로그인 페이지
  - 역할 선택 (요양사/센터장)
  - 이메일/비밀번호 입력
  - Backend API 연동
  - 오류 메시지 표시
- [x] 대시보드 페이지
  - 사용자 정보 표시
  - 역할별 메뉴 (구현 예정)
  - 로그아웃 기능
- [x] 인증 상태 관리
  - Context API 사용
  - LocalStorage 토큰 저장
  - 인증 기반 라우팅
- [x] 반응형 디자인 (모바일/태블릿/데스크톱)
- [x] Dark Mode 지원

### ✅ Backend

- [x] FastAPI 서버
- [x] JWT 인증
- [x] 테스트 계정 자동 생성
- [x] Swagger API Docs

### 🔜 다음 단계 (Phase 2)

- [ ] 음성 기록 기능
- [ ] 이용자 관리 (CRUD)
- [ ] 건강 지표 추적
- [ ] 보고서 생성
- [ ] PostgreSQL 마이그레이션
- [ ] 프로덕션 배포

---

## ⚠️ 문제 해결

### 웹 앱이 로그인 페이지를 계속 보여줌
```
확인사항:
1. Backend가 http://localhost:8000에서 실행 중인지 확인
2. 네트워크 탭에서 /api/v1/auth/login 요청 상태 확인
3. 브라우저 콘솔에서 에러 메시지 확인
```

### CORS 오류 발생
```
해결: Backend의 main.py에 CORS 설정이 있는지 확인
allow_origins=["*"] 로 설정되어 있어야 함
```

### 로그인 후 대시보드가 로드되지 않음
```
확인사항:
1. 토큰이 LocalStorage에 저장되었는지 확인 (F12 → Application)
2. 사용자 정보가 올바른지 확인
3. 네트워크 탭에서 요청 실패 여부 확인
```

---

## 🎉 성공 지표

로그인과 대시보드가 완성되면:

1. ✅ Backend가 포트 8000에서 실행
2. ✅ 웹 앱이 포트 3000에서 실행
3. ✅ 로그인 페이지 표시
4. ✅ 테스트 계정으로 로그인 성공
5. ✅ 대시보드 페이지 표시
6. ✅ 로그아웃 후 로그인 페이지로 돌아감

---

## 🔗 유용한 링크

- [Next.js 공식 문서](https://nextjs.org/docs)
- [Tailwind CSS](https://tailwindcss.com)
- [FastAPI 공식 문서](https://fastapi.tiangolo.com)
- [Vercel 배포 가이드](https://vercel.com/docs)

---

## 📝 다음 작업

로그인 및 대시보드 테스트 완료 후:

```
1. 음성 기록 기능 구현
2. 이용자 데이터 관리 API
3. 대시보드 데이터 조회
4. PostgreSQL 연동
5. 프로덕션 배포 (Vercel + 클라우드 Backend)
```

Happy coding! 🚀
