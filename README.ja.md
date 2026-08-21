[English](README.md) | [한국어](README.ko.md) | 日本語

# Requirements Impact Refiner

Requirements Impact Refiner `0.3.0` は、具体的なソフトウェア変更を実装計画の前に、根拠と結び付いた影響台帳へ精緻化するリポジトリ認識型 Agent Skill です。[README.md](README.md) を意味上の正本とし、[README.ko.md](README.ko.md) と [README.ja.md](README.ja.md) は完全な翻訳です。

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

リポジトリの [`.agents/plugins/marketplace.json`](.agents/plugins/marketplace.json) はルートの [Codex plugin manifest](.codex-plugin/plugin.json) を参照し、その `skills` は単一の正本 `./skills/` ツリーを指します。MCP server、hook、app、agent、dependency は追加しません。

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

以下の主張は保存済み評価根拠に限定します。「動作評価」はスキルと参照ファイルを渡した fresh-context モデル実行であり、外部プラグインローダーやオーケストレーターが実行された証明ではありません。製品、バージョン、状態の列は全翻訳で同一とし、根拠メモだけを翻訳しています。

| Environment | Version | Status | Evidence note |
| --- | --- | --- | --- |
| Codex standalone behavioral harness | `codex-cli 0.148.0-alpha.15`; `gpt-5.6-luna`; hosted runtime unavailable | `not verified` | 1ケース1回の厳格評価は **7/17** で失敗しました。陽性 0/8、陰性 3/5、統合 4/4 です。 |
| Codex with Superpowers | executed client/model/version not recorded in selected transcripts | `not verified` | 1ケース1回の厳格評価は **10/17** で失敗しました。陽性は1件合格、7件部分合格で、陰性 5/5 と統合 4/4 は合格しました。 |
| Codex skill quick validator | local system snapshot | `blocked` | PyYAML がありません。静的監査では、この検証器の許可キー一覧に Agent Skills の `compatibility` キーがないことも確認しました。実行合格とは主張しません。 |
| Codex plugin validator | local system snapshot | `blocked` | `ModuleNotFoundError: yaml` で実行が停止しました。manifest テストをこの検証器の合格として代用しません。 |
| Claude Code standalone | version unavailable | `blocked` | `claude` 実行ファイルがありません。 |
| Claude Code with Superpowers | version unavailable | `blocked` | `claude` 実行ファイルと Claude 側 Superpowers ランタイムがありません。 |
| Claude Code with `feature-dev` | version unavailable | `blocked` | `claude` 実行ファイルと `feature-dev` ランタイムがありません。 |
| Claude Code with Spec Kit | version unavailable | `blocked` | `claude` 実行ファイルと Spec Kit ランタイムがありません。 |
| Generic Agent Skills-compatible harness | client/version unavailable | `blocked` | 名前付きまたは設定済みの汎用ハーネス実行ファイルがありません。 |

両方の Codex 評価で陽性の表層項目 **24/24** を検出し、統合所有境界 **4/4** を維持しました。これは観察された動作であり、互換性やサポートではありません。全17ケースを5回ずつ再実行していません。Task 7 ではスキルまたはアダプター文言を変更しておらず、1回実行のコーパスがすでに厳格なサポート基準に失敗したためです。全 transcript、再実行、scorecard、checksum は [`evals/results/with-skill.md`](evals/results/with-skill.md) にあります。

## 7. 比較と非目標

Superpowers はブレインストーミング、計画、実行、デバッグ、レビューのオーケストレーターであり続けます。Claude Code `feature-dev` は段階的な機能開発フロー、GitHub Spec Kit は仕様・計画フローであり続けます。Requirements Impact Refiner はそれらを置き換えたり内包したりしません。それぞれの明確化と計画の間に、リポジトリ根拠付き影響台帳と反復的な影響低減を提供します。

本プロジェクトは広範なアイデア出し、一般的な PRD 作成、アーキテクチャ設計、タスク分解、実装、デバッグ、コードレビューを提供しません。MCP server や専用 code-graph engine も同梱しません。他フレームワークを自動で導入、起動、連結せず、関連プロジェクトへの言及は依存関係やコード再利用を意味しません。

