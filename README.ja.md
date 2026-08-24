[English](README.md) | [한국어](README.ko.md) | 日本語

# Requirements Impact Refiner

Requirements Impact Refiner `0.4.0` は、具体的なソフトウェア変更を実装計画の前に、根拠と結び付いた影響台帳へ精緻化する **Public Preview** のリポジトリ認識型 Agent Skill です。[README.md](README.md) を意味上の正本とし、[README.ko.md](README.ko.md) と [README.ja.md](README.ja.md) は完全な翻訳です。

## 1. 課題

バイブコーディングによる変更は、最新の要求を満たす一方で、既存の認可境界、保存済みペイロード、モバイルクライアント、保持規則、リトライの意味論、可観測性をひそかに壊すことがあります。通常の要求明確化は何を作るかを説明しますが、変更をリポジトリの根拠に沿って追跡するとは限りません。

このスキルはその空白を埋めます。変更内容と調査範囲が具体的な場合にのみ開始し、現行動作を不変条件として記録し、信頼度付きで影響面を示します。ユーザーが影響を低減、保留、解決、または明示的に受容できるよう支援します。出力は報告書だけの `Planning Handoff` で終わり、製品の発想、実装計画の作成、コード編集、デバッグ、コードレビューは行いません。

## 2. 中核概念

正本のスキルは [`skills/requirements-impact-refiner/SKILL.md`](skills/requirements-impact-refiner/SKILL.md) です。すべての改訂を追跡できるよう、安定した ID を使用します。

| ID | 意味 |
| --- | --- |
| `RPT-###` | 連続するリビジョンで維持する報告書 ID |
| `REQ-###` | 元の要求または精緻化された要求 |
| `INV-###` | 保持が必要になり得る現行動作 |
| `IMP-###` | 影響を受ける動作、契約、データ経路、リスク |
| `DEC-###` | ユーザーまたは関係者が明示的に選んだ決定 |
| `AC-###` | 観測可能な受入基準または回帰基準 |

根拠レベルは正確に `verified`, `inferred`, `unknown` です。影響状態は正確に `detected`, `refining`, `mitigated`, `resolved`, `accepted`, `deferred`, `blocked`, `superseded` です。`reopened` は終端状態の影響が再び活動状態へ戻る Delta 遷移であり、台帳状態ではありません。各報告書は `RPT-###`, Revision, `Previous SHA-256`, phase を記録します。Revision 1 の基準報告は predecessor を `none`、全影響を `new` とし、後続リビジョンは ID を維持して直前ファイルの正確なバイト列と比較します。

## 3. クイックスタート

クライアントが対応している場合は、GitHub リポジトリをネイティブのマーケットプレイス機能でインストールします。マーケットプレイス名とプラグイン名はどちらも `requirements-impact-refiner` です。

Codex CLI では次を実行します。

```sh
codex plugin marketplace add sdj7072/requirements-impact-refiner --ref main
codex plugin add requirements-impact-refiner@requirements-impact-refiner
```

既存の Codex インストールをアップグレードするには、マーケットプレイスのスナップショットを更新し、プラグインを再インストールしてキャッシュ済みコピーを置き換えます。

```sh
codex plugin marketplace upgrade requirements-impact-refiner
codex plugin remove requirements-impact-refiner@requirements-impact-refiner
codex plugin add requirements-impact-refiner@requirements-impact-refiner
```

リポジトリの [`.agents/plugins/marketplace.json`](.agents/plugins/marketplace.json) はルートの [Codex plugin manifest](.codex-plugin/plugin.json) を参照し、その `skills` は単一の正本 `./skills/` ツリーを指します。[`.mcp.json`](.mcp.json) はローカルかつ標準ライブラリのみの `rir_begin` と `rir_finalize` も公開します。MCP はホストが tool を呼ぶ場合に構造化された強制を提供し、同梱 CLI は不正な finalize でユーザー出力を返さない hard-enforcement 境界です。controller に network client や third-party runtime dependency はなく、hook、app、agent も追加しません。

Claude Code では、Claude Code 内で次を実行します。

```text
/plugin marketplace add sdj7072/requirements-impact-refiner
/plugin install requirements-impact-refiner@requirements-impact-refiner
```

既存の Claude Code インストールをアップグレードするには、マーケットプレイスを更新し、インストール済みプラグインを更新して再読み込みします。

```text
/plugin marketplace update requirements-impact-refiner
/plugin update requirements-impact-refiner@requirements-impact-refiner
/reload-plugins
```

