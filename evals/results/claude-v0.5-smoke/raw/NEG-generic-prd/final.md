I have gathered all the repository evidence (MVP scope, scenarios, constraints, feature list, IA/design, policy docs). Here is the complete PRD, written in Korean to match the repository's documentation language, synthesized from `/Users/p042890/workspace/polaris/submission/1_기획서/01~04`, `POLICY.md`, `DESIGN.md`, `TODO.md`.

---

# POLARIS 제품 요구사항 정의서 (PRD)

| 항목 | 내용 |
| --- | --- |
| 제품명 | POLARIS — 접근정책 신청·검토·승인·반영·회수 엔터프라이즈 AI 업무 포털 |
| 문서 버전 | v1.0 (2026-08-25) |
| 근거 문서 | `submission/1_기획서/01_MVP_개발범위.md`(M-*), `02_사용자_데모_시나리오.md`(SC-*), `03_제약사항_및_가정.md`, `04_기능목록_AI_식별.md`(F-*/AI-*), `POLICY.md`, `DESIGN.md`, `TODO.md` |
| 마감 | 본선 제출 2026-09-03 23:59, 코드 동결 2026-09-02 |

## 1. 배경과 문제 정의

프로젝트에 신규 인력이 투입될 때마다 방화벽·서버·DB 접근권한을 개별 정책 단위로 반복 신청한다. 이 방식은 세 가지 고질적 문제를 만든다.

1. **반복 입력과 시간 낭비** — 인력 1명당 수십 건의 정책을 수기로 작성해 신청서 1건에 약 30분이 소요된다.
2. **누락·과다·오입력** — 필수 권한 누락으로 업무가 지연되고, 역할 대비 과다 권한(예: 운영 DB 쓰기)이 통제 없이 승인된다.
3. **잔존 권한** — 인력 철수나 정책 변경 후에도 권한이 회수되지 않아 보안 위험으로 남는다.

POLARIS는 권한을 낱개 정책이 아닌 **"출발지 패키지 ↔ 목적지 패키지의 승인된 연결"**로 관리하고, AI 추천·룰 엔진 검토·사람의 승인·목업 반영·검증·자동 회수를 하나의 흐름으로 연결한다.

## 2. 제품 비전과 핵심 차별점

> 다수 멤버 선택 → AI 목적지 패키지 추천 → 연결 신청 → 위험 검토 → 승인 → 목업 반영 → 반영 누락 탐지 → 패키지 변경 회수

핵심 차별점은 **비대칭 통제(M-07)**다.

- **제거는 자동**: 목적지 패키지에서 정책을 제거하면 연결된 모든 멤버의 권한이 별도 승인 없이 즉시 자동 회수된다.
- **추가는 승인**: 신규 정책은 보안 검토와 고객사 승인을 통과해야만 반영된다.

이 비대칭 통제는 축소 불가 항목이며 제품 혁신성의 핵심 증빙이다.

## 3. 핵심 도메인 개념

| 개념 | 정의 |
| --- | --- |
| 출발지 패키지 | 프로젝트 멤버 1명이 접근을 시도하는 위치. IP·CIDR Endpoint 묶음. 멤버당 1개. **버전 없이 현재 상태만 관리**(버전 관리는 Should F-074) |
| 목적지 패키지 | 업무 목적으로 묶인 서버·도메인·DB 자원과 자원별 프로토콜·포트·접근 수준. 프로젝트·환경 범위를 가지며 **버전으로 변경 관리** |
| 패키지 연결 | 출발지 ↔ 목적지 사이의 승인된 관계. 유효 정책은 이 연결에서 결정적으로 전개 |
| 정책 작업 | 연결 생성·변경 시 계산되는 ADD/DELETE 작업. `FIREWALL`, `SERVER`, `DATABASE` 유형 |

## 4. 대상 사용자

### 4.1 로그인 사용자 (역할 코드는 09_ERD 5.2.1이 단일 기준)

| 사용자 | 코드 | 핵심 과업 |
| --- | --- | --- |
| 프로젝트 실무자 | `PROJECT_PRACTITIONER` | 출발지·목적지 패키지 관리, 멤버 대리 연결 신청, AI 추천 확인·수정, 재제출 |
| 보안 담당자 | `SECURITY_REVIEWER` | 최소권한·누락·과다·중복·충돌 검토, 수정 요청·검토 완료 |
| 고객사 담당자 | `CUSTOMER_MANAGER` | 업무 필요성·변경 영향 확인 후 최종 승인·반려 |
| 시스템 관리자 | `SYSTEM_ADMIN` | 기준정보, 목업 반영·검증·재처리, 데모 초기화 |

### 4.2 로그인하지 않는 프로젝트 멤버
권한을 부여받는 투입자. 실무자가 대리 신청한다. 담당업무: PL·기획자·Designer·FE·BE·DA·QA. 회원가입 없음 — DB 시드 테스트 계정, Spring Boot 세션 인증(HttpOnly 쿠키).