## 8. 安全性と制限

リポジトリへのアクセス、検索、テストは信頼度を高めますが、提供ファイルだけで動作する場合もあり、自動アクセスは保証されません。`verified` は直接調べた裏付けを表し、ランタイム根拠を実際に調べていない限りランタイム証明ではありません。`inferred` と `unknown` は表示し続けます。`AC-###` は将来の目標であり、現行動作が合格した証拠ではありません。

中核評価は 25/25 ではなく **24/25** です。既知の単一確率的失敗 `POS-payments-5` は、ユーザーがリトライ方針を選ぶ前に reconcile-before-retry の仕組みを要求へ埋め込みました。最終チェックリストはこのパターンに対処しますが、許可された修正ラウンドを使い切ったため制限を開示しています。別のワークフロー統合最終構成は **30/30** です。これらは記録済み Codex ハーネスの結果であり、未試験クライアントへ一般化してはいけません。

より広い Task 7 リリース監査は、クライアント対応を推論できない結果です。Codex standalone は厳格評価 **7/17**、Codex with Superpowers は **10/17** で失敗しました。各ケースの採用結果は1件だけで、runbook の5回サポート基準にも届きません。したがって、このリリース根拠では両環境とも検証済みまたはサポート済みではありません。

スキルは調査範囲外の影響を見逃す可能性があります。未解決、`deferred`、`blocked`、`accepted` のリスクを計画中も可視化し、重要な動作は適切な人手レビューとテストで検証してください。

v0.2 は履歴形式です。`0.3.0` への移行は manual migration です。最初に変換した成果物を新しい `RPT-###` の Revision 1 とし、`Previous SHA-256` は `none`、維持する全影響は `new` とします。v0.2 の predecessor digest を捏造してはいけません。以降のリビジョンでは ID を維持し、直前ファイルの正確なバイト列を使います。

## 9. 報告書スキーマと検証

[`テンプレート選択`](skills/requirements-impact-refiner/assets/impact-report-template.md) から始めます。バージョン `0.3.0` は `pre-decision` と `post-decision` の報告を分離し、選択前の決定記録を禁止し、完全で重複のない Impact Delta と報告書 lineage を検証します。

完成した報告書は標準ライブラリだけの検証器で確認します。

```sh
python3 skills/requirements-impact-refiner/scripts/validate-impact-report.py path/to/report.md
```

後続リビジョンは正確な predecessor とともに検証し、両ファイルを変更せず計算済み Delta を表示できます。

```sh
python3 skills/requirements-impact-refiner/scripts/validate-impact-report.py --previous previous.md current.md
python3 skills/requirements-impact-refiner/scripts/validate-impact-report.py --previous previous.md --print-expected-delta current.md
```

検証器は必須セクション、定義と参照、正確な根拠/状態 enum、`accepted` の決定リンク、`resolved` の根拠、critical 影響の `AC-###` リンク、連続リビジョン番号、安定した報告書/影響 ID、正確な predecessor digest、`reopened` を含む決定的 Delta 遷移を確認します。引用したリポジトリ事実の真偽は検証せず、predecessor を自動検索もしません。任意のローカル skill/plugin platform validator は前述の環境問題で `blocked` され、成功は主張しません。

## 10. 開発とコントリビューション

リポジトリルートから標準ライブラリのテストを実行します。

```sh
python3 -m unittest discover -s tests -v
python3 -m unittest tests.test_documentation -v
```

RED/GREEN 評価規律、五回反復の対照、検証コマンド、互換性主張の規則、翻訳方針は [CONTRIBUTING.md](CONTRIBUTING.md) を参照してください。英語文書が正本ですが、意味を変える README 更新では `README.ko.md` と `README.ja.md` も同時に更新するか、翻訳待ちを明記します。本プロジェクトは [MIT License](LICENSE) で提供されます。