インストール結果で求められた場合は `/reload-plugins` を実行します。[`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json) はルートの [Claude plugin manifest](.claude-plugin/plugin.json) を配布します。ローカル開発用にはリポジトリをクローンし、ルートで次を実行します。

```sh
claude --plugin-dir .
```

その他の [Agent Skills 互換クライアント](https://agentskills.io/clients) では、リポジトリをクローンし、正本スキル全体をクライアントが指定するディレクトリへコピーします。`.agents/skills/` は便利なクロスクライアント既定値ですが、Agent Skills 仕様がインストール先を必須化しているわけではありません。

```sh
python3 scripts/install-agent-skill.py --target-dir ~/.agents/skills
```

インストーラーは既存のインストールを上書きしません。クライアント固有の選択肢として `~/.codex/skills` と `~/.claude/skills` も利用できますが、Codex と Claude Code では上記のマーケットプレイス方式の方が更新を管理しやすくなります。

プラグインが有効な場合、[`using-requirements-impact-refiner`](skills/using-requirements-impact-refiner/SKILL.md) がソフトウェア開発の会話を自動確認し、具体的な動作変更では計画前の適切な境界で中核スキルを呼び出します。専用の呼び出し文句は不要です。自動確認を止めるには、クライアントのプラグイン設定でこのプラグインを無効にします。

各報告書の先頭には、利用者向けの `Change Impact Summary` が表示されます。変更される機能、起こり得る問題、影響を受ける機能や利用者、発生条件、予防または確認方法を示します。既定値は `balanced` で、リポジトリルートの `.requirements-impact-refiner.json` で設定できます。

```json
{"audience":"balanced","delivery":"compact"}
```

audience は `simple`, `balanced`, `technical` を指定できます。delivery の既定値は compact です。完全な正規報告をインラインで返すには `delivery: full` を依頼するか `"delivery":"full"` を設定します。Compact モードは append-only JSON と Markdown を保存し、短い要約とパスだけを返します。保存できない場合は明示した `full-inline` fallback を使います。現在の依頼がリポジトリ設定より優先されます。これは Codex や Claude 専用画面ではなくクロスクライアントのスキル設定です。

既定経路は `rir_scan` 1回と最大 `180 words` の renderer-owned 応答です。high-risk でも detailed refinement を自動実行せず先に確認します。graph engine の target は `10s`、ceiling は `30s` ですが total model latency の保証ではありません。最初の representative canary は API → decoder → cache → migration path を17 msで発見しましたが model turn は `297.159`秒で strict one-call automation に失敗したため、v0.4 は `not verified` のままです。

互換性のため detailed graph refinement は `rir_begin → rir_trace_impact → inspect compact receipt → rir_finalize → return display_text` を維持します。promoted Fast Scan は trace を省略して receipt を再利用します。receipt は impact ごとの短い path と一つの coverage footer を加え、raw provider output は表示しません。全クライアントで同じ bounded local graph 設定を使います。

```json
{"impact_graph":{"enabled":true,"max_seconds":30,"target_seconds":10,"providers":["auto"],"install_policy":"never","deep":false}}
```

CLI fallback は同じ実行順序を使います。

```sh
python3 "$SKILL_DIR/scripts/rir-controller.py" begin --repo-root REPO --input REQUEST.json
python3 "$SKILL_DIR/scripts/rir-controller.py" trace --repo-root REPO --draft-id DRAFT_ID --input SEEDS.json
python3 "$SKILL_DIR/scripts/rir-controller.py" finalize --repo-root REPO --draft-id DRAFT_ID --graph-receipt-id RECEIPT_ID --input ANALYSIS.json
```

target は `10s`、hard ceiling は `30s` です。detect-only であり no automatic install or network です。optional local provider (`builtin`, `codegraph`, `scip`, `joern`, `ast-grep`) は各自の license に従い、missing、unsafe、unsupported、stale、failed、timed out になり得ます。builtin fallback の precision は限定的で、cache hit は一致する receipt だけを再利用し、partial cache は partial のままです。Deep は bounded discovery を広げるだけで complete を証明しません。unknown frontiers は残します。`full-inline` と CLI fallback もこの制限を維持します。表の compatibility は `not verified`/`blocked` のままで、transaction correctness と review は closed ではありません。Task 5 の parked exclusive-quarantine race は Task 7 が閉じる必要があります。

![Compact delivery flow](assets/compact-delivery-demo.svg)

完全な依頼、応答、成果物、full render の例は [compact delivery demo](docs/compact-delivery-demo.md) を参照してください。

読み込み後、変更とリポジトリ範囲を併記して依頼します。例: 「計画前に `displayName` API 名変更を API、iOS DTO、キャッシュ済みプロフィール経路に対して精緻化して」。複数のオーケストレーターがある場合は、正確に一つだけ選びます。

## 4. 実例

要求: 公開 API フィールド `displayName` を `name` に変更する。リポジトリ根拠では `ios/UserDTO.swift` が `displayName` をデコードし、キャッシュ済みプロフィール JSON がそれを保存し、公開 changelog は一バージョンの非推奨期間を約束しています。

| 成果物 | 例 |
| --- | --- |
| `REQ-001` | `displayName` を `name` に変更する。 |
| `INV-001` | 既存 iOS リリースは `displayName` をデコードする。`ios/UserDTO.swift` から得た `verified` 根拠。 |
| `IMP-001` | モバイルのデコードが失敗し得る。状態 `refining`、根拠 `verified`。 |
| `IMP-002` | 未調査の外部クライアントが `displayName` を利用し得る。状態 `detected`、根拠 `inferred`。 |
| Decision needed | 即時破壊、二フィールド互換、または別の明示的移行方針を選ぶ。 |
| `DEC-001` | ユーザーが公開済みの一非推奨バージョンの間、二フィールド互換を選ぶ。 |
| `REQ-002` | `name` を導入し、非推奨の `displayName` を一バージョン保持し、互換性基準を満たした後にだけ削除する。 |
| `AC-001` | そのバージョン中、現行 iOS デコーダーとキャッシュペイロード fixture が動作し続ける。 |

Revision 1 の基準報告では両方の影響を `new` とします。次の報告書で再計算した Delta は `IMP-001` を `mitigated`、外部利用者の根拠を調べるまで `IMP-002` を `unchanged` とし、同じ影響を二度記載しません。後の根拠が解決済み影響を無効にした場合、その影響は `reopened` です。changelog の約束は不変条件であり、捏造したユーザー決定ではありません。`DEC-001` は明示的な選択後にのみ存在します。

## 5. 統合

一回の実行を所有する正式アダプターは一つだけです。各フローは明確化の後、計画の前に影響精緻化を挿入します。

| モード | 正式な順序 | アダプター |
| --- | --- | --- |
| `generic` | 具体的要求 + リポジトリ範囲 → 影響精緻化 → ユーザーが選んだ計画方法 | [`integration-generic.md`](skills/requirements-impact-refiner/references/integration-generic.md) |
| `superpowers` | `brainstorming` 設計承認 → 影響精緻化 → `writing-plans` | [`integration-superpowers.md`](skills/requirements-impact-refiner/references/integration-superpowers.md) |
| `claude-feature-dev` | Phase 3 明確化 → 影響精緻化 → Phase 4 アーキテクチャ設計 | [`integration-claude-feature-dev.md`](skills/requirements-impact-refiner/references/integration-claude-feature-dev.md) |
| `spec-kit` | `speckit.specify` または `speckit.clarify` → 影響精緻化 → `speckit.plan` | [`integration-spec-kit.md`](skills/requirements-impact-refiner/references/integration-spec-kit.md) |
| BMAD | 仕様 → 影響精緻化 → アーキテクチャ/準備度 | v1 は手動ガイダンスのみ。正式アダプターなし |
| GSD および他のフロー | 要求明確化 → 影響精緻化 → 計画 | v1 は手動ガイダンスのみ。正式アダプターなし |

アダプターは前後のワークフローを起動しません。複数のオーケストレーターが有効なら、結合せずユーザーに一つを選んでもらいます。

## 6. 互換性

以下の主張は保存済み評価根拠に限定します。履歴上の Codex standalone 動作ハーネスはスキルと参照ファイルを渡した fresh-context 実行であり、外部プラグインローダーやオーケストレーターが実行された証明ではありません。これに対し、封印済み v0.3.1 Codex-with-Superpowers バッチは、正本リリースと機能 payload のバイトが一致する実際のインストール済みプラグインキャッシュで実行しました。製品、バージョン、状態の列は全翻訳で同一とし、根拠メモだけを翻訳しています。

| Environment | Version | Status | Evidence note |
| --- | --- | --- | --- |
| Codex standalone behavioral harness | `codex-cli 0.148.0-alpha.15`; `gpt-5.6-luna`; hosted runtime unavailable | `not verified` | 1ケース1回の厳格評価は **7/17** で失敗しました。陽性 0/8、陰性 3/5、統合 4/4 です。 |
| Codex with Superpowers | `codex-cli 0.148.0-alpha.21`; `gpt-5.6-sol`; `high`; RIR `0.3.1` | `not verified` | 封印済み v0.3.1 バッチでは、リトライなしの初回 85 件がすべてランタイム合格（85/85）でしたが、機械スコアは 84/85 です。`POS-cache` repetition 2 の不正な ledger/unknown `IMP-002` 失敗が唯一であり、検証ブロッカーが 1 件残ります。 |
| Codex skill quick validator | local system snapshot | `blocked` | PyYAML がありません。静的監査では、この検証器の許可キー一覧に Agent Skills の `compatibility` キーがないことも確認しました。実行合格とは主張しません。 |
| Codex plugin validator | local system snapshot | `blocked` | `ModuleNotFoundError: yaml` で実行が停止しました。manifest テストをこの検証器の合格として代用しません。 |
| Claude Code standalone | `2.1.228 (Claude Code)`; RIR `0.3.1` structural probe | `blocked` | 構造プローブのみであり、認証済み Claude 動作評価は実行していません。 |
| Claude Code with Superpowers | `2.1.228 (Claude Code)`; RIR `0.3.1` structural probe | `blocked` | 構造プローブのみであり、Claude 側 Superpowers の動作互換性は引き続き blocked です。 |
| Claude Code with `feature-dev` | `2.1.228 (Claude Code)`; RIR `0.3.1` structural probe | `blocked` | 構造プローブのみであり、`feature-dev` の動作互換性は引き続き blocked です。 |
| Claude Code with Spec Kit | `2.1.228 (Claude Code)`; RIR `0.3.1` structural probe | `blocked` | 構造プローブのみであり、Spec Kit の動作互換性は引き続き blocked です。 |
| Generic Agent Skills-compatible harness | client/version unavailable | `blocked` | 名前付きまたは設定済みの汎用ハーネス実行ファイルがありません。 |

履歴上の Codex standalone 結果 **7/17** はサポートの根拠ではありません。封印済み Codex-with-Superpowers v0.3.1 の証拠は、旧来の 1 回実行結果を置き換えます。選択された 85 件のランタイム出力はすべて合格しましたが、決定的な機械チェック 1 件が検証を妨げます。最終 report、controller、scorecard、manifest、raw transcript、引用がバインドされた adjudication は [`evals/results/installed-v0.3.1/report.md`](evals/results/installed-v0.3.1/report.md) と [`evals/results/installed-v0.3.1/adjudication.json`](evals/results/installed-v0.3.1/adjudication.json) に保存されています。

### 封印済み v0.3.1 評価証拠

以下の表は変更不能な最終評価証拠を記録します。この表によってリリース状態が verified に昇格することはありません。

| Evidence key | Sealed value |
| --- | --- |
| release | 0.3.1 |
| composition | Codex with Superpowers |
| Codex client | codex-cli 0.148.0-alpha.21 |
| RIR plugin | requirements-impact-refiner@requirements-impact-refiner-v031-eval |
| model / reasoning | gpt-5.6-sol / high |
| runtime outcomes | 85/85 pass; 85 attempt 1 selections; no retries |
| mechanical score | 84/85; one failure: POS-cache repetition 2 |
| human adjudication | 400/400 passed; every adjudication quote is bound to its selected final output |
| release status | not verified; one mechanical verification blocker |
| Claude probe | 2.1.228 (Claude Code) / RIR 0.3.1; structural-only, behavioral compatibility remains blocked |

正確なプラグイン識別子は `requirements-impact-refiner@requirements-impact-refiner-v031-eval` です。これは isolated local evaluation-only marketplace の別名であり、not a public install ID or support claim です。最上位 marketplace 名は意図的に異なるため wrapper ファイルだけを除外し、すべての機能 payload コンポーネントのバイトは封印済み [installed payload](evals/results/installed-v0.3.1/installed-payload.json) インベントリで一致しています。v0.3.1 manifest digest は `8e195a0cd5584dd56980917ae97ca284e8ef1653570742bdb1838079ec99d88d` であり、raw transcript のインベントリはバイト保存と秘密情報スキャンを維持します。唯一の機械的失敗は `POS-cache` repetition 2 の不正な Impact Ledger 行と unknown `IMP-002` 参照を正確に記録します。400 件の人手 adjudication はすべて合格し、各引用が選択された最終出力の部分文字列であることを確認しています。Claude の証拠は structural-only であり、blocked の動作互換性状態を変更しません。

## 7. 比較と非目標

Superpowers はブレインストーミング、計画、実行、デバッグ、レビューのオーケストレーターであり続けます。Claude Code `feature-dev` は段階的な機能開発フロー、GitHub Spec Kit は仕様・計画フローであり続けます。Requirements Impact Refiner はそれらを置き換えたり内包したりしません。それぞれの明確化と計画の間に、リポジトリ根拠付き影響台帳と反復的な影響低減を提供します。

本プロジェクトは広範なアイデア出し、一般的な PRD 作成、アーキテクチャ設計、タスク分解、実装、デバッグ、コードレビューを提供しません。限定的なローカル MCP server と CLI は影響レポート生成だけを制御し、専用 code-graph engine は同梱しません。MCP host は tool call を省略できるため、CLI finalize 経路だけが hard enforcement です。他フレームワークを自動で導入、起動、連結せず、関連プロジェクトへの言及は依存関係やコード再利用を意味しません。

## 8. 安全性と制限

リポジトリへのアクセス、検索、テストは信頼度を高めますが、提供ファイルだけで動作する場合もあり、自動アクセスは保証されません。`verified` は直接調べた裏付けを表し、ランタイム根拠を実際に調べていない限りランタイム証明ではありません。`inferred` と `unknown` は表示し続けます。`AC-###` は将来の目標であり、現行動作が合格した証拠ではありません。

中核評価は 25/25 ではなく **24/25** です。既知の単一確率的失敗 `POS-payments-5` は、ユーザーがリトライ方針を選ぶ前に reconcile-before-retry の仕組みを要求へ埋め込みました。最終チェックリストはこのパターンに対処しますが、許可された修正ラウンドを使い切ったため制限を開示しています。別のワークフロー統合最終構成は **30/30** です。これらは記録済み Codex ハーネスの結果であり、未試験クライアントへ一般化してはいけません。

より広いリリース記録はクライアントサポートを推論しません。Codex standalone は厳格評価 **7/17** に失敗しました。Codex with Superpowers は全 5 回反復、85 final の v0.3.1 バッチを完了しましたが、85/85 のランタイムと 400/400 の adjudication 件数にもかかわらず、`POS-cache` repetition 2 の機械的失敗がリリースブロッカーであるため、引き続き `not verified` です。

スキルは調査範囲外の影響を見逃す可能性があります。未解決、`deferred`、`blocked`、`accepted` のリスクを計画中も可視化し、重要な動作は適切な人手レビューとテストで検証してください。

v0.2 は履歴形式です。`0.3.0` への移行は manual migration です。最初に変換した成果物を新しい `RPT-###` の Revision 1 とし、`Previous SHA-256` は `none`、維持する全影響は `new` とします。v0.2 の predecessor digest を捏造してはいけません。以降のリビジョンでは ID を維持し、直前ファイルの正確なバイト列を使います。

## 9. 報告書スキーマと検証

[`テンプレート選択`](skills/requirements-impact-refiner/assets/impact-report-template.md) から始めます。バージョン `0.3.0` は `pre-decision` と `post-decision` の報告を分離し、選択前の決定記録を禁止し、完全で重複のない Impact Delta と報告書 lineage を検証します。

完成した報告書は標準ライブラリだけの検証器で確認します。

```sh
python3 skills/requirements-impact-refiner/scripts/validate-impact-report.py --require-summary path/to/report.md
```

後続リビジョンは正確な predecessor とともに検証し、両ファイルを変更せず計算済み Delta を表示できます。

```sh
python3 skills/requirements-impact-refiner/scripts/validate-impact-report.py --previous previous.md current.md
python3 skills/requirements-impact-refiner/scripts/validate-impact-report.py --previous previous.md --print-expected-delta current.md
```

検証器は必須セクション、定義と参照、正確な根拠/状態 enum、`accepted` の決定リンク、`resolved` の根拠、critical 影響の `AC-###` リンク、連続リビジョン番号、安定した報告書/影響 ID、正確な predecessor digest、`reopened` を含む決定的 Delta 遷移を確認します。`--require-summary` を付けると、各 impact に要約行が一つだけあること、および severity と status が台帳と一致することも検査します。0.3.2 より前の報告書は、このフラグなしで引き続き検証できます。引用したリポジトリ事実の真偽は検証せず、predecessor を自動検索もしません。任意のローカル skill/plugin platform validator は前述の環境問題で `blocked` され、成功は主張しません。

## 10. 開発とコントリビューション

リポジトリルートから標準ライブラリのテストを実行します。

```sh
python3 -m unittest discover -s tests -v
python3 -m unittest tests.test_documentation -v
```

RED/GREEN 評価規律、五回反復の対照、検証コマンド、互換性主張の規則、翻訳方針は [CONTRIBUTING.md](CONTRIBUTING.md) を参照してください。英語文書が正本ですが、意味を変える README 更新では `README.ko.md` と `README.ja.md` も同時に更新するか、翻訳待ちを明記します。本プロジェクトは [MIT License](LICENSE) で提供されます。