## 5. 목표와 성공 지표

### 정성 완료 기준 (MVP)
- 다수 멤버의 출발지 패키지에 추천 목적지 패키지를 연결해 하나의 신청으로 제출 가능
- AI 추천에 추적 가능한 근거(패키지·정책 ID) 표시
- 누락·과다·중복·충돌 결함 사례 탐지, 역할별 검토·승인 수행
- 승인 작업과 목업 반영 결과 불일치 탐지, 제거 정책 전원 자동 회수
- 신규 추가 정책은 승인 전 미반영(비대칭 통제), LLM 실패 시 자동 승인 없이 안전모드
- 배포 URL에서 전체 시나리오 반복 실행

### 정량 목표
| 지표 | AS-IS | TO-BE |
| --- | --- | --- |
| 신청서 작성 시간 | 약 30분 | **5분 이내** |
| 주입 결함(누락·오입력) 탐지율 | — | **90% 이상** |
| 초기화 데이터 기준 핵심 시나리오 성공률 | — | **10회 중 9회 이상** |

## 6. 기능 요구사항

### 6.1 Must (M-01 ~ M-08)

**M-01 출발지·목적지 패키지 관리** (F-010, F-011, F-012, F-013)
- 출발지: 멤버당 1개 생성·조회·수정, IP·CIDR Endpoint 1개 이상, 현재 상태만 + 감사 이력
- 목적지: 업무 목적 기준 생성·조회·수정, 자원별 프로토콜·포트·접근 수준 정책 항목, 버전 번호·변경 전후·사유 단순 이력(복원 없음)
- 자원 카탈로그는 합성 시드, 별도 관리 화면 없음. 패키지 화면 하나에서 유형 탭(`?type=source|destination`)으로 전환

**M-02 다수 멤버 일괄 연결 신청** (F-020~F-023)
- 여러 멤버 선택 시 소속·담당업무·프로젝트·출발지 패키지 자동 연결
- 사용자는 목적지 패키지와 투입 기간만 확인·지정, 하나의 신청으로 다수 연결 일괄 생성
- AI 추천 외 직접 검색·추가 제공

**M-03 AI 권한 패키지 추천** (F-021, AI-02)
- 멤버의 프로젝트·담당업무·환경 + 활성 목적지 패키지 기반 후보 추천
- 결과에 패키지 ID·근거·일치 항목·주의사항 표시, JSON 스키마 검증, 근거 없으면 자동 제출 금지

**M-04 보안 위험 검토** (F-030~F-032, AI-03)
- 룰 엔진이 최소권한·환경 분리·만료·중복·충돌 우선 검사(결정적)
- AI가 룰 결과+신청 맥락으로 위험도·근거 설명(Hybrid), 최종 결정은 보안 담당자

**M-05 고객사 승인 지원** (F-040, F-041, AI-04)
- 신청 목적·대상 인력·변경 권한·위험도·검토 결과 요약, 승인·반려는 사람만. **AI는 승인권 없음**

**M-06 공통 목업 반영과 검증** (F-050~F-052)
- 단일 공통 Mock Adapter가 `FIREWALL`/`SERVER`/`DATABASE` 유형별 반영 결과 생성(일괄 실행)
- Provisioning Verifier가 승인값과 결과를 대조, 의도적 누락 탐지·원인·영향 사용자 표시, 실패 항목 1회 재실행

**M-07 패키지 변경 자동 회수 — 비대칭 통제** (F-060~F-062) *축소 불가*
- 정책 제거 시 연결 기준 영향 멤버 전원 식별 → 승인 없이 즉시 자동 회수
- 신규 추가는 보안 검토·고객사 승인 후에만 반영, 결과·영향 멤버 감사 이력 기록

**M-08 배포·데모 재현성** (F-001, F-002, F-080, F-090, F-091)
- Vercel 배포 URL + 역할별 데모 계정, 합성 데이터만 저장, 데모 초기화 절차, 시크릿 창·타 브라우저 시연 가능

### 6.2 Should (Must 안정화 후)
- F-073 정책 작업 의존 순서 순차 실행(`ADD → 검증 → DELETE`)과 중간 실패 롤백
- F-074 출발지 패키지 버전 관리(ACTIVE/PENDING 비교)
- F-075 보안 검토·승인·반영 독립 큐 화면(Must는 신청 목록의 역할별 큐 필터로 대체)
- F-070 개별 예외 정책 신청 + 기본 30일 만료, F-072 철수·만료 이벤트 자동 회수
- 반영 실패 재처리 강화, AI 호출량·비용·응답시간 기록

### 6.3 Could
제한적 RAG(AI-06), 반복 예외 패키지 편입 제안(AI-05), 미사용 권한 분석(AI-07), 멀티 Agent, 고급 대시보드(F-102)

