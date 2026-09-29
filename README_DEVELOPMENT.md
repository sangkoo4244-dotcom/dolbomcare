# dolbomcare 개발 계획 - 전체 가이드

## 📚 문서 구조

이 디렉토리의 개발 계획 문서들을 다음 순서대로 읽으세요:

### 1️⃣ **06_TECHNICAL_DEVELOPMENT_PLAN.md** (필독)
dolbomcare 프로젝트의 **완전한 개발 계획서**입니다.
- 기술 스택 최종 결정 (React Native, FastAPI, PostgreSQL, AWS)
- MVP 스코프 (6개월 계획)
- 시스템 아키텍처
- 6개월 상세 일정 (주별 작업)
- 필요한 자원 및 비용
- 위험 요소 및 대응

**시간:** 30분  
**대상:** 모든 팀원

---

### 2️⃣ **07_WEEK_1_STARTUP_GUIDE.md** (지금 시작!)
**이번 주(Week 1)에 해야할 모든 것**이 정리되어 있습니다.

**내용:**
- Day 1-2: 기술 스택 최종 확인
- Day 3-4: 로컬 개발 환경 설정 (상세 명령어)
- Day 5: AWS 인프라 구축
- Github 저장소 구조
- CI/CD 파이프라인 (Github Actions 스크립트)
- Slack/Notion 설정
- 주간 체크리스트

**시간:** 5일 (각 팀원별)  
**대상:** 백엔드 개발자, 프론트엔드 개발자 (모바일 + 웹), DevOps

**지금 바로 Day 1을 시작하세요!**

---

### 3️⃣ **08_DATABASE_SCHEMA.md** (백엔드 필독)
데이터베이스의 **완전한 설계**입니다.

**포함 내용:**
- 11개 테이블 정의 (SQL)
- 각 테이블 컬럼 상세 설명
- 관계도 (ERD)
- 인덱싱 전략
- 마이그레이션 전략 (Alembic)
- 초기 데이터 시딩
- 백업 및 복구 전략

**대상:** 백엔드 개발자 (Week 3부터 필요)

---

### 4️⃣ **09_API_SPECIFICATION.md** (모든 개발자)
백엔드 **API 명세서**입니다.

**포함 내용:**
- 30개 이상의 API 엔드포인트
- 인증 (회원가입, 로그인)
- 센터, 입소자, 기록, 일정 관리
- 통계 및 리포트
- 알림 시스템
- 요양사 성과 조회
- 요청/응답 예시
- 에러 처리

**대상:** 백엔드 개발자 (Week 3)  
**대상:** 프론트엔드 개발자 (Week 5부터)

---

### 5️⃣ **10_MASTER_CHECKLIST.md** (모든 팀원)
**개발 전체 일정의 체크리스트**입니다.

**구성:**
- Phase 1-6: 각 단계별 상세 체크리스트
- 테스트 & QA 전체
- 성공 지표 (Month 6 종료)
- 운영 체크리스트 (일일/주간/월간)

**용도:** 진행 상황 추적  
**갱신:** 매주 업데이트

---

## 🚀 지금 바로 시작하기 (오늘)

### Step 1: 이 README 읽기 (5분)
✅ 방금 하고 있습니다.

### Step 2: 기술 스택 확인 (10분)
```bash
# 06_TECHNICAL_DEVELOPMENT_PLAN.md의 "1️⃣ 기술 스택" 섹션 읽기

✅ React Native + Expo (모바일)
✅ Next.js (웹)
✅ FastAPI (백엔드)
✅ PostgreSQL (DB)
✅ Redis (캐싱)
✅ AWS (호스팅)
```

확인이 끝났으면 팀에 Slack으로 알리기: "✅ 기술 스택 확인 완료"

### Step 3: 07_WEEK_1_STARTUP_GUIDE.md 읽기 (30분)
Day 1-2부터 시작하는 "기술 스택 최종 확인" 섹션을 읽으세요.

### Step 4: Github 저장소 생성 (30분)
```bash
# 3개 저장소 생성
- dolbomcare-backend
- dolbomcare-mobile
- dolbomcare-web

# .gitignore 템플릿 추가
# README.md 생성
# 팀원 초대
```

