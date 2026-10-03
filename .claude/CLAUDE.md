# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes + dolbomcare project-specific instructions.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

---

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

**dolbomcare specific:**
- Before adding features, check if it's in the MVP roadmap (Phase 1: basic functionality only)
- Always verify Backend ↔ Mobile integration requirements

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

**dolbomcare specific:**
- Focus on: Login → Data Recording → Dashboard (in that order)
- Skip: Medical integration (Phase 2), Advanced analytics (Phase 2)
- Code should work with PostgreSQL 15, FastAPI, React Native

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

**dolbomcare specific:**
- All files created ONLY in: `D:\dolbomcare\...`
- Never create files in `C:\Users\COM` (project path rule)
- Commit frequently with clear messages (focus on WHY, not WHAT)

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Build feature X" → "Test it in Backend, then test it in Mobile"

**dolbomcare specific:**
- Backend success: API responds correctly + Swagger docs show endpoint
- Mobile success: Screen renders + button navigation works
- Integration success: Mobile receives data from Backend API

---

## 프로젝트별 가이드

### 프로젝트 개요
**dolbomcare** - 2026년 한국 요양관리(care management) 플랫폼
- 목표: 요양사 독립성 + 의료기관 연계 + 보호자 신뢰
- 시장: 65.82억 USD (연평균 10.6% 성장)
- 로드맵: MVP(6개월) → 상용화(12개월) → 전국 확장(24개월)

### 현재 상태 (2026-09-29)
- ✅ 시장 조사 + 경쟁사 분석 + K-스타트업 평가 (92/100, 선정 확률 70-80%)
- ✅ Backend 기본 구조 (FastAPI, 11개 모델, JWT 인증)
- ✅ Mobile 기본 구조 (React Native, 로그인, 대시보드, 라우팅)
- ✅ Python 3.11 + PostgreSQL 15 (포트 5433) 설치
- ✅ Git 저장소 초기화 및 첫 커밋 완료

### 실행 중인 서버
```
🚀 Backend: http://localhost:8000
   - API Docs: http://localhost:8000/docs (Swagger)
   - Status: http://localhost:8000/

🚀 Mobile (Expo): http://localhost:8081
   - Web: http://localhost:8081 (press 'w' in Expo CLI)
   - QR Code: Expo Go 앱에서 스캔 가능
```

### 실행 명령어

**Backend 시작:**
```powershell
cd D:\dolbomcare\backend
.\venv\Scripts\Activate.ps1
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**Mobile 시작:**
```powershell
cd D:\dolbomcare\mobile
npx expo start
# 그 후 'w' 눌러서 웹에서 실행
```

### 환경 설정 (.env)
```
DATABASE_URL=postgresql://postgres:ckswns4244@localhost:5433/dolbomcare_db
DEBUG=True
ENVIRONMENT=development
SECRET_KEY=your-secret-key-change-in-production-2026
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
```

### 다음 단계 (우선순위 순서)
1. **로그인 기능 완성** (Backend ↔ Mobile 연동)
   - 테스트 계정 생성 (caregiver, center_manager)
   - 토큰 저장/검증
   - 대시보드 진입 가능 확인

2. **PostgreSQL 데이터베이스 연결**
   - 테이블 자동 생성
   - CRUD 작업 테스트
   - 데이터 조회 확인

3. **음성 기록 기능 기본 구현**
   - Voice-to-Text API 통합
   - 데이터 저장
   - 조회 기능

### 발견된 실수 및 개선사항

#### 1. 파일 경로 관리 (고정)
- **문제**: 파일이 C:\Users\COM에 생성됨
- **해결**: 모든 파일은 D:\dolbomcare에만 생성
- **규칙**: Write/Edit 사용 시 D:\dolbomcare\... 경로 명시

#### 2. DATABASE_URL 특수 문자 문제
- **문제**: 비밀번호에 @ 문자 있으면 파싱 오류
- **해결**: 비밀번호에 특수문자 제거 (ckswns4244 사용)

#### 3. PostgreSQL 포트 설정
- **문제**: 포트가 5432가 아닌 5433으로 설정됨
- **해결**: .env에 포트 5433으로 명시

#### 4. requirements.txt 의존성
- **문제**: jose, email-validator 패키지 누락
- **해결**: python-jose, email-validator, bcrypt 추가

#### 5. ⚠️ Backend 데이터베이스 자동 생성 비활성화 (매우 중요!)
- **규칙**: main.py 16번 줄의 `Base.metadata.create_all(bind=engine)` 반드시 주석 처리!
- **이유**: PostgreSQL 연결 실패 시 서버 시작 불가
- **위험**: 활성화 상태로 서버 시작 → 모든 테이블 초기화 → 전체 데이터 손실!
- **2026-10-03 교훈**: 비활성화 상태 확인 안 했다가 데이터 손실 (VoiceRecords, Salaries 등)
- **확인 방법**: Backend 시작 전에 항상 main.py 16번 줄 확인
- **현재**: 주석 처리됨 ✅

---

## 주의사항

### 코드 품질 원칙
- 함수/변수명으로 의도가 명확해야 함 (주석 최소화)
- 3줄 반복은 괜찮음 (과도한 추상화 금지)
- 불완성 구현 금지

### Git 커밋
- 메시지는 WHY를 중심으로 작성
- 빈번한 커밋 (큰 덩어리보다는 작은 단위)
- 분석/계획 문서는 커밋하지 않기

### 테스트 검증
- UI 변경 후 브라우저/앱에서 직접 테스트
- 행복 경로(happy path) + 엣지 케이스 모두 확인
- 자동 테스트는 정확성 검증이지, 기능 검증이 아님

---

**These guidelines work if:** fewer unnecessary changes in diffs, faster implementation loops, and clarifying questions come before code rather than after mistakes.
