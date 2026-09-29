# MVP 개발 시작 가이드

**상태**: 초기 코드 생성 완료  
**시작일**: 2026년 10월 (K-스타트업 선정 후)  
**예상 완성**: 2026년 12월 (2개월)

---

## 🚀 현재 준비 상황

### ✅ 완료된 것
```
Backend (FastAPI):
├─ main.py - 애플리케이션 진입점
├─ database.py - PostgreSQL 연결
├─ models.py - 11개 테이블 ORM 모델
├─ schemas.py - 요청/응답 스키마
├─ app/api/health.py - 헬스체크 API
└─ app/api/users.py - 인증/회원가입 API

Mobile (React Native Expo):
├─ src/App.tsx - 라우팅 & 인증 관리
├─ src/screens/LoginScreen.tsx - 로그인 화면
└─ src/screens/CaregiverDashboard.tsx - 요양사 대시보드

설치된 의존성:
├─ Node.js 24.21.0 ✅
├─ npm 11.19.0 ✅
├─ React Native Expo ✅
└─ Git ✅
```

### ⏳ 아직 필요한 것
```
시스템 요구사항:
├─ Python 3.11 ❌ (Chocolatey로 설치 필요)
├─ PostgreSQL 15 ❌ (Chocolatey로 설치 필요)
└─ 데이터베이스 초기화 ❌
```

---

## 📋 Step 1: Python & PostgreSQL 설치 (필수)

### 1.1 Chocolatey 설치 (관리자 권한 필요)

PowerShell을 **관리자로 실행**한 후:

```powershell
Set-ExecutionPolicy Bypass -Scope Process -Force; [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
```

### 1.2 Python 3.11 설치

```powershell
choco install python311 -y
```

설치 확인:
```powershell
python --version
pip --version
```

### 1.3 PostgreSQL 15 설치

```powershell
choco install postgresql15 -y --params='/Password:dolbomcare123'
```

설치 확인:
```powershell
psql --version
```

### 1.4 데이터베이스 & 사용자 생성

PostgreSQL 명령줄 실행:
```powershell
psql -U postgres
```

다음 명령어 실행:
```sql
-- 데이터베이스 생성
CREATE DATABASE dolbomcare_db;

-- 사용자 생성
CREATE USER dolbomcare_user WITH PASSWORD 'password';

-- 권한 부여
ALTER ROLE dolbomcare_user SET client_encoding TO 'utf8';
ALTER ROLE dolbomcare_user SET default_transaction_isolation TO 'read committed';
ALTER ROLE dolbomcare_user SET default_transaction_deferrable TO on;
GRANT ALL PRIVILEGES ON DATABASE dolbomcare_db TO dolbomcare_user;

-- 종료
\q
```

---

## 📦 Step 2: Backend 환경 설정

### 2.1 가상환경 생성

```bash
cd D:\dolbomcare\backend
python -m venv venv
```

### 2.2 가상환경 활성화

**Windows (PowerShell):**
```powershell
.\venv\Scripts\Activate.ps1
```

**Windows (CMD):**
```cmd
.\venv\Scripts\activate.bat
```

### 2.3 의존성 설치

```bash
pip install -r requirements.txt
```

### 2.4 환경 변수 설정

`D:\dolbomcare\backend\.env` 파일 생성:

```
DATABASE_URL=postgresql://dolbomcare_user:password@localhost:5432/dolbomcare_db
DEBUG=True
ENVIRONMENT=development
LOG_LEVEL=INFO
SECRET_KEY=your-secret-key-change-in-production
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
ALLOWED_ORIGINS=["http://localhost:3000", "http://localhost:8081", "http://localhost:19000"]
```

### 2.5 데이터베이스 마이그레이션

```bash
python -c "from app.database import Base, engine; Base.metadata.create_all(bind=engine)"
```

또는 더 직접적으로:
```bash
cd D:\dolbomcare\backend
python -c "
from app.database import engine, Base
from app.models import *
Base.metadata.create_all(bind=engine)
print('✅ 데이터베이스 테이블 생성 완료!')
"
```

### 2.6 Backend 서버 시작

```bash
python main.py
```

결과:
```
✓ Uvicorn running on http://127.0.0.1:8000
✓ API 문서: http://127.0.0.1:8000/docs
```

---

## 📱 Step 3: Mobile 환경 설정

### 3.1 의존성 설치

```bash
cd D:\dolbomcare\mobile

# npm 의존성 설치
npm install

# 추가 필요 패키지
npm install @react-navigation/native @react-navigation/native-stack
npm install @react-native-async-storage/async-storage
npm install react-native-screens react-native-safe-area-context
```

### 3.2 Expo 개발 서버 시작

```bash
npx expo start
```

결과:
```
✓ Expo server running on http://localhost:8081
✓ QR 코드 표시됨
```

### 3.3 앱 실행 (3가지 방법)

**방법 1: Expo Go 앱 사용**
- iPhone/Android에 Expo Go 앱 설치
- QR 코드 스캔

**방법 2: iOS 시뮬레이터**
```bash
i  # Expo CLI에서 입력
```

**방법 3: Android 에뮬레이터**
```bash
a  # Expo CLI에서 입력
```

---

## 🧪 Step 4: 개발 및 테스트

### 4.1 테스트 계정 생성

