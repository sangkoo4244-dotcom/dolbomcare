# Week 1 스타트업 가이드

## 핵심 목표
- [ ] 개발 환경 완벽 구축
- [ ] Github 저장소 초기화 (백엔드 + 프론트엔드)
- [ ] AWS 기초 인프라 (EC2, RDS)
- [ ] 첫 "Hello World" API 배포
- [ ] 팀 협업 도구 설정

---

## Day 1-2: 기술 스택 최종 확인

### 확인 사항
```
✅ React Native + Expo (모바일 앱)
✅ Next.js (센터장 웹)
✅ FastAPI (백엔드 API)
✅ PostgreSQL 15 (주 DB)
✅ Redis (캐싱)
✅ AWS (호스팅)
```

### 팀원별 학습 자료
```
백엔드 개발자:
- FastAPI 공식 튜토리얼 (30분)
- SQLAlchemy ORM (1시간)
- 비동기 Python (1시간)
→ 총 2.5시간

프론트엔드 개발자 (모바일):
- React Native 기초 (1시간)
- Expo 튜토리얼 (1시간)
- React Navigation (1시간)
→ 총 3시간

프론트엔드 개발자 (웹):
- Next.js App Router (1시간)
- React Query (1시간)
→ 총 2시간
```

---

## Day 3-4: 로컬 개발 환경 구축

### 사전 요구사항
```
□ Node.js 18+ (LTS)
□ Python 3.10+
□ Git
□ VS Code (또는 선호 에디터)
□ PostgreSQL 15 (로컬 또는 Docker)
□ Redis (로컬 또는 Docker)
```

### 1. 백엔드 환경 설정 (30분)

```bash
# 1. 저장소 클론
git clone https://github.com/<org>/dolbomcare-backend.git
cd dolbomcare-backend

# 2. 가상 환경 생성
python -m venv venv

# Windows
venv\Scripts\activate
# Mac/Linux
source venv/bin/activate

# 3. 필수 패키지 설치
pip install -r requirements.txt

# requirements.txt 초본
fastapi==0.104.0
uvicorn==0.24.0
sqlalchemy==2.0.23
psycopg2-binary==2.9.9
pydantic==2.5.0
pydantic-settings==2.1.0
python-dotenv==1.0.0
python-jose==3.3.0
passlib==1.7.4
bcrypt==4.1.1
pytest==7.4.3
httpx==0.25.2

# 4. 환경 변수 설정
cp .env.example .env
# .env 파일 수정
# DATABASE_URL=postgresql://user:password@localhost/dolbomcare
# REDIS_URL=redis://localhost:6379
# SECRET_KEY=<생성된 랜덤 문자열>

# 5. 데이터베이스 마이그레이션
alembic upgrade head

# 6. 개발 서버 시작
uvicorn main:app --reload
# http://localhost:8000/docs 접속 (Swagger UI)
```

### 2. 모바일 앱 환경 설정 (20분)

```bash
# 1. Expo 프로젝트 생성
npx create-expo-app dolbomcare-mobile
cd dolbomcare-mobile

# 2. 필수 패키지 설치
npm install @react-navigation/native @react-navigation/bottom-tabs
npm install react-native-screens react-native-safe-area-context
npm install axios react-query
npm install redux @reduxjs/toolkit react-redux
npm install react-native-paper

# 3. .env 파일 생성
touch .env
# API_BASE_URL=http://localhost:8000

# 4. 개발 서버 시작
npx expo start
# QR 코드로 Expo Go 앱에서 확인
```

### 3. 웹 대시보드 환경 설정 (20분)

```bash
# 1. Next.js 프로젝트 생성
npx create-next-app@latest dolbomcare-web
# TypeScript: Yes
# ESLint: Yes
# Tailwind: Yes
# App Router: Yes

cd dolbomcare-web

# 2. 추가 패키지
npm install axios react-query recharts zustand

# 3. .env.local 생성
touch .env.local
# NEXT_PUBLIC_API_URL=http://localhost:8000

# 4. 개발 서버 시작
npm run dev
# http://localhost:3000
```

---

## Day 5: AWS 기초 인프라 (1시간)

### 사전 요구사항
```
□ AWS 계정 생성
□ IAM 사용자 생성 (프로그래밍 액세스)
□ AWS CLI 설치 및 설정
```

### 1. EC2 인스턴스 생성

```bash
# AWS CLI로 생성 (또는 콘솔에서)
aws ec2 run-instances \
  --image-id ami-0c55b159cbfafe1f0 \
  --instance-type t3.medium \
  --key-name dolbomcare-key \
  --security-groups default \
  --region ap-northeast-2
```

### 2. RDS PostgreSQL 생성

```bash
# AWS 콘솔에서:
# 1. RDS → 데이터베이스 → 데이터베이스 생성
# 2. 엔진: PostgreSQL 15
# 3. 인스턴스 클래스: db.t3.small
# 4. 스토리지: 20GB (필요시 자동 확장 활성화)
# 5. 마스터 사용자명: postgres
# 6. 암호: <강력한 비밀번호>
# 7. 초기 DB: dolbomcare
```

