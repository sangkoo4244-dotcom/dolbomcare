# dolbomcare 개발 계획서

## 1️⃣ 기술 스택 최종 결정

### Frontend (요양사/센터장/보호자 앱)

**프레임워크: React Native + Expo**
- 이유: iOS/Android 동시 개발, 빠른 개발 속도, 재사용 가능한 컴포넌트
- 초기 학습곡선: 중간 (React 경험자 기준 2-3주)
- 상태 관리: Redux Toolkit
- API 통신: Axios + React Query
- UI 라이브러리: React Native Paper

**센터장 대시보드: React + TypeScript**
- Next.js (SSR, API Routes)
- 차트: Recharts
- 테이블: TanStack Table
- 스타일: Tailwind CSS

### Backend

**언어 & 프레임워크: Python + FastAPI**
- 이유: 빠른 개발, 좋은 문서화, 비동기 지원, 팀 학습 용이
- 응답 시간: <200ms (대부분의 API)
- 동시 처리: 1000+ 요청/초

**주요 라이브러리:**
- FastAPI: 웹 프레임워크
- SQLAlchemy: ORM
- Pydantic: 데이터 검증
- JWT: 인증
- Celery: 비동기 작업 (알림, 보고서)

### Database

**PostgreSQL 15**
- 이유: ACID 준수, JSON 지원, 확장성, 커뮤니티
- 캐싱: Redis (세션, 임시 데이터)
- 메시지 큐: RabbitMQ (알림, 이메일)

**초기 스키마:**
```
Users (id, email, password_hash, role, center_id)
Residents (id, center_id, name, birth_date, health_info)
Records (id, resident_id, caregiver_id, type, content, timestamp)
CaregiverPerformance (id, caregiver_id, center_id, records_count)
Alerts (id, resident_id, guardian_id, message, read_at)
```

### Cloud & Hosting

**선택: AWS**
- EC2: t3.medium (초기)
- RDS: db.t3.small PostgreSQL
- S3: 파일 저장
- ElastiCache: Redis
- CloudFront: CDN
- Route53: DNS
- **초기 월간 비용: $200-300**

### 개발 도구

| 도구 | 용도 | 비용 |
|------|------|------|
| Github | 저장소, CI/CD | 무료 |
| Github Actions | 자동 배포 | 무료 |
| Slack | 팀 협업 | $6.67/명 |
| Figma | UI/UX 디자인 | $12/월 |
| Postman | API 테스트 | 무료 |
| Sentry | 에러 추적 | $29/월 |

---

## 2️⃣ MVP 스코프 (Phase 1: 6개월)

### 요양사 앱 (모바일)
✅ 로그인/회원가입 (이메일, 비밀번호)
✅ 대시보드 (오늘의 입소자 목록)
✅ 기록 입력 (체크박스 기반)
  - 식사 여부/시간
  - 약물 복용
  - 활동/외출
  - 일반 메모
✅ 음성 기록 (선택, 간단한 음성→텍스트)
✅ 일일 기록 조회
✅ 오프라인 지원 (로컬 캐싱)
✅ 푸시 알림 (기본)

### 센터장 대시보드 (웹)
✅ 로그인
✅ 요양사 목록 및 상태
✅ 입소자 목록
✅ 기본 통계 (기록 수, 활동도)
✅ 일일/주간/월간 리포트
✅ 기록 상세 조회
✅ CSV 내보내기

### 보호자 앱 (모바일)
✅ 로그인
✅ 부모님 상태 (마지막 활동 시간)
✅ 일일 요약
✅ 긴급 알림
✅ 기록 조회

### 백엔드
✅ 사용자 관리 (인증, 권한)
✅ 입소자 관리
✅ 기록 CRUD
✅ 통계 API
✅ 알림 시스템

---

## 3️⃣ 시스템 아키텍처

```
┌─────────────────────────────────────────────────────────────┐
│                   요양사 앱 (React Native)                    │
│                센터장 웹 (Next.js)                            │
│                보호자 앱 (React Native)                       │
└────────────────────┬────────────────────────────────────────┘
                     │
         ┌───────────┴───────────┐
         │                       │
┌────────▼──────────┐   ┌────────▼──────────┐
│   API Gateway     │   │  Websocket (알림) │
│   (FastAPI)       │   │                   │
└────────┬──────────┘   └────────┬──────────┘
         │                       │
         │      ┌────────────────┘
         │      │
    ┌────▼──────▼────────────────────────┐
    │      FastAPI Backend Server         │
    │  - 사용자 관리                       │
    │  - 기록 관리                         │
    │  - 통계 계산                         │
    │  - 알림 처리                         │
    └────┬──────┬──────────┬──────┬───────┘
         │      │          │      │
    ┌────▼──┐ ┌─▼────┐ ┌──▼──┐ ┌─▼─────┐
    │  RDS  │ │Redis │ │ S3  │ │ SQS   │
    │(PostgreSQL)   │ │(파일)│ │(메시지)
    └───────┘ └──────┘ └─────┘ └───────┘
```