### Step 5: 각 팀원별 개발 환경 설정 (2-3시간)
**백엔드 개발자:**
```bash
# 07_WEEK_1_STARTUP_GUIDE.md의 "Day 3-4: 로컬 개발 환경" 섹션
# "1. 백엔드 환경 설정" 따라하기

# 확인: http://localhost:8000/docs 접속 가능?
```

**프론트엔드 개발자 (모바일):**
```bash
# 07_WEEK_1_STARTUP_GUIDE.md의 "Day 3-4: 로컬 개발 환경" 섹션
# "2. 모바일 앱 환경 설정" 따라하기

# 확인: Expo Go에서 QR 코드로 실행 가능?
```

**프론트엔드 개발자 (웹):**
```bash
# 07_WEEK_1_STARTUP_GUIDE.md의 "Day 3-4: 로컬 개발 환경" 섹션
# "3. 웹 대시보드 환경 설정" 따라하기

# 확인: npm run dev에서 http://localhost:3000 접속 가능?
```

### Step 6: AWS 인프라 설정 (1시간)
**DevOps 또는 백엔드 리드:**
```bash
# 07_WEEK_1_STARTUP_GUIDE.md의 "Day 5: AWS 기초 인프라" 섹션 따라하기

# 확인:
- [ ] EC2 인스턴스 생성
- [ ] RDS PostgreSQL 생성
- [ ] 테스트 배포 성공
```

---

## 📅 주간 일정

### Week 1 (이번 주)
```
Monday    : 팀 킥오프 + 기술 스택 확인
Tuesday   : 로컬 개발 환경 설정
Wednesday : AWS 인프라 구축
Thursday  : 첫 API 작성 & 배포
Friday    : 주간 회고 + 다음주 계획
```

### Week 2-8 (Month 1-2)
```
- 백엔드: 데이터베이스 스키마 & 인증 시스템
- 프론트엔드: 기본 네비게이션 & 레이아웃
- DevOps: CI/CD 파이프라인
```

### Week 9-24 (Month 3-6)
```
- Phase 3: MVP 핵심 기능 (기록, 대시보드 등)
- Phase 4: 통합 & 배포
- Phase 5: 고도화 (음성, 알림, 리포트)
```

---

## 📞 빠른 참조 (Quick Links)

| 필요한 것 | 문서 |
|----------|------|
| 기술 스택 선택 이유 | 06_TECHNICAL_DEVELOPMENT_PLAN.md 섹션 1 |
| Week 1 해야할 일 | 07_WEEK_1_STARTUP_GUIDE.md |
| 로컬 환경 설정 명령어 | 07_WEEK_1_STARTUP_GUIDE.md > Day 3-4 |
| AWS 설정 | 07_WEEK_1_STARTUP_GUIDE.md > Day 5 |
| DB 스키마 | 08_DATABASE_SCHEMA.md |
| API 엔드포인트 | 09_API_SPECIFICATION.md |
| 전체 체크리스트 | 10_MASTER_CHECKLIST.md |
| 6개월 일정 | 06_TECHNICAL_DEVELOPMENT_PLAN.md 섹션 4 |

---

## ❓ FAQ

**Q: 어디서 시작해야 할까요?**
A: 07_WEEK_1_STARTUP_GUIDE.md의 Day 1부터 시작하세요. 단계별로 따라하면 됩니다.

**Q: 기술 스택을 바꿀 수 있나요?**
A: Week 1-2에는 가능합니다. 이후에는 일정 지연이 발생합니다. 필요하면 팀 회의에서 논의하세요.

**Q: 데이터베이스 스키마를 먼저 봐야 하나요?**
A: 백엔드 개발자는 Week 3부터 필요합니다. 지금은 개발 환경 설정만 하세요.

**Q: API 명세서를 먼저 봐야 하나요?**
A: 백엔드는 Week 3부터, 프론트엔드는 Week 5부터 필요합니다. 지금은 환경 설정을 우선하세요.

**Q: 기술 스택이 너무 많은 것 같은데요?**
A: 각 팀원이 필요한 것만 배우면 됩니다:
- 백엔드: Python + FastAPI + PostgreSQL + AWS
- 프론트엔드 모바일: React Native + Expo + AWS S3
- 프론트엔드 웹: Next.js + Tailwind + AWS S3
- DevOps: AWS + Github Actions + Docker

