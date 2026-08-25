# Report-flow verification batch — sealed at repetition 1

Ran the eight fixture-anchored positives once against the installed
plugin with the strengthened bootstrap trigger, then **stopped
deliberately**: a decisive probe proved the report flow itself cannot be
exercised from this session, so further repetitions would measure the
same ask-flow instructions again.

## The measurement boundary, established by evidence

A sentinel subagent was asked to quote its own skill listing verbatim.
It returned the **0.5.0** description — the pre-change wording — while
the marketplace and installed caches already carried the new one. After
publishing 0.6.0 and installing it (`0.5.0 -> 0.6.0` confirmed, new
`hide display_text` instruction present in the 0.6.0 cache), a fresh
probe still executed the ask flow. Subagents therefore resolve skills
from the snapshot taken at session start; a client restart is required.

Version 0.6.0 exists partly because of this finding: plugin installs
snapshot by version string, so the flow change could not reach any
client while the manifest still said 0.5.0.

## What this batch does measure: the engagement cliff

The trigger wording under test here is 0.5.0's, but the request phrasing
and fixtures match the sealed ask-flow batch, so the engagement rate is
directly comparable.

| Metric | Sealed ask-flow batch | This batch |
| --- | --- | --- |
| Positives engaging the skill | 3/8 | **8/8** |
| Positives modifying the repository | 5/8 | **0/8** |
| Fixture files altered (sha256-verified) | not tracked | **0 of 46** |

Every run performed refinement first, returned the scan verbatim, and
stopped at the refinement question without touching a file. Fixture
integrity was verified by hashing all 46 planted files before the batch
and re-hashing after: zero modifications, zero deletions.

The controlled difference is the prompt's explicit
`Run requirements impact refinement before anything else.` line. That
isolates the cause: the cliff was never a capability failure — the
agents can and do refine — it was a **salience** failure, and one
sentence of framing closes it. This is the empirical case for the
strengthened trigger (which encodes that framing permanently) and the
report flow (which removes the ask checkpoint the agents stopped at).

## Caveat this batch does not resolve

Because every prompt carried the explicit instruction, this batch cannot
distinguish "the new trigger works" from "explicit instruction works."
A restarted session running these same cases *without* the instruction
line is the test that separates them, and it is the next batch to run.

## Artifacts

`raw/BATCH-report-flow-rep1/<case>.md` — verbatim final outputs for all
eight runs. Scratchpad contention recurred (parallel agents overwriting
each other's scan-input files); every affected agent detected the
substitution, refused the foreign request, and re-ran from a fresh file.
