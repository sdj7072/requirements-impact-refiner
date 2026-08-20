[English](README.md) | 한국어 | [日本語](README.ja.md)

# Requirements Impact Refiner

Requirements Impact Refiner `0.1.0`은 구체적인 소프트웨어 변경을 구현 계획 전에 근거와 연결된 영향도 목록으로 정제하는 저장소 인식형 Agent Skill입니다. [README.md](README.md)가 의미상 기준 문서이며 [README.ko.md](README.ko.md)와 [README.ja.md](README.ja.md)는 완전한 번역본입니다.

## 1. 문제

바이브 코딩으로 만든 변경은 최신 요구사항을 만족하면서도 잘 작동하던 권한 경계, 저장된 페이로드, 모바일 클라이언트, 보존 정책, 재시도 의미론, 관측 가능성을 조용히 망가뜨릴 수 있습니다. 일반적인 요구사항 명확화는 무엇을 만들지 설명하지만, 변경이 저장소 근거를 따라 어디까지 영향을 주는지는 반드시 추적하지 않습니다.

이 스킬은 그 빈 구간을 담당합니다. 변경 내용과 검사 범위가 구체적일 때만 시작하고, 현재 동작을 불변 조건으로 기록하며, 신뢰 수준과 함께 영향 범위를 드러냅니다. 이후 사용자가 영향을 줄이거나, 보류하거나, 해결하거나, 명시적으로 수용하도록 돕습니다. 결과는 보고서 형태의 `Planning Handoff`에서 끝나며 제품 구상, 구현 계획 작성, 코드 수정, 디버깅, 코드 리뷰는 하지 않습니다.

## 2. 핵심 개념

기준 스킬은 [`skills/requirements-impact-refiner/SKILL.md`](skills/requirements-impact-refiner/SKILL.md)입니다. 모든 수정 내역을 추적할 수 있도록 안정적인 ID를 사용합니다.

| ID | 의미 |
| --- | --- |
| `REQ-###` | 최초 또는 정제된 요구사항 |
| `INV-###` | 보존이 필요할 수 있는 현재 동작 |
| `IMP-###` | 영향을 받는 동작, 계약, 데이터 경로 또는 위험 |
| `DEC-###` | 사용자나 이해관계자가 명시적으로 선택한 결정 |
| `AC-###` | 관찰 가능한 인수 또는 회귀 기준 |

근거 수준은 정확히 `verified`, `inferred`, `unknown`입니다. 영향 상태는 정확히 `detected`, `refining`, `mitigated`, `resolved`, `accepted`, `deferred`, `blocked`, `superseded`입니다. `accepted`에는 연결된 `DEC-###`가, `resolved`에는 뒷받침하는 근거가 필요합니다. 중요한 요구사항이 수정될 때마다 알려진 전체 영향 집합을 다시 계산하고, 필요하면 `new: none`까지 포함하여 중복 없는 변화량을 표시합니다.

## 3. 빠른 시작

저장소를 복제한 다음 기준 스킬을 사용하는 클라이언트에 노출합니다. 일부 크로스 클라이언트 구성은 `.agents/skills/`를 사용합니다. 이는 실용적인 관례일 뿐 Agent Skills 명세가 강제하는 설치 경로가 아닙니다.

```sh
mkdir -p .agents/skills
ln -s ../../skills/requirements-impact-refiner .agents/skills/requirements-impact-refiner
```

Codex에서는 사용하는 Codex 클라이언트의 플러그인 로딩 기능으로 이 저장소를 로컬 플러그인으로 불러옵니다. [`.codex-plugin/plugin.json`](.codex-plugin/plugin.json)의 `skills`는 `./skills/`를 가리키며 MCP 서버, hook, app, agent, dependency를 추가하지 않습니다. 이 저장소의 호환성 실행에서 검증된 Codex CLI 로딩 명령은 없으므로 특정 명령을 성공했다고 주장하지 않습니다.

Claude Code 개발 로딩은 저장소 루트에서 다음을 실행합니다.

```sh
claude --plugin-dir .
```

루트의 [`.claude-plugin/plugin.json`](.claude-plugin/plugin.json)은 Claude Code의 일반적인 루트 `skills/` 탐색 방식을 사용합니다. 이 명령은 Claude Code가 설치된 환경을 위한 안내이며, 현재 환경에는 `claude`가 없어 실행이 `blocked`되었습니다.

로딩 후에는 변경과 저장소 범위를 함께 제시합니다. 예: “계획 전에 `displayName` API 이름 변경이 API, iOS DTO, 캐시된 프로필 경로에 미치는 영향을 정제해 줘.” 오케스트레이터가 여러 개라면 정확히 하나를 선택합니다.