Backend에서:
```bash
# 데이터베이스에 직접 테스트 계정 추가
python -c "
from app.database import SessionLocal
from app.models import User
from app.api.users import get_password_hash

db = SessionLocal()

# 요양사 계정
caregiver = User(
    email='caregiver@dolbomcare.com',
    hashed_password=get_password_hash('password123'),
    full_name='김요양사',
    role='caregiver'
)

# 센터장 계정
manager = User(
    email='manager@dolbomcare.com',
    hashed_password=get_password_hash('password123'),
    full_name='박센터장',
    role='center_manager'
)

db.add(caregiver)
db.add(manager)
db.commit()
print('✅ 테스트 계정 생성 완료!')
"
```

### 4.2 API 테스트

Swagger UI 접속: http://127.0.0.1:8000/docs

**테스트 순서:**
1. POST /api/v1/auth/login (테스트 계정으로 로그인)
2. GET /api/v1/health (헬스체크)
3. POST /api/v1/auth/register (새 사용자 생성)

### 4.3 모바일 앱 테스트

1. 로그인 화면에서 역할 선택 (요양사 또는 센터장)
2. 테스트 계정으로 로그인:
   - 이메일: caregiver@dolbomcare.com
   - 비밀번호: password123
3. 요양사 대시보드 표시 확인
4. "음성 기록" 버튼 클릭 → 다음 화면으로 이동 확인

---

## 📝 Step 5: 기능 추가 (2주차부터)

### Week 1 (~2026-11-15): 로그인 및 기본 대시보드
```
✅ User 회원가입/로그인
✅ 센터장 대시보드 (기본)
✅ 요양사 대시보드 (기본)
```

### Week 2-3 (~2026-11-30): 핵심 기능
```
⏳ 요양사: 음성 기반 일일 기록
⏳ 센터장: 요양사 관리 및 급여 조회
⏳ 보호자: 실시간 상태 조회
```

### Week 4 (~2026-12-15): 고도화
```
⏳ AI 자동 요약 (음성 → 텍스트)
⏳ 대시보드 통계 (차트)
⏳ 알림 시스템
```

### Week 5-6 (~2027-01-01): 최적화 및 테스트
```
⏳ 성능 최적화
⏳ 버그 수정
⏳ 보안 강화
⏳ 파일럿 센터 대응
```

---

## 🔍 Step 6: 문제 해결

### Backend 연결 오류
```
에러: "연결을 거부했습니다" (refused)
해결: PostgreSQL이 실행 중인지 확인
- Windows 서비스에서 PostgreSQL 시작
- 또는: pg_ctl -D "C:\Program Files\PostgreSQL\15\data" start
```

### 포트 충돌
```
에러: "Address already in use"
해결: 포트 번호 변경 또는 프로세스 종료
- Backend: python main.py --port 8001
- Mobile: npx expo start --port 8082
```

### 모바일 앱이 API에 연결 불가
```
에러: "Network error"
해결: API_URL 확인 (localhost는 모바일에서 작동 안 함)
- 실제 IP 주소로 변경: http://192.168.x.x:8000
- 또는: ngrok으로 터널링
```

### Python 모듈 찾기 실패
```
에러: "ModuleNotFoundError: No module named 'fastapi'"
해결: 가상환경 활성화 확인
- .\venv\Scripts\Activate.ps1 실행
- pip list로 확인
```

---

## ✅ 최종 체크리스트

### 환경 설정
- [ ] Python 3.11 설치 확인 (`python --version`)
- [ ] PostgreSQL 15 설치 확인 (`psql --version`)
- [ ] 데이터베이스 `dolbomcare_db` 생성
- [ ] 사용자 `dolbomcare_user` 생성
- [ ] 가상환경 `.env` 파일 작성
- [ ] 데이터베이스 테이블 생성

### Backend 준비
- [ ] `D:\dolbomcare\backend\venv` 생성
- [ ] `requirements.txt` 의존성 설치
- [ ] `python main.py` 실행 (포트 8000)
- [ ] http://127.0.0.1:8000/docs 접속 가능
- [ ] 테스트 계정 생성

### Mobile 준비
- [ ] `D:\dolbomcare\mobile\node_modules` 설치
- [ ] `npx expo start` 실행
- [ ] Expo Go 앱에서 QR 스캔
- [ ] 로그인 화면 표시

### 통합 테스트
- [ ] 테스트 계정으로 로그인 성공
- [ ] 요양사 대시보드 표시
- [ ] 센터장 대시보드 표시
- [ ] API Swagger에서 엔드포인트 테스트

---

## 🎯 다음 단계

```
현재: MVP 기본 코드 준비 ✅
┌─────────────────────────────┐
│                             │
│  1️⃣ 환경 설정 (1-2일)      │
│     Python, PostgreSQL 설치 │
│                             │
│  2️⃣ Backend 시작 (1주)     │
│     API 개발, DB 연결      │
│                             │
│  3️⃣ Mobile 앱 (1-2주)     │
│     기본 화면, 로그인      │
│                             │
│  4️⃣ 통합 테스트 (3-5일)   │
│     E2E 테스트, 버그 수정  │
│                             │
│  5️⃣ 파일럿 센터 (2월)     │
│     5곳 현장 테스트        │
│                             │
└─────────────────────────────┘
         ↓
    Alpha 버전 완성 (12월)
```

---

## 📞 도움이 필요하면

1. **Backend API 에러**
   - http://127.0.0.1:8000/docs 에서 직접 테스트
   - 응답 메시지 확인

2. **Database 연결 에러**
   - `.env` 파일의 DATABASE_URL 확인
   - PostgreSQL 서비스 상태 확인

3. **Mobile 앱 에러**
   - Expo 로그 확인 (`npx expo start`)
   - Chrome DevTools 디버거 실행

**화이팅!** 🚀