**Q: 6개월이 맞나요?**
A: Week 1-2에 2주 버퍼가 있습니다. 지연이 생기면 이 버퍼를 사용합니다.

---

## 📊 프로젝트 구조

```
dolbomcare/
├── 06_TECHNICAL_DEVELOPMENT_PLAN.md    ← 6개월 전체 계획
├── 07_WEEK_1_STARTUP_GUIDE.md          ← Week 1 상세 가이드
├── 08_DATABASE_SCHEMA.md               ← DB 설계
├── 09_API_SPECIFICATION.md             ← API 명세서
├── 10_MASTER_CHECKLIST.md              ← 전체 체크리스트
├── README_DEVELOPMENT.md               ← 이 문서
│
├── dolbomcare-backend/                 ← 백엔드 저장소 (Github)
│   ├── app/
│   ├── tests/
│   ├── requirements.txt
│   └── .env.example
│
├── dolbomcare-mobile/                  ← 모바일 앱 저장소 (Github)
│   ├── app/
│   ├── components/
│   ├── app.json
│   └── package.json
│
└── dolbomcare-web/                     ← 웹 대시보드 저장소 (Github)
    ├── app/
    ├── components/
    ├── tailwind.config.js
    └── package.json
```

---

## 🎯 주요 마일스톤

```
Week 2 말   : 로컬 개발 환경 완성
Week 4 말   : 백엔드 기초 완성 (인증, API)
Week 6 말   : 프론트엔드 기초 완성
Week 8 말   : 첫 배포 성공 (베타)
Week 16 말  : MVP 기능 완성 (3개 앱)
Week 24 말  : 프로덕션 배포 (최종)
```

---

## 🎓 팀원별 학습 경로

### 백엔드 개발자
1. FastAPI 기본 (2시간)
2. SQLAlchemy ORM (2시간)
3. PostgreSQL 쿼리 (1시간)
4. 08_DATABASE_SCHEMA.md 읽기 (1시간)
5. 09_API_SPECIFICATION.md 읽기 (1.5시간)
6. Week 3부터 실제 구현 시작

### 프론트엔드 개발자 (모바일)
1. React Native 기본 (2시간)
2. React Navigation (1시간)
3. React Query (1시간)
4. Expo 배포 (1시간)
5. Week 5부터 실제 구현 시작

### 프론트엔드 개발자 (웹)
1. Next.js 기본 (2시간)
2. Tailwind CSS (1시간)
3. React Query (1시간)
4. Next.js 배포 (1시간)
5. Week 5부터 실제 구현 시작

---

## ✅ 체크인 포인트

### Week 1 종료 시
- [ ] 3개 저장소 생성 완료
- [ ] 각 팀원 로컬 개발 환경 설정 완료
- [ ] AWS 인프라 기초 설정 완료
- [ ] "Hello World" API 배포 성공
- [ ] CI/CD 파이프라인 작동

### Week 2 종료 시
- [ ] 모든 팀원이 개발 환경에서 작업 가능
- [ ] Github, Slack, Notion 모두 활성화
- [ ] 팀 문화 형성 (스탠드업, 회고)

### Week 4 종료 시
- [ ] 백엔드 인증 시스템 작동
- [ ] 기본 API 3-5개 구현 완료
- [ ] 자동 테스트 >60% 커버리지

### Week 8 종료 시
- [ ] 3개 앱 모두 AWS에 배포 가능
- [ ] 마지막 E2E 테스트 완료
- [ ] 베타 테스트 준비 완료

---

## 💡 팁

1. **문서 먼저**: 코드를 쓰기 전에 이 문서들을 읽으세요.
2. **주간 회고**: 매주 금요일에 팀이 모여 진행 상황을 점검하세요.
3. **작은 커밋**: 큰 작업은 작은 PR로 나누어 리뷰하세요.
4. **테스트 먼저**: 기능 구현 전에 테스트를 작성하세요 (TDD).
5. **문서화**: 코드를 작성할 때마다 주석과 문서를 함께 작성하세요.

---

## 📞 연락처

- **팀 리드:** [이름] - [Slack]
- **기술 리드:** [이름] - [Slack]
- **제품 매니저:** [이름] - [Slack]

---

**마지막 업데이트:** 2024년 1월  
**다음 리뷰:** Week 4 말
