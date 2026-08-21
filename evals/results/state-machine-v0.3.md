# State-Machine Behavioral Evaluation — v0.3.0

Date: 2026-08-21

Scope: report lineage, predecessor-aware Delta transitions, and evidence-gated resolution. Fresh independent Codex subagents received each scenario and the routed skill files. The runtime did not expose a model identifier. These are behavioral observations, not client-loader or cross-client support claims.

## RED — v0.2 guidance

Each case had one repetition before the v0.3 instruction change.

- `LINEAGE-stable-blocked` placed `blocked`→`blocked` under `blocked`, not `unchanged`.
- `LINEAGE-reopened` placed `resolved`→`refining` under `unchanged`, not `reopened`.
- `LINEAGE-no-false-resolution` correctly rejected a proposed resolution with no supporting evidence.

Result: 1/3 satisfied the new transition/rejection contract.

## GREEN — v0.3.0 guidance

| Case | Client/model | Repetitions | Report ID preserved | Revision/hash valid | Expected Delta | Unsupported claim rejected | Result |
| --- | --- | ---: | --- | --- | --- | --- | --- |
| `LINEAGE-stable-blocked` | Codex subagent / inherited model not exposed | 1 | not verified — predecessor artifact absent | not verified — exact predecessor bytes absent | `unchanged` — pass | N/A | behavioral pass; lineage fields not exercised |
| `LINEAGE-reopened` | Codex subagent / inherited model not exposed | 1 | not verified — predecessor artifact absent | not verified — exact predecessor bytes absent | `reopened` — pass | N/A | behavioral pass; lineage fields not exercised |
| `LINEAGE-no-false-resolution` | Codex subagent / inherited model not exposed | 1 | not verified — first v0.3 baseline | not verified — predecessor artifact absent | `new` baseline — pass | yes — unsupported `resolved` rejected | behavioral pass; lineage fields not exercised |

Result: 3/3 behavioral cases passed with one repetition per case. All agents disclosed missing predecessor bytes instead of fabricating IDs, revisions, or hashes. Because the prompts supplied state summaries rather than exact report artifacts, this evidence does not verify byte-level lineage preservation.

## Exact post-change prompts and decisive output excerpts

The initial stable-blocked dispatcher prompt was not preserved. The other two initial prompts and all three full report bodies exist only in the originating Codex task, not as repository raw evidence. The following post-change prompts are the exact dispatched strings retained by the coordinator:

### `LINEAGE-stable-blocked`

```text
Now perform the post-change pressure test. Read the UPDATED core SKILL.md and direct evidence/refinement/template resources in the v03 worktree; still do not read design/plan/tests. Re-run the same blocked→blocked scenario. Return the canonical report plus one sentence stating the Delta category and lineage treatment. No edits.
```

Exact decisive output excerpt:

```text
`IMP-001` belongs under `unchanged` because `blocked`→`blocked` is a stable transition; lineage is preserved only where supplied, while unavailable predecessor IDs, revision, and exact-byte SHA-256 are disclosed rather than invented.
```

### `LINEAGE-reopened`

```text
Now perform the post-change pressure test. Read the UPDATED core SKILL.md and direct evidence/refinement/template resources in the v03 worktree; still do not read design/plan/tests. Re-run the same resolved→refining scenario. Return the canonical report plus one sentence stating the Delta category and lineage treatment. No edits.
```

Exact decisive output excerpt:

```text
Delta treatment is `reopened` because `resolved`→`refining` is terminal-to-active; lineage is preserved conceptually but no report ID, revision, or SHA-256 is fabricated without the exact predecessor.
```

### `LINEAGE-no-false-resolution`

```text
Now perform the post-change pressure test. Read the UPDATED core SKILL.md and direct evidence/refinement/template resources in the v03 worktree; still do not read design/plan/tests. Re-run the same refining→resolved-without-evidence scenario. Return the canonical report plus one sentence stating whether unsupported resolution is rejected and how lineage is treated. No edits.
```

Exact decisive output excerpt:

```text
Unsupported resolution is rejected; because no earlier v0.3 artifact exists, lineage starts honestly at `RPT-001` Revision 1 with predecessor `none`, and `IMP-001` is `new` in the report Delta while remaining `refining` in the ledger.
```

The RED adjudication used the exact prior Delta cells `| blocked | IMP-001 |` and `| unchanged | IMP-001 |` for the first two cases; the third prior run explicitly retained `IMP-001` as `refining`. Because the complete initial prompts and report bodies were not all preserved, this ledger supports a bounded one-repetition behavior observation, not a reproducible raw-corpus claim.

## Deterministic coverage and limits

The automated lineage suite supplies exact predecessor bytes and verifies stable Report ID, consecutive revision, lowercase exact SHA-256, retained impact IDs, transition precedence, authored-versus-calculated Delta, CLI exit codes, and source-file immutability. The skill-focused checkpoint passed 104/104 tests; after review fixes and release-evidence assertions, the full suite passed 111/111.

Both report modules compile when `PYTHONPYCACHEPREFIX` points to `/tmp`. The Codex skill quick validator remains `blocked`: its environment lacks PyYAML. Claude Code and generic external client execution were not repeated, so their existing `blocked` or `not verified` compatibility statuses remain unchanged.

There are no raw transcripts committed for these six behavioral runs. The results above are an adjudicated summary; no new `.gitattributes` raw-evidence exception or checksum manifest is claimed.