---

## 4️⃣ 6개월 개발 일정 (Week by Week)

### Month 1-2: 기초 구축 (Weeks 1-8)

**Week 1-2: 환경 설정**
- [ ] AWS 계정 설정 및 초기 인프라
- [ ] Git 저장소 생성 (backend, frontend-app, frontend-web)
- [ ] 개발 환경 문서화
- [ ] CI/CD 파이프라인 (Github Actions)
- [ ] 팀 협업 도구 설정 (Slack)

**Week 3-4: 백엔드 기초**
- [ ] FastAPI 프로젝트 구조
- [ ] PostgreSQL 스키마 설계
- [ ] 사용자 관리 API (회원가입, 로그인)
- [ ] JWT 인증 시스템
- [ ] 단위 테스트 (pytest)
- [ ] API 문서화 (Swagger)

**Week 5-6: 프론트엔드 기초**
- [ ] React Native Expo 프로젝트 초기화
- [ ] Next.js 대시보드 프로젝트 초기화
- [ ] 네비게이션 구조 (React Navigation)
- [ ] 기본 레이아웃 컴포넌트
- [ ] API 통신 레이어 (Axios, React Query)

**Week 7-8: 통합**
- [ ] 백엔드 배포 (AWS EC2)
- [ ] 프론트엔드 빌드 파이프라인
- [ ] E2E 테스트 (Cypress 또는 Playwright)
- [ ] 배포 자동화 테스트

**산출물:**
- API 스펙 문서 (Swagger)
- 아키텍처 다이어그램
- 배포 가이드
- 팀 온보딩 문서

---

### Month 3-4: MVP 핵심 기능 (Weeks 9-16)

**Week 9-10: 요양사 앱 - 기본 기록**
- [ ] 로그인 화면 & 기능
- [ ] 홈 화면 (입소자 목록)
- [ ] 기록 입력 화면 (체크박스)
- [ ] 기록 저장 API 연동
- [ ] 로컬 캐싱 (SQLite 또는 AsyncStorage)
- [ ] 오프라인 지원

**Week 11-12: 센터장 대시보드 - 관리 기능**
- [ ] 로그인 화면
- [ ] 요양사 목록 및 상태
- [ ] 입소자 목록
- [ ] 기본 통계 대시보드
- [ ] 기록 조회 기능
- [ ] 필터링 & 검색

**Week 13-14: 보호자 앱 - 실시간 상태**
- [ ] 로그인 화면
- [ ] 부모님 상태 표시
- [ ] 일일 요약 화면
- [ ] 알림 표시
- [ ] 기록 상세 조회

**Week 15-16: 통합 & QA**
- [ ] 기능 통합 테스트
- [ ] 성능 테스트 (응답 시간)
- [ ] 보안 감시 (OWASP Top 10)
- [ ] 베타 버전 배포
- [ ] 사용자 테스트 피드백

**산출물:**
- 작동하는 베타 앱 (3개)
- 테스트 보고서
- 사용자 피드백 문서

---

### Month 5-6: 고도화 & 최적화 (Weeks 17-24)

**Week 17-18: 음성 기반 기록**
- [ ] 음성 녹음 UI
- [ ] 음성 파일 저장 & 전송
- [ ] 음성→텍스트 API (Google Speech-to-Text)
- [ ] 텍스트 정규화 (맞춤법 검사)
- [ ] 사용자 피드백 반영

**Week 19-20: 알림 시스템 강화**
- [ ] 푸시 알림 (Firebase Cloud Messaging)
- [ ] 이메일 알림
- [ ] 알림 설정 UI
- [ ] 알림 히스토리

**Week 21-22: 데이터 분석 & 리포트**
- [ ] 월간 리포트 생성
- [ ] 차트/그래프 (Recharts)
- [ ] CSV/PDF 내보내기
- [ ] 성능 지표 대시보드

**Week 23-24: 배포 & 최적화**
- [ ] 프로덕션 배포
- [ ] 성능 최적화 (로딩 시간 <3초)
- [ ] 보안 강화 (SSL, CORS)
- [ ] 모니터링 설정 (Sentry)
- [ ] 문서 작성 완료