## 4. 예시

요청: 공개 API 필드 `displayName`을 `name`으로 변경합니다. 저장소 근거에 따르면 `ios/UserDTO.swift`가 `displayName`을 디코딩하고, 캐시된 프로필 JSON이 이 값을 저장하며, 공개 변경 이력은 한 버전의 사용 중단 유예를 약속합니다.

| 산출물 | 예시 |
| --- | --- |
| `REQ-001` | `displayName`을 `name`으로 변경한다. |
| `INV-001` | 기존 iOS 릴리스는 `displayName`을 디코딩한다. `ios/UserDTO.swift`에서 확인한 `verified` 근거. |
| `IMP-001` | 모바일 디코딩이 실패할 수 있다. 상태 `refining`, 근거 `verified`. |
| `IMP-002` | 검사하지 않은 외부 클라이언트가 `displayName`을 사용할 수 있다. 상태 `detected`, 근거 `inferred`. |
| Decision needed | 즉시 호환성 중단, 두 필드 병행, 또는 다른 명시적인 마이그레이션 정책 중 선택한다. |
| `DEC-001` | 사용자가 공개된 한 번의 사용 중단 유예 버전 동안 두 필드를 병행하기로 선택한다. |
| `REQ-002` | `name`을 도입하고 한 버전 동안 폐기 예정인 `displayName`을 보존한 뒤 호환성 기준을 통과한 후에만 제거한다. |
| `AC-001` | 해당 버전 동안 현재 iOS 디코더와 캐시 페이로드 fixture가 계속 동작한다. |

재계산된 변화량은 `IMP-001`을 `mitigated`에 배치하고, 외부 소비자 근거를 확인하기 전까지 `IMP-002`를 `unchanged`에 유지하며, 어떤 영향도 두 번 기재하지 않고 `new: none`을 표시합니다. 변경 이력의 약속은 불변 조건이지 임의로 만든 사용자 결정이 아닙니다. `DEC-001`은 명시적 선택 이후에만 생깁니다.

## 5. 연동

한 번의 실행은 하나의 정식 어댑터만 소유합니다. 각 흐름은 명확화 이후, 계획 이전에 영향도 정제를 삽입합니다.

| 모드 | 정식 순서 | 어댑터 |
| --- | --- | --- |
| `generic` | 구체적인 요구사항 + 저장소 범위 → 영향도 정제 → 사용자가 선택한 계획 방식 | [`integration-generic.md`](skills/requirements-impact-refiner/references/integration-generic.md) |
| `superpowers` | `brainstorming` 설계 승인 → 영향도 정제 → `writing-plans` | [`integration-superpowers.md`](skills/requirements-impact-refiner/references/integration-superpowers.md) |
| `claude-feature-dev` | Phase 3 명확화 → 영향도 정제 → Phase 4 아키텍처 설계 | [`integration-claude-feature-dev.md`](skills/requirements-impact-refiner/references/integration-claude-feature-dev.md) |
| `spec-kit` | `speckit.specify` 또는 `speckit.clarify` → 영향도 정제 → `speckit.plan` | [`integration-spec-kit.md`](skills/requirements-impact-refiner/references/integration-spec-kit.md) |
| BMAD | 명세 → 영향도 정제 → 아키텍처/준비도 | v1에서는 수동 지침만 제공, 정식 어댑터 없음 |
| GSD 및 기타 흐름 | 요구사항 명확화 → 영향도 정제 → 계획 | v1에서는 수동 지침만 제공, 정식 어댑터 없음 |

어댑터는 앞뒤 워크플로를 직접 실행하지 않습니다. 여러 오케스트레이터가 활성화되어 있으면 결합하지 않고 사용자에게 하나를 고르게 합니다.

## 6. 호환성

아래 주장은 보존된 평가 근거로 한정됩니다. “동작 평가”는 스킬과 참조 파일을 제공한 fresh-context 모델 실행을 뜻하며 외부 플러그인 로더나 오케스트레이터가 실제 실행되었다는 증명이 아닙니다.

| 클라이언트 또는 경로 | 버전/환경 | 상태 |
| --- | --- | --- |
| Codex fresh-context 동작 평가 도구 | `codex-cli 0.148.0-alpha.15`, 평가 모델 `gpt-5.6-luna`; hosted runtime version은 확인 불가 | tested: 핵심 최종 구성 24/25, 연동 최종 구성 30/30 |
| Codex 로컬 플러그인 manifest 검증 | 로컬 Python 환경 | `blocked`: `ModuleNotFoundError: yaml` |
| Claude Code 플러그인 로딩/검증 | Claude Code 버전 확인 불가 | `not tested`; `claude` 미설치로 검증/로딩 명령 `blocked` |
| 일반 `.agents/skills/` 탐색 | 클라이언트와 버전 미지정 | `not tested`; 탐색 보장 없이 관례만 문서화 |
| Superpowers, Claude Code `feature-dev`, Spec Kit 런타임 실행 | 외부 워크플로를 실행하지 않음 | `not tested`; Codex 평가 도구에서 어댑터 지시 동작만 평가 |
| BMAD와 GSD | v1 어댑터 없음 | `not tested`; 수동 지침만 제공 |

