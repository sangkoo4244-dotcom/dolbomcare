# 🤖 dolbomcare + RUflo Integration

## 개요

RUflo를 통해 dolbomcare의 자동화 워크플로우를 구현합니다.

```
Voice Record Created
    ↓
RUflo Swarm Agents
    ├─ voice-processor (Whisper API)
    ├─ billing-approver (규칙 평가)
    ├─ quality-monitor (검증)
    └─ guardian-notifier (알림)
    ↓
Memory Learning (AgentDB)
```

---

## 📁 폴더 구조

```
.claude-flow/
├── agents.yml          # 5개 에이전트 정의
├── workflows.yml       # 5개 자동화 워크플로우
├── mcp-server.json     # 25개 MCP 도구 정의
├── mcp-server/         # MCP 서버 구현
│   ├── index.js
│   └── package.json
└── README.md          # 이 파일
```

---

## 🚀 시작하기

### 1. Backend 실행
```bash
cd D:\dolbomcare\backend
.\venv\Scripts\Activate.ps1
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 2. RUflo 실행 (ruflo 폴더)
```bash
cd D:\dolbomcare\ruflo
npx ruflo run --workflow voice_to_billing
```

### 3. API 테스트
```bash
curl http://localhost:8000/
```

---

## 🤖 5개 에이전트

### 1. voice-processor
**목적:** 음성 기록 → 텍스트 변환 → 청부 생성

**Trigger:** 
- `voice_record.created` webhook
- 매 시간마다 배치 처리

**동작:**
1. Whisper API로 음성→텍스트 변환
2. 서비스 유형 추출 (AI 기반)
3. 청부 금액 계산
4. BillingRecord 자동 생성 (pending 상태)

**모델:** claude-opus (고급 음성 분석)

---

### 2. billing-approver
**목적:** 규칙 기반 청부 자동 승인

**Trigger:**
- 4시간마다 대기 청부 조회
- `billing.pending_review` 이벤트

**동작:**
1. 대기 중인 청부 조회
2. 검증 규칙 평가 (95% 신뢰도)
   - `amount_between_bounds` - 금액 범위 확인
   - `caregiver_active` - 요양사 활성 확인
   - `resident_valid` - 이용자 유효성 확인
   - `no_duplicates` - 중복 기록 없음
   - `not_flagged` - 이상 플래그 없음
3. 통과한 청부 자동 승인
4. 미통과한 청부는 수동 검토 표시

**모델:** claude-sonnet (규칙 판단)

---

### 3. guardian-notifier
**목적:** 일일 보호자 알림 발송

**Trigger:**
- 매일 6시 (Asia/Seoul)
- `billing_approved` 이벤트

**동작:**
1. 어제 요양 기록 요약 생성
2. 건강 지표 수집
3. 보호자별 맞춤 메시지 생성 (쉬운 한국말)
4. 푸시 + 이메일 발송

**모델:** claude-haiku (경량, 빠른 응답)

---

### 4. analytics-engine
**목적:** 데이터 분석 및 리포트 생성

**Trigger:**
- 매월 1일 9시
- 요청 시 즉시 생성

**동작:**
1. 청부, 요양사, 이용자 통계 수집
2. 월별 리포트 생성 (PDF)
3. 센터장에게 이메일 발송

**모델:** claude-opus (분석)

---

### 5. quality-monitor
**목적:** 실시간 데이터 이상 감지

**Trigger:**
- 30분마다 실행
- 즉시 감지 필요 시

**동작:**
1. 청부액 편차 확인 (표준편차 2.5배)
2. 음성 텍스트 품질 확인
3. 중복 기록 감지
4. 이상 발견 시 자동 승인 일시 중지
5. 센터장에게 알림

**모델:** claude-haiku (경량)

---

## 🔄 5개 워크플로우

### Workflow 1: 음성기록→자동청부
```yaml
음성 기록 생성 (webhook)
  ↓ voice-processor
  Whisper 변환 + 서비스 유형 추출
  ↓ billing-approver
  청부 자동 생성 (pending 상태)
  ↓ quality-monitor
  검증
  ↓
  ✉️ 센터장에게 이메일 알림
```

### Workflow 2: 청부 자동승인
```yaml
4시간마다 트리거
  ↓ billing-approver
  대기 청부 조회 + 규칙 평가 (95% 신뢰도)
  ├─ 통과: 자동 승인
  ├─ 실패: 수동 검토 표시
  ↓
  ✉️ 센터장에게 요약 보고
