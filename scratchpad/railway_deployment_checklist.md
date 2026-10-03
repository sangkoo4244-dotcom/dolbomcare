# 🚂 Railway 배포 검증 체크리스트 (2026-10-03)

## ✅ 현재 상태

### Backend 준비 상태
- ✅ **requirements.txt**: 완벽하게 준비됨
  - FastAPI, uvicorn, SQLAlchemy, PostgreSQL 드라이버 모두 포함
  - bcrypt, python-jose (JWT 인증) 포함

- ✅ **main.py**: FastAPI 앱 초기화 완료
  - CORS 미들웨어 설정 ✅
  - 모든 라우터 등록됨 (users, billing, residents, schedule, salary, records) ✅
  - 정적 파일 마운트 설정 ✅

- ✅ **Database 마이그레이션**: 필요한 엔드포인트 모두 구현됨
  - /api/v1/health (헬스 체크) ✅
  - /api/v1/auth (로그인/회원가입) ✅
  - /api/v1/schedule (일정 관리) ✅

---

## ⚠️ 배포 전 필수 작업

### 1️⃣ GitHub 저장소 연결 (중요!)
- [ ] GitHub 계정 준비
- [ ] 저장소명: `dolbomcare`
- [ ] SSH Key 또는 Personal Access Token 설정
- [ ] .gitignore 확인 (아래 참고)

**현재 상태**: ❌ Git Remote가 설정되지 않음
```bash
# 현재 상태
git remote -v
# (출력 없음 = GitHub 연결 안 됨)
```

**해결 방법**:
```bash
git remote add origin https://github.com/your-username/dolbomcare.git
git branch -M main
git push -u origin main
```

### 2️⃣ 변경사항 커밋 (중요!)
- [ ] 수정된 파일 커밋
- [ ] 새 파일 (schedule.py) 커밋

**현재 상태**: ⚠️ 변경사항 미커밋
```
modified:   .claude/CLAUDE.md
modified:   backend/app/models.py
modified:   backend/main.py
untracked:  backend/app/api/schedule.py
```

**해결 방법**:
```bash
git add backend/
git commit -m "feat: Add schedule management API endpoints"
git push origin main
```

### 3️⃣ .env 파일 보안 (중요!)
- [ ] .gitignore에 `.env` 추가 확인
- [ ] 민감한 정보(PASSWORD, SECRET_KEY) 노출 확인

**현재 상태**: ⚠️ `.env` 파일이 존재함
- 위치: `D:\dolbomcare\backend\.env`
- 내용: DATABASE_URL, SECRET_KEY 등 포함

**해결 방법**:
```bash
# .gitignore 확인
cat .gitignore | grep env

# 없으면 추가
echo ".env" >> .gitignore
git rm --cached backend/.env  # 이미 tracked된 경우
git commit -m "chore: Ignore .env file"
```

### 4️⃣ Procfile 생성 (Railway 배포용)
- [ ] Backend용 Procfile 생성

**파일 위치**: `D:\dolbomcare\backend\Procfile`

**내용**:
```
web: uvicorn main:app --host 0.0.0.0 --port $PORT
```

### 5️⃣ railway.json 생성 (선택사항)
- [ ] Railway 설정 파일 (자동 감지도 됨)

**파일 위치**: `D:\dolbomcare\railway.json`

**내용**:
```json
{
  "build": {
    "builder": "dockerfile"
  },
  "deploy": {
    "numReplicas": 1,
    "restartPolicyType": "unless-stopped",
    "restartPolicyMaxRetries": 10
  }
}
```

또는 더 간단하게:
```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": {
    "builder": "nixpacks"
  }
}
```

---

## 📋 Railway 배포 전 최종 체크리스트

### Backend 코드 준비
- ✅ requirements.txt 완성
- ✅ main.py 초기화 완료
- ✅ 모든 라우터 등록
- ✅ CORS 설정
- ⚠️ DATABASE_URL 환경 변수 확인 필요

### Git 저장소
- ❌ GitHub 저장소 생성 필수
- ❌ git remote 연결 필수
- ⚠️ 변경사항 커밋 필수
- ⚠️ .env 파일 .gitignore 추가 필수

### 배포 설정
- ⚠️ Procfile 필요 (또는 railway.json)
- ⚠️ 환경 변수 설정 (Railway Dashboard에서)

---

## 🚀 배포 순서 (Railway)

### Step 1: GitHub 준비 (10분)
```bash
# 1. GitHub 저장소 생성 (https://github.com/new)
# 저장소명: dolbomcare

# 2. 로컬 git 설정
cd D:\dolbomcare
git remote add origin https://github.com/your-username/dolbomcare.git
git branch -M main

# 3. .env 보안
echo ".env" >> .gitignore
git add .gitignore backend/app/api/schedule.py backend/main.py backend/app/models.py .claude/CLAUDE.md

# 4. 커밋
git commit -m "feat: Add schedule management API

- Implement Schedule model with status tracking
- Add full CRUD endpoints for schedule management
- Support for repeat scheduling (weekly, biweekly, monthly)
- Add role-based filtering (caregiver vs center_manager)
- Integrate with billing system for automatic BillingRecord creation"

# 5. Push
git push -u origin main
```

### Step 2: Railway 배포 (5분)
```
1. Railway 대시보드 → Projects → New
2. GitHub 저장소 선택 (dolbomcare)
3. 자동 감지됨 (Python FastAPI)
4. 환경 변수 추가:
   - DATABASE_URL (Railway PostgreSQL 자동)
   - SECRET_KEY
   - DEBUG=False
   - ENVIRONMENT=production
5. Deploy 클릭
```

### Step 3: 환경 변수 설정 (3분)
Railway Dashboard에서:
```
DATABASE_URL: [자동 생성]
SECRET_KEY: your-very-long-secret-key-here
DEBUG: False
ENVIRONMENT: production
ACCESS_TOKEN_EXPIRE_MINUTES: 30
ALGORITHM: HS256
```

### Step 4: 배포 확인 (2분)
```
1. Railway 로그 확인: "Application started successfully"
2. 브라우저 확인: https://dolbomcare.up.railway.app
3. Swagger 확인: https://dolbomcare.up.railway.app/docs
```

---

## ⚠️ 주의사항

### 1. 데이터베이스
- Railway가 PostgreSQL 자동으로 제공함
- DATABASE_URL은 자동으로 설정됨
- 수동 설정 불필요

### 2. 환경 변수
- Railway Dashboard → Variables에서 설정
- .env 파일은 git에 올리면 안 됨
- Production 환경변수 따로 설정

### 3. 배포 후 문제 해결
```bash
# 로그 확인
railway logs

# 재배포
railway up

# 상태 확인
railway status
```

---

## 🎯 배포 준비 완료도: 70%

### 완료된 것
- ✅ Backend 코드 준비
- ✅ API 엔드포인트 구현
- ✅ 데이터베이스 모델 설정

### 남은 것
- ❌ GitHub 저장소 생성 및 연결
- ❌ 변경사항 커밋 및 push
- ❌ Procfile 생성
- ❌ 환경 변수 설정

**다음 단계**: GitHub 저장소 생성 → 코드 push → Railway 연결

---

**예상 총 소요 시간**: 20분
- GitHub 설정: 10분
- Railway 배포: 5분
- 테스트 확인: 5분