### 6.4 제외 범위
실제 고객사·사내 데이터, 실제 방화벽·서버·DB·PAM·IAM 제어, SSO·전자결재·인증서 연동, 무감독 AI 자동 승인, 전사 패키지 거버넌스, 운영 수준 HA·DR, 다국어, 회원가입·MFA·비밀번호 복구

## 7. AI 기능 명세

구현 대상 Must AI 3종 — 동일 LLM API·공통 구조화 출력·로깅·안전모드 모듈 재사용, 별도 Agent 분리 없음:

| ID | 기능 | 입력 | 구조화 출력 | 사람의 통제 | 평가 |
| --- | --- | --- | --- | --- | --- |
| AI-02 Package Recommender | 목적지 패키지 추천 | 담당업무, 프로젝트, 활성 패키지 목록 | 추천 ID, 점수, 일치 항목, 근거 | 신청자가 검색·수정·제출 | 정답 세트 Top-k 적중률, 근거 일치율 |
| AI-03 Security Explainer | 위험 설명·수정 권고 | 신청 항목, 룰 위반 목록, 역할·환경 | 위험도, 근거 정책 ID, 설명, 권고 | 보안 담당자 검토·수정 | 결함 설명 커버리지, 사실 일치율 |
| AI-04 Approval Copilot | 승인 요약 | 목적, 영향 멤버, 변경 작업, 위험 결과 | 업무 목적, 변경 범위, 위험도, 주의사항 | 고객사 담당자 승인·반려 | 필수 필드 충족률, 사실 일치율 |

AI-01 Package Curator(패키지 현행화 후보 제안)는 Must 유지/Should 이동 결정 대기.

**AI/비-AI 경계 원칙**: 룰 판정, 상태 전이·승인권, 반영 대조, 영향 멤버 계산, 자동 회수, 감사는 결정적 룰·자동화로 처리하고 AI로 홍보하지 않는다.

**AI 안전장치 (F-091, SC-06)**
- 정의된 JSON 스키마 외 출력 거부, 근거 정책 ID 없는 추천은 승인 단계 전달 금지
- 타임아웃 시 1회만 재시도 → 실패 시 규칙 기반 안전모드(직접 검색 + 룰 결과)로 전환, 실패 상태를 화면에 표시
- 검증된 데모 입력은 캐시 응답으로 시연 가능(외부 장애 대비용)
- 모델·프롬프트 버전·입력 참조 ID·출력·사람의 수정을 감사 이력에 기록
- LLM 런타임은 Vercel AI Gateway 경유 Claude 모델(모델·예산 확정 대기), Gateway 장애 시 미승인 모델 자동 전환 차단

## 8. 사용자 시나리오 (수용 시나리오)

- **SC-00** 패키지 생성·현행화 — AI가 자동 확정하지 않고, 목적지는 검토된 버전으로 저장
- **SC-01** 신규 멤버 10명 일괄 연결 신청 — 멤버·패키지·기간만으로 신청 생성, 추천 근거·위험 결과 기록
- **SC-02** 과다·누락 권한 탐지 — 필수 DB 조회 누락과 운영 DB 쓰기 과다를 구분 탐지, 수정 요청→재검토
- **SC-03** 고객사 승인 — AI 요약 확인 후 사람이 승인·반려, 결정자·시간·사유 감사 기록
- **SC-04** 반영 누락 탐지 — Mock Adapter의 의도적 DB Role 누락을 대조로 탐지, 재처리 후 완료
- **SC-05** 노후 서버 제거 + 대체 서버 추가 — 20명 영향 산출, 제거 즉시 회수·추가는 승인 대기(비대칭 통제 증빙)
- **SC-06** LLM 장애 — 1회 재시도 후 안전모드, 자동 승인 없음, 캐시로 시연 지속

데모 권장 순서: 문제 설명(30초) → SC-00 → SC-01 → SC-02 → SC-03 → SC-04 → SC-05 → 지표·감사 확인. 목표 5~7분.

## 9. 상태 모델

**신청 상태**: `DRAFT → SECURITY_REVIEW → CUSTOMER_APPROVAL → APPROVED → APPLYING → COMPLETED | PARTIAL_FAILED → REVOKED` (수정 요청·반려는 DRAFT로 복귀, PARTIAL_FAILED는 재실행으로 APPLYING 복귀). 정책 제거는 승인 경로를 거치지 않고 즉시 회수 — 일부 회수 시 신청은 COMPLETED 유지·해당 할당만 REVOKED, 전체 회수 시 신청 REVOKED.

**목적지 패키지**: `DRAFT → ACTIVE → INACTIVE`. **패키지 버전**(UI 기준, IA 4.9.2): `DRAFT → PENDING → APPROVED → APPLYING → ACTIVE → PARTIAL_FAILED / SUPERSEDED`. 출발지 패키지는 ACTIVE/INACTIVE만.