```

### Workflow 3: 일일 보호자 알림
```yaml
매일 6시 트리거
  ↓ analytics-engine
  어제 요양 기록 요약 생성
  ↓ guardian-notifier
  보호자별 맞춤 메시지 생성
  ↓
  📱 푸시 + 📧 이메일 발송
```

### Workflow 4: 월간 센터장 리포트
```yaml
매월 1일 9시
  ↓ analytics-engine
  청부, 요양사, 이용자 통계 수집
  ↓
  📄 PDF 리포트 생성 및 이메일 발송
```

### Workflow 5: 품질 모니터링
```yaml
30분마다
  ↓ quality-monitor
  청부액 편차, 음성 품질, 중복 기록 검사
  ↓ 이상 감지 (표준편차 2.5배)
  ├─ 심각: 자동 승인 일시 중지 + 알림
  ├─ 경미: 로그 기록만
  ↓
  ✉️ 이상 항목 센터장 알림
```

---

## 🛠️ MCP 도구 (25개)

### Voice (3개)
- `dolbomcare/voice/create` - 음성 기록 생성 + Whisper 변환
- `dolbomcare/voice/list` - 조회 (필터링: resident_id, status, date_range)
- `dolbomcare/voice/archive` - 아카이브

### Billing (4개)
- `dolbomcare/billing/auto_create` - 음성→청부 자동 생성
- `dolbomcare/billing/approve` - 승인 (notes, override_amount)
- `dolbomcare/billing/reject` - 거절 (reason)
- `dolbomcare/billing/list` - 조회 (상태별, 요양사별)

### Residents (3개)
- `dolbomcare/residents/list` - 이용자 목록
- `dolbomcare/residents/get` - 상세 정보
- `dolbomcare/residents/update` - 정보 수정

### Caregivers (2개)
- `dolbomcare/caregivers/list` - 요양사 목록
- `dolbomcare/caregivers/get_performance` - 성과 지표

### Analytics (3개)
- `dolbomcare/analytics/daily_summary` - 일일 요약
- `dolbomcare/analytics/monthly_report` - 월간 리포트
- `dolbomcare/analytics/detect_anomalies` - 이상 감지

### Notifications (2개)
- `dolbomcare/notifications/push` - 푸시 알림
- `dolbomcare/notifications/email` - 이메일

---

## 🧠 Memory Learning Loop

### Pattern: billing_approval_rules
**설명:** 청부 승인 규칙 학습

**학습 방식:**
1. 매 승인마다 패턴 기록
2. 거절된 청부와 승인된 청부 비교
3. 신뢰도 기준 자동 조정 (threshold: 0.95)

**활용:**
- 향후 유사 청부 자동 승인
- 규칙 위반 자동 감지

---

## 📊 성공 지표

| 지표 | 목표 | 측정 방법 |
|------|------|---------|
| 음성→청부 자동화율 | 95% | 자동 생성된 청부 / 전체 음성 |
| 청부 자동 승인율 | 70% | 자동 승인 / 대기 청부 |
| 보호자 알림 전달률 | 95% | 성공 발송 / 총 발송 시도 |
| 품질 모니터링 응답시간 | < 5분 | 이상 감지부터 알림까지 |
| 메모리 학습 정확도 | > 90% | 학습된 규칙 정확성 |

---

## 🐛 문제 해결

### MCP 서버 연결 안 될 때
```bash
# 1. 확인: .mcp.json이 D:\dolbomcare에 있는지
# 2. 확인: Backend가 http://localhost:8000에서 실행 중인지
# 3. 로그 확인:
cd D:\dolbomcare
node .claude-flow/mcp-server/index.js
```

### 워크플로우 실행이 안 될 때
```bash
# RUflo 로그 확인
cd D:\dolbomcare\ruflo
npx ruflo run --workflow voice_to_billing --debug
```

---

## 📚 참고 자료

- [agents.yml](agents.yml) - 에이전트 정의
- [workflows.yml](workflows.yml) - 워크플로우 정의
- [mcp-server.json](mcp-server.json) - MCP 도구 정의
- [mcp-server/index.js](mcp-server/index.js) - MCP 서버 구현

---

**마지막 업데이트:** 2026-10-02
**RUflo 버전:** 3.49.0+
**상태:** ✅ 통합 준비 완료

