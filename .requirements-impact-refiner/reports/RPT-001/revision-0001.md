# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| `RPT-001` | 1 | none | post-decision |

## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | 내장 그래프 자격증명 마스킹 | 여러 줄·raw string·escape 값이 영향도 영수증에 노출될 수 있다. | 로컬 영수증과 그래프 증거 | 자격증명 RHS가 단순 한 줄 문자열이 아닐 때 | critical | 경계가 제한된 문자열 상태 스캐너와 end-to-end 누출 테스트를 사용한다. | refining |
| `IMP-002` | Fast Scan 완료 승격 | 불완전한 결과가 complete로 승인될 수 있다. | rir_scan에서 rir_begin으로 이어지는 흐름 | provider unavailable 접두사 뒤에 추가 불완전성이 있을 때 | high | coordinator 소유의 정확한 사유만 승격 대상으로 인정한다. | refining |
| `IMP-003` | 내장 그래프 import edge 분류 | 무관한 파일이 구조적 영향으로 과대평가될 수 있다. | Python 및 JavaScript/TypeScript 의존 경로 | import binding 또는 suffix가 파일명과 겹칠 때 | high | 언어별 모듈 지정자만 추출하고 정확한 정규화 일치만 허용한다. | refining |
| `IMP-004` | controller/MCP 소스 인벤토리 | 검사하지 못한 파일이 있어도 완료로 표시될 수 있다. | 직접 graph/controller 호출자 | regular source open/read가 실패할 때 | high | 모든 진입점이 동일한 읽기 실패 분류와 incomplete frontier를 사용한다. | refining |
| `IMP-005` | 모델용 compact 그래프 | 토큰 사용량이 급증하고 frontier 사유가 소실될 수 있다. | 상세 영향도 분석의 compact_graph | 긴 문자열 또는 선행 frontier가 노드 예산을 초과할 때 | high | 직렬화 바이트 예산과 frontier 우선의 결정적 수용을 적용한다. | refining |
| `IMP-006` | Fast Scan 표시 | 선언한 180단어 상한을 초과한다. | 모든 사용자 표시 모드 | 본문이 예산을 정확히 소비하고 다음 줄이 잘릴 때 | medium | 말줄임표를 본문 예산에서 선차감한다. | refining |
| `IMP-007` | 한·영·일 기능 설명 | 사용자가 import 추론 범위를 잘못 이해할 수 있다. | GitHub 및 설치 사용자 | 내장 스캐너 제한사항을 읽을 때 | low | AST/의미론적 해석과 lexical import inference를 구분한다. | refining |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| `REQ-001` | Harden the fable-optimization branch so credential redaction covers multiline, escaped, and Go raw-string values; provider-limited scans cannot promote from free-form reason prefixes; Python and JavaScript/TypeScript imports do not create false structural edges; unreadable sources make all scan entrypoints incomplete; compact graph delivery preserves actionable frontiers and stays within a real serialized byte budget; the renderer stays within 180 words; and English, Korean, and Japanese documentation accurately describes lexical import inference. | User request and supplied repository evidence. |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| `REQ-001` | 메인 병합 전에 fable-optimization의 자격증명 비공개성, 보수적 완료 판정, import 구조 추론, 모든 진입점의 완전성 표기, 실제 바이트 제한 compact 전달, 180단어 한도와 다국어 문서 정확성을 테스트 우선으로 보장한다. | `DEC-001` | none |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| `INV-001` | 자격증명 값은 지원 문자열 문법에서 노드·에지·영수증 증거에 원문으로 나타나지 않는다. | verified | 일반 한 줄 값의 해시 치환 동작과 기존 테스트. |
| `INV-002` | 불완전성이나 의견 불일치가 남은 스캔은 complete/promotable로 승격되지 않는다. | verified | 현재 상태 판정은 inventory, budget status, frontier를 사용한다. |
| `INV-003` | structural-inferred import edge는 실제 모듈 지정자가 대상 파일을 지칭할 때만 생성된다. | verified | 내장 그래프가 imports와 references 및 confidence를 기록한다. |
| `INV-004` | 읽지 못한 소스와 잘린 경로·frontier는 완전한 범위로 표현되지 않는다. | verified | 영수증에 inventory completeness 및 truncation/frontier가 존재한다. |
| `INV-005` | Fast Scan 표시와 compact 그래프는 선언된 단어·바이트 예산 안에서 안전 정보를 보존한다. | verified | 현재 WORD_LIMIT 및 compact list cap이 존재한다. |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| `INV-001` | `REQ-001` | `IMP-001` | 일반 한 줄 값의 해시 치환 동작과 기존 테스트. |
| `INV-002` | `REQ-001` | `IMP-002` | 현재 상태 판정은 inventory, budget status, frontier를 사용한다. |
| `INV-003` | `REQ-001` | `IMP-003`, `IMP-007` | 내장 그래프가 imports와 references 및 confidence를 기록한다. |
| `INV-004` | `REQ-001` | `IMP-004` | 영수증에 inventory completeness 및 truncation/frontier가 존재한다. |
| `INV-005` | `REQ-001` | `IMP-005`, `IMP-006` | 현재 WORD_LIMIT 및 compact list cap이 존재한다. |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IMP-001` | `REQ-001` | authorization/privacy | critical | refining | unknown | 여러 줄, Go backtick, escaped quote 값이 edge evidence까지 남는 것을 재현했다. | `INV-001` | `DEC-001` | `AC-001` |
| `IMP-002` | `REQ-001` | functionality | high | refining | unknown | 불완전 사유가 complete/can_promote=True로 승격되는 것을 재현했다. | `INV-002` | `DEC-001` | `AC-002` |
| `IMP-003` | `REQ-001` | interfaces | high | refining | unknown | TypeScript auth binding과 oauth suffix가 무관한 auth 파일을 structural-inferred로 연결했다. | `INV-003` | `DEC-001` | `AC-003` |
| `IMP-004` | `REQ-001` | operations | high | refining | unknown | 권한 없는 regular file에서 inventory complete=True와 builtin closed를 재현했다. | `INV-004` | `DEC-001` | `AC-004` |
| `IMP-005` | `REQ-001` | operations | high | refining | unknown | 48개 노드와 8개 경로로 약 60KB 출력 및 frontier 소실을 재현했다. | `INV-005` | `DEC-001` | `AC-005` |
| `IMP-006` | `REQ-001` | functionality | medium | refining | unknown | 경계 입력에서 181단어 출력을 재현했다. | `INV-005` | `DEC-001` | `AC-007` |
| `IMP-007` | `REQ-001` | compatibility | low | refining | unknown | README 설명과 실제 imports edge 생성 구현이 모순된다. | `INV-003` | `DEC-001` | `AC-008` |

## Decisions and Accepted Risks

| Decision ID | Choice | Requirement revision | Accepted impacts | Rationale |
| --- | --- | --- | --- | --- |
| `DEC-001` | 재현된 모든 병합 차단 항목을 공개 인터페이스를 유지하며 테스트 우선으로 수정한다. | `REQ-001` | `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004`, `IMP-005`, `IMP-006`, `IMP-007` | 사용자가 제시된 수정 설계를 승인하고 진행을 명시했다. |

## Impact Delta

| Category | Impact IDs |
| --- | --- |
| resolved | none |
| mitigated | none |
| unchanged | none |
| accepted | none |
| deferred | none |
| blocked | none |
| superseded | none |
| reopened | none |
| new | `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004`, `IMP-005`, `IMP-006`, `IMP-007` |

## Requirement Revision History

| Requirement ID | Revision | Decision | Superseded impacts | Change summary |
| --- | --- | --- | --- | --- |
| `REQ-001` | 메인 병합 전에 fable-optimization의 자격증명 비공개성, 보수적 완료 판정, import 구조 추론, 모든 진입점의 완전성 표기, 실제 바이트 제한 compact 전달, 180단어 한도와 다국어 문서 정확성을 테스트 우선으로 보장한다. | `DEC-001` | none | Controller-created refinement revision. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| `AC-001` | `REQ-001` | `IMP-001` | `INV-001` | 한 줄·여러 줄·escaped quote·Go backtick 값이 redacted text와 최종 edge evidence에 남지 않는다. | 실패 후 통과하는 실제 동작 테스트 또는 다국어 문서 검토. |
| `AC-002` | `REQ-001` | `IMP-002` | `INV-002` | provider unavailable 외 의미가 섞인 frontier는 partial이며 can_promote=False다. | 실패 후 통과하는 실제 동작 테스트 또는 다국어 문서 검토. |
| `AC-003` | `REQ-001` | `IMP-003` | `INV-003` | Python과 JS/TS에서 모듈 지정자만 structural import를 얻고 binding·suffix 충돌은 lexical이다. | 실패 후 통과하는 실제 동작 테스트 또는 다국어 문서 검토. |
| `AC-004` | `REQ-001` | `IMP-004` | `INV-004` | 모든 진입점에서 읽을 수 없는 regular source는 incomplete/provider_limited와 frontier를 만든다. | 실패 후 통과하는 실제 동작 테스트 또는 다국어 문서 검토. |
| `AC-005` | `REQ-001` | `IMP-005` | `INV-005` | 계약상 긴 문자열과 깊은 경로에서도 compact JSON은 24,000바이트 이하이고 참조 가능하다. | 실패 후 통과하는 실제 동작 테스트 또는 다국어 문서 검토. |
| `AC-006` | `REQ-001` | `IMP-005` | `INV-004` | 수용 불가 frontier 뒤의 이미 선택된 노드 관련 위험 사유도 보존된다. | 실패 후 통과하는 실제 동작 테스트 또는 다국어 문서 검토. |
| `AC-007` | `REQ-001` | `IMP-006` | `INV-005` | 말줄임표와 footer를 포함한 표시가 180단어를 넘지 않는다. | 실패 후 통과하는 실제 동작 테스트 또는 다국어 문서 검토. |
| `AC-008` | `REQ-001` | `IMP-007` | `INV-003` | 세 언어 문서가 AST 해석은 없지만 lexical import inference는 있음을 설명한다. | 실패 후 통과하는 실제 동작 테스트 또는 다국어 문서 검토. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| 내장 그래프 및 Fast Scan 파이프라인 | 지정된 scripts와 tests 및 직접 재현 | 직접 증거는 높지만 외부 provider PATH는 예산 소진으로 미확인. |
| 설치용 미러와 다국어 README | skills 미러 및 README.md/ko/ja | 파일 비교와 문서 직접 검토. |
| Graph paths for IMP-001 | 그래프 검사가 예산 소진으로 PATH를 생성하지 못했으므로 supplied-only 직접 코드 검토와 재현 증거만 사용한다. | provider unavailable; confidence unknown; location unavailable |
| Graph paths for IMP-002 | 그래프 검사가 예산 소진으로 PATH를 생성하지 못했으므로 supplied-only 직접 코드 검토와 재현 증거만 사용한다. | provider unavailable; confidence unknown; location unavailable |
| Graph paths for IMP-003 | 그래프 검사가 예산 소진으로 PATH를 생성하지 못했으므로 supplied-only 직접 코드 검토와 재현 증거만 사용한다. | provider unavailable; confidence unknown; location unavailable |
| Graph paths for IMP-004 | 그래프 검사가 예산 소진으로 PATH를 생성하지 못했으므로 supplied-only 직접 코드 검토와 재현 증거만 사용한다. | provider unavailable; confidence unknown; location unavailable |
| Graph paths for IMP-005 | 그래프 검사가 예산 소진으로 PATH를 생성하지 못했으므로 supplied-only 직접 코드 검토와 재현 증거만 사용한다. | provider unavailable; confidence unknown; location unavailable |
| Graph paths for IMP-006 | 그래프 검사가 예산 소진으로 PATH를 생성하지 못했으므로 supplied-only 직접 코드 검토와 재현 증거만 사용한다. | provider unavailable; confidence unknown; location unavailable |
| Graph paths for IMP-007 | 그래프 검사가 예산 소진으로 PATH를 생성하지 못했으므로 supplied-only 직접 코드 검토와 재현 증거만 사용한다. | provider unavailable; confidence unknown; location unavailable |
| Impact graph coverage | Impact scan: 8.6 s · codegraph (missing) + scip (missing) + ast-grep (missing) + builtin (ready) · 6 nodes / 0 edges · 3 unknown frontiers | budget_exhausted; receipt 41d432e426403e1ef8035e65c923996c; sha256 ca6748705a108af112f383da1b699a14061d4a83e7ca52d31fa6c751b009c760; frontier FRONTIER-001,FRONTIER-002,FRONTIER-003 |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| `REQ-001` | `REQ-001`, `INV-001`, `INV-002`, `INV-003`, `INV-004`, `INV-005`, `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004`, `IMP-005`, `IMP-006`, `IMP-007`, `DEC-001` | `IMP-001`, `IMP-002`, `IMP-003`, `IMP-004`, `IMP-005`, `IMP-006`, `IMP-007` | `AC-001`, `AC-002`, `AC-003`, `AC-004`, `AC-005`, `AC-006`, `AC-007`, `AC-008` | superpowers:after-approved-brainstorming;impact-refinement;manual-handoff-before-writing-plans |