### 3. 테스트 배포

```bash
# EC2 SSH 접속
ssh -i dolbomcare-key.pem ec2-user@<EC2-IP>

# Python 및 필수 도구 설치
sudo yum update -y
sudo yum install -y python3.10 git postgresql

# 저장소 클론 및 실행
git clone <repo>
cd dolbomcare-backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 백그라운드에서 실행
nohup uvicorn main:app --host 0.0.0.0 --port 8000 > app.log &
```

---

## Github 저장소 구조

```
GitHub 조직 설정
└── dolbomcare
    ├── dolbomcare-backend (Python/FastAPI)
    │   ├── app/
    │   │   ├── main.py
    │   │   ├── models/
    │   │   ├── schemas/
    │   │   ├── api/
    │   │   │   ├── users.py
    │   │   │   ├── residents.py
    │   │   │   ├── records.py
    │   │   │   └── stats.py
    │   │   ├── database.py
    │   │   └── config.py
    │   ├── tests/
    │   ├── alembic/
    │   ├── requirements.txt
    │   ├── .env.example
    │   ├── .gitignore
    │   └── README.md
    │
    ├── dolbomcare-mobile (React Native/Expo)
    │   ├── app/
    │   │   ├── index.tsx
    │   │   ├── (auth)/
    │   │   ├── (home)/
    │   │   └── (dashboard)/
    │   ├── components/
    │   ├── hooks/
    │   ├── services/
    │   ├── store/
    │   ├── app.json
    │   ├── .env.example
    │   └── package.json
    │
    └── dolbomcare-web (Next.js)
        ├── app/
        │   ├── layout.tsx
        │   ├── page.tsx
        │   ├── auth/
        │   ├── dashboard/
        │   └── reports/
        ├── components/
        ├── hooks/
        ├── services/
        ├── .env.local.example
        └── package.json
```

---

## CI/CD 파이프라인 (Github Actions)

### 백엔드 자동 테스트 (.github/workflows/backend.yml)

```yaml
name: Backend CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

jobs:
  test:
    runs-on: ubuntu-latest
    
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_DB: dolbomcare_test
          POSTGRES_PASSWORD: test
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432

    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
      
      - name: Run tests
        run: pytest -v --cov=app
      
      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

### 프론트엔드 자동 배포 (.github/workflows/frontend.yml)

```yaml
name: Frontend CI/CD

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  build:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Node
        uses: actions/setup-node@v3
        with:
          node-version: '18'
      
      - name: Install dependencies
        run: npm ci
      
      - name: Run linter
        run: npm run lint
      
      - name: Build
        run: npm run build
      
      - name: Deploy to Vercel
        uses: vercel/action@master
        with:
          vercel-token: ${{ secrets.VERCEL_TOKEN }}
          vercel-org-id: ${{ secrets.VERCEL_ORG_ID }}
          vercel-project-id: ${{ secrets.VERCEL_PROJECT_ID }}
```

---

## 팀 협업 도구 설정

### Slack 채널 구조
```
#general              - 공지사항
#development          - 개발 논의
#backend              - 백엔드 관련
#frontend             - 프론트엔드 관련
#devops               - 인프라/배포
#bugs                 - 버그 리포팅
#daily-standup        - 일일 보고
#random               - 잡담
```

### Github Integration
```bash
# Slack에서 GitHub 앱 설치
/github subscribe dolbomcare-backend
/github subscribe dolbomcare-mobile
/github subscribe dolbomcare-web

# 알림 받기
/github subscribe dolbomcare-backend pulls reviews
```

### Notion 문서 구조
```
Dolbomcare 개발
├── 📋 스프린트 계획
├── 🐛 버그 리스트
├── 📚 API 문서
├── 🏗️ 아키텍처
├── 📖 온보딩
└── 📊 성과 지표
```

---

## 첫 주 체크리스트

### 월요일
- [ ] 팀 킥오프 회의 (30분)
- [ ] 기술 스택 최종 확인
- [ ] 개발자 역할 분담
- [ ] Github 조직 생성

### 화요일
- [ ] 로컬 개발 환경 구축 (모두)
- [ ] 각 팀원별 "Hello World" 구현
- [ ] 저장소 구조 최종 확인

### 수요일
- [ ] AWS 계정 설정
- [ ] EC2 + RDS 기본 설정
- [ ] CI/CD 파이프라인 구축

### 목요일
- [ ] 첫 API 작성 (사용자 등록)
- [ ] 테스트 작성
- [ ] 자동 배포 테스트

### 금요일
- [ ] 주간 회고
- [ ] 다음주 스프린트 계획
- [ ] 문서화 점검

---

## 다음 단계 (Week 2 준비)

- [ ] 데이터베이스 스키마 상세 설계
- [ ] API 엔드포인트 목록 작성
- [ ] UI/UX 디자인 완성
- [ ] 모바일 앱 네비게이션 구현 시작