## 7. 비교와 비목표

Superpowers는 아이디어 구상, 계획, 실행, 디버깅, 리뷰의 오케스트레이터로 남습니다. Claude Code `feature-dev`는 단계형 기능 개발 흐름으로, GitHub Spec Kit은 명세와 계획 흐름으로 남습니다. Requirements Impact Refiner는 이들을 대체하거나 내장하지 않습니다. 각 흐름의 명확화와 계획 사이에서 저장소 근거 기반 영향도 목록과 반복적인 영향 축소를 제공합니다.

이 프로젝트는 광범위한 아이디어 발굴, 일반 PRD 작성, 아키텍처 설계, 작업 분해, 구현, 디버깅, 코드 리뷰를 제공하지 않습니다. MCP 서버나 전용 코드 그래프 엔진도 포함하지 않습니다. 다른 프레임워크를 자동 설치·호출·연결하지 않으며, 관련 프로젝트를 언급한다고 해서 의존성이나 코드 재사용을 뜻하지 않습니다.

## 8. 안전과 한계

저장소 접근, 검색, 테스트는 신뢰도를 높이지만 제공된 파일만으로 동작할 수도 있고 자동 접근이 보장되지는 않습니다. `verified`는 직접 검사한 근거를 뜻하며, 런타임 근거를 실제로 검사하지 않았다면 런타임 증명을 의미하지 않습니다. `inferred`와 `unknown`은 계속 표시해야 합니다. `AC-###`는 미래 목표이지 현재 동작이 통과했다는 근거가 아닙니다.

핵심 평가는 25/25가 아니라 **24/25**입니다. 알려진 단일 확률적 실패 `POS-payments-5`는 사용자가 재시도 정책을 고르기 전에 reconcile-before-retry 방식을 요구사항에 포함했습니다. 최종 체크리스트가 이 패턴을 다루지만 허용된 수정 라운드를 모두 사용했으므로 한계를 그대로 공개합니다. 별도의 워크플로 연동 최종 구성은 **30/30**입니다. 이 점수는 기록된 Codex 평가 도구의 결과이며 테스트하지 않은 클라이언트로 일반화하면 안 됩니다.

스킬은 검사 범위 밖의 영향을 놓칠 수 있습니다. 해결되지 않거나 `deferred`, `blocked`, `accepted`된 위험을 계획 과정에서도 유지하고, 중요한 동작은 적절한 사람의 검토와 테스트로 검증해야 합니다.

## 9. 보고서 스키마와 검증

[`impact-report-template.md`](skills/requirements-impact-refiner/assets/impact-report-template.md)에서 시작합니다. 최초/현재 요구사항, 현재 동작, 보존 불변 조건, 영향도 목록, 결정, 수정 이력, 인수 기준, 미해결 항목, 범위 한계, `Planning Handoff`를 포함합니다.

완성된 보고서는 표준 라이브러리 기반 검증기로 확인합니다.

```sh
python3 skills/requirements-impact-refiner/scripts/validate-impact-report.py path/to/report.md
```

검증기는 필수 섹션, 정의와 참조, 정확한 근거/상태 enum, `accepted`의 결정 연결, `resolved`의 근거, critical 영향의 `AC-###` 연결을 검사합니다. 인용한 저장소 사실이 참인지는 검증하지 않습니다. 선택적인 로컬 스킬/플러그인 플랫폼 검증기는 위에 설명한 환경 문제로 `blocked`되었으며 성공했다고 주장하지 않습니다.

## 10. 개발과 기여

저장소 루트에서 표준 라이브러리 테스트를 실행합니다.

```sh
python3 -m unittest discover -s tests -v
python3 -m unittest tests.test_documentation -v
```

RED/GREEN 평가 원칙, 다섯 번 반복하는 대조군, 검증 명령, 호환성 주장 규칙, 번역 정책은 [CONTRIBUTING.md](CONTRIBUTING.md)를 참고하세요. 영어 문서가 기준이지만 의미가 달라지는 README 수정은 `README.ko.md`와 `README.ja.md`도 함께 고치거나 번역 대기 상태를 명시해야 합니다. 이 프로젝트는 [MIT License](LICENSE)로 제공됩니다.