## 10. 비기능 요구사항

**보안**
- 프론트엔드는 Supabase에 직접 접근하지 않는다. DB 자격증명·LLM 키는 Backend/Vercel 환경변수만 사용, 저장소·제출물에서 제외
- 역할은 사용자가 수정 불가한 Backend 역할 테이블 + 세션 검증, 서버·데이터 계층에서도 역할 검증
- AI 입출력·로그에 실제 개인정보·기밀 금지, 합성 데이터만 사용
- 미결: Spring JDBC 직결 구조에서 RLS 적용 방식(05_아키텍처 13.5 대응안 승인 필요)

**아키텍처·스택** (POLICY.md)
- 모노레포: `frontend/`(Next.js·React·TS, App Router) + `backend/`(Java 17·Spring Boot: Core Workflow, 인가, AI/Rule 연동, Mock Adapter, 검증, Lifecycle/회수) + `supabase/`(PostgreSQL, 운영) / H2(로컬) + `contracts/openapi.yaml`(FE-BE 단일 계약)
- 배포: Vercel 독립 프로젝트 2개(FE/BE), 인증은 Spring 세션

**UX·접근성** (DESIGN.md)
- 근접 블랙·미드나이트 네이비 다크 테마, 별빛 Primary 절제 사용. WCAG AA 대비, 키보드 접근, 44px 터치 영역
- 모든 데이터 영역에 Loading/Empty/Error/AI Failure/Partial Failure/Success 상태 설계
- AI 추천·룰 결과·사람의 결정·시스템 반영을 시각적으로 구분, 부분 실패를 성공처럼 표시 금지
- 상태 Enum→레이블 매핑 원본은 `frontend/src/lib/domain.ts`
- 한국어 UI, 최신 데스크톱 Chrome 중심 + 기본 반응형

**성능·규모**: 해커톤 합성 데이터·동시 시연 사용자 수준 검증(부하시험 제외)

## 11. 일정·마일스톤과 범위 축소 규칙

| 단계 | 내용 |
| --- | --- |
| 1단계 | 범위·설계 확정 (데이터 모델·화면·API·AI 스키마 정합) |
| 2단계 | 기반 구현 (패키지 CRUD, 멤버 선택, 상태 워크플로우, Seed) |
| 3단계 | AI·핵심 시나리오 (추천, 룰 엔진, 승인, 반영, 회수) |
| 4단계 | 검증·안정화 (탐지율·재현성 측정, E2E) |
| 5~6단계 | 제출 자료 작성·최종 점검 (09-03 22:00 내부 제출) |

축소 규칙: 08-26 패키지·신청 미작동 시 Should·Could 전체 제외 → 08-27 버전 비교 미작동 시 감사 이력으로 축소 → 08-28 AI 미작동 시 추천·위험분석·승인요약 3종만 유지 → 08-30 전체 흐름 미연결 시 패키지 제거 회수만 유지 → 09-02 코드 동결.

## 12. 미결 사항 (Open Questions)

1. AI-01 Package Curator의 Must 유지/Should 이동 결정
2. LLM 제공자·모델·예산·타임아웃 확정 (Vercel AI Gateway Claude 후보 비교 중)
3. RLS 적용 방식 — Spring JDBC 직결 구조에서 Data API 미노출 + 최소 RLS + Spring Security 전담 인가 승인 여부
4. `POLICY.md` 병합 충돌 해소(현재 `contracts/openapi.yaml`도 UU 충돌 상태), 이원 모델 ERD 팀 승인, v2 개정의 B·C 합의

---

Summary for the caller: I wrote the complete PRD above (in Korean, matching the repository's documentation language) by synthesizing the product idea from the POLARIS repo — an enterprise AI portal for access-policy request/review/approval/provisioning/revocation built on a source-package ↔ destination-package connection model with "asymmetric control" (removals auto-revoke, additions require human approval) as the flagship differentiator. Key sources: `/Users/p042890/workspace/polaris/submission/1_기획서/01_MVP_개발범위.md` (M-01~M-08 scope), `02_사용자_데모_시나리오.md` (SC-00~SC-09, state machines), `03_제약사항_및_가정.md` (constraints/tailoring), `04_기능목록_AI_식별.md` (F-*/AI-* feature and AI inventory), plus `POLICY.md` (architecture), `DESIGN.md` (UX), `TODO.md` (milestones). The PRD covers problem, vision, personas, domain model, Must/Should/Could/out-of-scope requirements, AI specs with safety rails, acceptance scenarios, state models, NFRs, schedule with scope-reduction gates, and open questions (AI-01 priority, LLM model/budget, RLS approach, unresolved merge conflicts in POLICY.md/openapi.yaml).