**산출물:**
- 프로덕션 서비스
- 사용자 가이드
- 모니터링 대시보드
- 운영 매뉴얼

---

## 5️⃣ 즉시 시작 (Week 1)

### Week 1 Action Items

**Day 1-2: 기술 스택 최종 승인**
```
□ Frontend: React Native + Expo (이유: 동시 개발, 빠른 배포)
□ Backend: Python + FastAPI (이유: 개발 속도, 문서화)
□ Database: PostgreSQL + Redis (이유: 확장성, 성능)
□ Cloud: AWS (이유: 국내 지원, 커뮤니티)
```

**Day 3-4: 개발 환경 구축**
```bash
# Backend
git clone <repo>
python -m venv venv
pip install fastapi uvicorn sqlalchemy psycopg2
# 또는 pip install -r requirements.txt

# Frontend (React Native)
npx create-expo-app dolbomcare-app
cd dolbomcare-app
npm install

# Frontend (Web)
npx create-next-app@latest dolbomcare-web
cd dolbomcare-web
npm install
```

**Day 5: 첫 배포 테스트**
```
□ AWS EC2 인스턴스 생성 (t3.medium)
□ RDS PostgreSQL 인스턴스 생성 (db.t3.small)
□ Github Actions 파이프라인 설정
□ 간단한 "Hello World" API 배포
```

---

## 6️⃣ 필요한 자원

### 개발팀 (Year 1)
```
- Backend Engineer: 1명
- Frontend Engineer (Mobile): 1명
- Frontend Engineer (Web): 0.5명
- DevOps Engineer: 0.5명
- QA/Test Engineer: 0.5명
- Product Manager: 0.5명
─────────────────────────
총: 4-5명
```

### 월간 비용 예상
```
AWS 인프라:        $300-400
개발 도구:         $100-150
  - Github Pro: $21/명
  - Slack: $6.67/명
  - Figma: $12/월
  - Sentry: $29/월
─────────────────────────
총: $400-550/월
```

### 초기 투자 (1차)
```
개발 환경 구축:    $2,000-3,000
  - 개발자 맥북/노트북
  - 모니터, 키보드 등
AWS 초기 설정:     $500-1,000
  - 네트워크, 보안, 백업
스터디 자료:       $200-300
─────────────────────────
총: $2,700-4,300
```

---

## 7️⃣ 위험 요소 & 대응 계획

| 위험 | 확률 | 영향 | 대응 |
|------|------|------|------|
| 음성 기록 API 지연 | 중간 | 높음 | Week 17로 미루거나 간단한 음성 저장만 우선 |
| 팀원 이탈 | 중간 | 높음 | 빨리 온보딩, 문서화, 페어 프로그래밍 |
| 성능 저하 | 낮음 | 높음 | Week 15-16부터 부하 테스트 (k6, JMeter) |
| 보안 취약점 | 중간 | 높음 | OWASP 검사, 정기 코드 리뷰, 침투 테스트 (Month 6) |
| DB 스키마 변경 | 높음 | 중간 | 마이그레이션 도구 (Alembic) 초기부터 사용 |
| 일정 지연 | 높음 | 높음 | **2주 버퍼** 계획 (총 26주 → 6개월) |

---

## 8️⃣ 성공 지표 (Month 6 종료 시)

✅ **기능 완성도**
- 3개 앱 모두 프로덕션 배포
- 90%+ 기능 완성
- 자동 테스트 커버리지 >70%

✅ **성능**
- API 응답 시간 <200ms
- 앱 로딩 시간 <3초
- 99.5%+ 가용성

✅ **보안**
- OWASP Top 10 모두 통과
- SSL/TLS 적용
- 침투 테스트 통과

✅ **팀 역량**
- 모든 팀원이 풀 스택 이해
- 자동화된 배포 프로세스
- 자동화된 테스트 <1시간

---

## 9️⃣ 선택 사항 (Beyond MVP)

Month 7+에 고려:
- [ ] AI 기반 입소자 추천 (예: 외로움 감지)
- [ ] 고급 분석 (기계학습 기반 건강 예측)
- [ ] 다국어 지원
- [ ] 웹훅 연동 (병원, 약국 시스템)
- [ ] 모바일 결제 (센터 요금 결제)

---

## 최종 확인

이 계획으로 진행할까요?

아래 중 수정이 필요한 항목을 체크하세요:
- [ ] 기술 스택 변경 필요? (어디?)
- [ ] 일정 조정 필요? (어디?)
- [ ] 기능 삭제/추가? (뭐?)
- [ ] 팀 구성 변경? (누구?)

**승인 후 Week 1 시작 가이드를 별도 문서로 작성하겠습니다.**
