import importlib.util
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    ROOT
    / "skills"
    / "requirements-impact-refiner"
    / "scripts"
    / "validate-impact-report.py"
)
SPEC = importlib.util.spec_from_file_location("validate_impact_report", SCRIPT_PATH)
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


EXPECTED_ERRORS = {
    "duplicate": "duplicate identifier IMP-001",
    "dangling": "unknown reference DEC-999",
    "malformed_id": "invalid identifier IMP-1",
    "state": "invalid impact state ignored",
    "evidence_level": "invalid evidence level certain",
    "missing_requirement": "impact IMP-001 requires REQ reference",
    "resolved_without_evidence": "resolved impact IMP-001 requires evidence",
    "accepted_without_decision": "accepted impact IMP-001 requires DEC reference",
    "critical_without_ac": "critical impact IMP-001 requires AC reference",
    "missing_limitations": "missing section: Analysis Scope and Limitations",
    "unresolved_accepted": "invalid impact state accepted",
}


VALID_REPORT = """# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| RPT-001 | 1 | none | post-decision |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| REQ-001 | Preserve existing exports while adding sharing. | Product request |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| REQ-001 | Add sharing without changing exports. | DEC-001 | — |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| INV-001 | Existing exports remain private. | verified | tests/test_exports.py |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| INV-001 | REQ-001 | IMP-001 | tests/test_exports.py |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| IMP-001 | REQ-001 | interfaces | critical | accepted | verified | tests/test_exports.py | INV-001 | DEC-001 | AC-001 |

## Decisions and Accepted Risks

| Decision ID | Choice | Requirement revision | Accepted impacts | Rationale |
| --- | --- | --- | --- | --- |
| DEC-001 | Preserve private export default. | REQ-001 | IMP-001 | Avoid regression. |

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
| new | IMP-001 |

## Requirement Revision History

| Requirement ID | Revision | Decision | Superseded impacts | Change summary |
| --- | --- | --- | --- | --- |
| REQ-001 | Add sharing with private defaults. | DEC-001 | — | Narrowed scope. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| AC-001 | REQ-001 | IMP-001 | INV-001 | Existing exports stay private. | tests/test_exports.py |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| Export and sharing paths only. | tests/test_exports.py | Other paths remain unknown. |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| REQ-001 | INV-001, IMP-001, DEC-001 | Accepted IMP-001 | AC-001 | Existing planning workflow |
"""


PRE_DECISION_REPORT = """# Requirements Impact Report

## Report State

| Report ID | Revision | Previous SHA-256 | Phase |
| --- | --- | --- | --- |
| RPT-001 | 1 | none | pre-decision |

## Original Requirement

| Requirement ID | Original request | Source |
| --- | --- | --- |
| REQ-001 | Add public sharing without changing authenticated exports. | Product request |

## Current Refined Requirement

| Requirement ID | Revision | Refined by decision | Supersedes |
| --- | --- | --- | --- |
| REQ-001 | Preserve authenticated exports while selecting sharing mechanics. | — | — |

## Current Behavior

| Invariant ID | Current behavior | Evidence level | Evidence |
| --- | --- | --- | --- |
| INV-001 | Existing export URLs require authentication. | verified | tests/test_exports.py |

## Preserved Invariants

| Invariant ID | Must preserve for requirement | Affected impacts | Evidence |
| --- | --- | --- | --- |
| INV-001 | REQ-001 | IMP-001 | tests/test_exports.py |

## Impact Ledger

| ID | Requirement | Category | Severity | State | Evidence Level | Evidence | Invariants | Decision | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| IMP-001 | REQ-001 | interfaces | critical | refining | verified | tests/test_exports.py | INV-001 | — | AC-001 |

## Decision Needed

| Question | Option | Impact IDs | Trade-off |
| --- | --- | --- | --- |
| Which sharing mechanism should be used? | Expiring signed URLs | IMP-001 | Simple expiry, limited revocation. |
| Which sharing mechanism should be used? | Revocable opaque links | IMP-001 | Explicit revocation, more stored state. |

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
| new | IMP-001 |

## Requirement Revision History

| Requirement ID | Revision | Decision | Superseded impacts | Change summary |
| --- | --- | --- | --- | --- |
| REQ-001 | Preserve authenticated exports while selecting sharing mechanics. | — | — | Initial refinement. |

## Acceptance and Regression Criteria

| Criterion ID | Requirement | Impact | Invariant | Observable criterion | Evidence/test |
| --- | --- | --- | --- | --- | --- |
| AC-001 | REQ-001 | IMP-001 | INV-001 | Existing authenticated exports remain unchanged. | Future regression test required. |

## Unresolved, Deferred, and Blocked Items

| Impact ID | State | Information gap or rationale | Linked decision | Next owner |
| --- | --- | --- | --- | --- |

## Analysis Scope and Limitations

| Scope or limitation | Inspected evidence | Consequence for confidence |
| --- | --- | --- |
| Export paths only. | tests/test_exports.py | Sharing implementation remains unknown. |

## Planning Handoff

| Refined requirement | Report IDs | Remaining risks | Acceptance criteria | Selected planning workflow |
| --- | --- | --- | --- | --- |
| Not ready until the pending decision is selected. | REQ-001, INV-001, IMP-001 | Pending sharing mechanism. | AC-001 | Not ready |
"""


POST_DECISION_REPORT = PRE_DECISION_REPORT.replace(
    "| pre-decision |", "| post-decision |", 1
).replace(
    "## Decision Needed\n\n"
    "| Question | Option | Impact IDs | Trade-off |\n"
    "| --- | --- | --- | --- |\n"
    "| Which sharing mechanism should be used? | Expiring signed URLs | IMP-001 | Simple expiry, limited revocation. |\n"
    "| Which sharing mechanism should be used? | Revocable opaque links | IMP-001 | Explicit revocation, more stored state. |",
    "## Decisions and Accepted Risks\n\n"
    "| Decision ID | Choice | Requirement revision | Accepted impacts | Rationale |\n"
    "| --- | --- | --- | --- | --- |\n"
    "| DEC-001 | Use revocable opaque links. | REQ-001 | IMP-001 | Explicit revocation is required. |",
    1,
).replace(
    "| REQ-001 | Preserve authenticated exports while selecting sharing mechanics. | — | — |",
    "| REQ-001 | Add revocable opaque sharing links and preserve authenticated exports. | DEC-001 | — |",
    1,
).replace(
    "| critical | refining | verified | tests/test_exports.py | INV-001 | — | AC-001 |",
    "| critical | accepted | verified | tests/test_exports.py | INV-001 | DEC-001 | AC-001 |",
    1,
).replace(
    "| REQ-001 | Preserve authenticated exports while selecting sharing mechanics. | — | — | Initial refinement. |",
    "| REQ-001 | Add revocable opaque sharing links and preserve authenticated exports. | DEC-001 | — | Applied selected mechanism. |",
    1,
).replace(
    "| Not ready until the pending decision is selected. | REQ-001, INV-001, IMP-001 | Pending sharing mechanism. | AC-001 | Not ready |",
    "| REQ-001 | INV-001, IMP-001, DEC-001 | Accepted IMP-001 | AC-001 | Existing planning workflow |",
    1,
)


class ValidateImpactReportTest(unittest.TestCase):
    def test_friendly_summary_is_required_only_when_requested(self):
        self.assertEqual(VALIDATOR.validate_report(POST_DECISION_REPORT), [])

        errors = VALIDATOR.validate_report(
            POST_DECISION_REPORT, require_summary=True
        )

        self.assertIn("missing section: Change Impact Summary", errors)

    def test_friendly_summary_covers_each_impact_and_matches_ledger(self):
        summary = """## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| IMP-001 | Public sharing | Existing private exports could become public. | People using private exports | Opening a sharing link | critical | Keep private-by-default regression coverage. | accepted |

"""
        report = POST_DECISION_REPORT.replace(
            "## Original Requirement\n", summary + "## Original Requirement\n", 1
        )

        self.assertEqual(
            VALIDATOR.validate_report(report, require_summary=True), []
        )

        wrong = report.replace(
            "| critical | Keep private-by-default", "| low | Keep private-by-default", 1
        )
        self.assertIn(
            "impact summary IMP-001 severity low disagrees with ledger critical",
            VALIDATOR.validate_report(wrong, require_summary=True),
        )

    def test_friendly_summary_rejects_unknown_duplicate_and_missing_impacts(self):
        summary = """## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| IMP-999 | Public sharing | Existing private exports could become public. | People using private exports | Opening a sharing link | critical | Keep private-by-default regression coverage. | accepted |
| IMP-999 | Public sharing | Existing private exports could become public. | People using private exports | Opening a sharing link | critical | Keep private-by-default regression coverage. | accepted |

"""
        report = POST_DECISION_REPORT.replace(
            "## Original Requirement\n", summary + "## Original Requirement\n", 1
        )

        errors = VALIDATOR.validate_report(report, require_summary=True)

        self.assertIn("impact summary references unknown impact IMP-999", errors)
        self.assertIn("impact summary lists IMP-999 more than once", errors)
        self.assertIn("impact summary missing known impact IMP-001", errors)

    def test_friendly_summary_requires_plain_language_fields(self):
        summary = """## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| IMP-001 | Public sharing |  | People using private exports | Opening a sharing link | critical | Keep private-by-default regression coverage. | accepted |

"""
        report = POST_DECISION_REPORT.replace(
            "## Original Requirement\n", summary + "## Original Requirement\n", 1
        )

        self.assertIn(
            "impact summary IMP-001 requires Possible issue",
            VALIDATOR.validate_report(report, require_summary=True),
        )

    def test_friendly_summary_rejects_duplicate_section_bypass(self):
        wrong = """## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| IMP-001 | Public sharing | Private exports become public. | Export users | Sharing | low | None. | resolved |

"""
        correct = """## Change Impact Summary

| Impact ID | Changed feature | Possible issue | Affected feature or user | Trigger | Severity | Prevention or check | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| IMP-001 | Public sharing | Private exports become public. | Export users | Sharing | critical | Preserve private defaults. | accepted |

"""
        report = POST_DECISION_REPORT.replace(
            "## Original Requirement\n",
            wrong + correct + "## Original Requirement\n",
            1,
        )

        self.assertIn(
            "duplicate section: Change Impact Summary",
            VALIDATOR.validate_report(report, require_summary=True),
        )

    def test_parses_v03_report_metadata(self):
        report, errors = VALIDATOR.parse_report(POST_DECISION_REPORT)

        self.assertEqual(errors, [])
        self.assertEqual(report.metadata.report_id, "RPT-001")
        self.assertEqual(report.metadata.revision, 1)
        self.assertEqual(report.metadata.previous_sha256, "none")
        self.assertEqual(report.metadata.phase, "post-decision")

    def test_revision_one_requires_none_predecessor_and_all_impacts_new(self):
        wrong_hash = POST_DECISION_REPORT.replace(
            "| RPT-001 | 1 | none |",
            f"| RPT-001 | 1 | {'a' * 64} |",
            1,
        )
        wrong_delta = POST_DECISION_REPORT.replace(
            "| unchanged | none |", "| unchanged | IMP-001 |", 1
        ).replace("| new | IMP-001 |", "| new | none |", 1)

        self.assertIn(
            "revision 1 requires Previous SHA-256 none",
            VALIDATOR.validate_report(wrong_hash),
        )
        self.assertIn(
            "revision 1 impact IMP-001 must be new",
            VALIDATOR.validate_report(wrong_delta),
        )

    def test_accepts_both_explicit_report_phases(self):
        self.assertEqual(VALIDATOR.validate_report(PRE_DECISION_REPORT), [])
        self.assertEqual(VALIDATOR.validate_report(POST_DECISION_REPORT), [])

    def test_rejects_missing_or_invalid_report_phase(self):
        missing = POST_DECISION_REPORT.replace("## Report State", "## Removed State", 1)
        invalid = POST_DECISION_REPORT.replace("| post-decision |", "| drafting |", 1)

        self.assertIn("missing section: Report State", VALIDATOR.validate_report(missing))
        self.assertIn("invalid report phase drafting", VALIDATOR.validate_report(invalid))

    def test_pre_decision_forbids_recorded_decisions_and_concrete_decision_ids(self):
        with_section = PRE_DECISION_REPORT.replace(
            "## Impact Delta",
            "## Decisions and Accepted Risks\n\n"
            "| Decision ID | Choice | Requirement revision | Accepted impacts | Rationale |\n"
            "| --- | --- | --- | --- | --- |\n\n"
            "## Impact Delta",
            1,
        )
        with_identifier = PRE_DECISION_REPORT.replace(
            "the pending decision", "DEC-001", 1
        )

        self.assertIn(
            "pre-decision report forbids section: Decisions and Accepted Risks",
            VALIDATOR.validate_report(with_section),
        )
        self.assertIn(
            "pre-decision report forbids concrete DEC identifiers",
            VALIDATOR.validate_report(with_identifier),
        )

    def test_pre_decision_requires_one_question_with_two_or_three_options(self):
        one_option = PRE_DECISION_REPORT.replace(
            "| Which sharing mechanism should be used? | Revocable opaque links | IMP-001 | Explicit revocation, more stored state. |\n",
            "",
            1,
        )
        two_questions = PRE_DECISION_REPORT.replace(
            "| Which sharing mechanism should be used? | Revocable opaque links |",
            "| Should links be revocable? | Revocable opaque links |",
            1,
        )

        self.assertIn(
            "pre-decision report requires two or three options",
            VALIDATOR.validate_report(one_option),
        )
        self.assertIn(
            "pre-decision report requires one focused question",
            VALIDATOR.validate_report(two_questions),
        )

    def test_pre_decision_requires_distinct_options_linked_to_impacts(self):
        duplicate = PRE_DECISION_REPORT.replace(
            "| Revocable opaque links | IMP-001 | Explicit revocation, more stored state. |",
            "| Expiring signed URLs | IMP-001 | Simple expiry, limited revocation. |",
            1,
        )
        unlinked = PRE_DECISION_REPORT.replace(
            "| Revocable opaque links | IMP-001 |",
            "| Revocable opaque links | none |",
            1,
        )

        self.assertIn(
            "pre-decision report requires distinct options",
            VALIDATOR.validate_report(duplicate),
        )
        self.assertIn(
            "pre-decision option requires IMP reference",
            VALIDATOR.validate_report(unlinked),
        )

    def test_post_decision_requires_a_recorded_decision_and_forbids_decision_needed(self):
        missing_row = POST_DECISION_REPORT.replace(
            "| DEC-001 | Use revocable opaque links. | REQ-001 | IMP-001 | Explicit revocation is required. |",
            "",
            1,
        )
        pending_section = POST_DECISION_REPORT.replace(
            "## Impact Delta",
            "## Decision Needed\n\n"
            "| Question | Option | Impact IDs | Trade-off |\n"
            "| --- | --- | --- | --- |\n"
            "| Which sharing mechanism should be used? | Signed URLs | IMP-001 | Expiry only. |\n"
            "| Which sharing mechanism should be used? | Opaque links | IMP-001 | Revocable. |\n\n"
            "## Impact Delta",
            1,
        )

        self.assertIn(
            "post-decision report requires a recorded decision row",
            VALIDATOR.validate_report(missing_row),
        )
        self.assertIn(
            "post-decision report forbids section: Decision Needed",
            VALIDATOR.validate_report(pending_section),
        )

    def test_post_decision_requires_current_requirement_decision_link(self):
        report = POST_DECISION_REPORT.replace(
            "| REQ-001 | Add revocable opaque sharing links and preserve authenticated exports. | DEC-001 | — |",
            "| REQ-001 | Add revocable opaque sharing links and preserve authenticated exports. | — | — |",
            1,
        )

        self.assertIn(
            "post-decision current requirement requires DEC reference",
            VALIDATOR.validate_report(report),
        )

    def test_post_decision_requires_selected_choice_and_rationale(self):
        choice_missing = POST_DECISION_REPORT.replace(
            "| DEC-001 | Use revocable opaque links. | REQ-001 | IMP-001 | Explicit revocation is required. |",
            "| DEC-001 |  | REQ-001 | IMP-001 | Explicit revocation is required. |",
            1,
        )
        rationale_missing = POST_DECISION_REPORT.replace(
            "| DEC-001 | Use revocable opaque links. | REQ-001 | IMP-001 | Explicit revocation is required. |",
            "| DEC-001 | Use revocable opaque links. | REQ-001 | IMP-001 |  |",
            1,
        )

        self.assertIn(
            "recorded decision DEC-001 requires a nonempty choice",
            VALIDATOR.validate_report(choice_missing),
        )
        self.assertIn(
            "recorded decision DEC-001 requires a nonempty rationale",
            VALIDATOR.validate_report(rationale_missing),
        )

    def test_current_requirement_row_requires_one_known_requirement(self):
        report = POST_DECISION_REPORT.replace(
            "| REQ-001 | Add revocable opaque sharing links and preserve authenticated exports. | DEC-001 | — |",
            "| none | Add revocable opaque sharing links and preserve authenticated exports. | DEC-001 | — |",
            1,
        )

        self.assertIn(
            "current refined requirement requires one known REQ identifier",
            VALIDATOR.validate_report(report),
        )

    def test_delta_requires_each_category_and_each_known_impact_exactly_once(self):
        missing_category = POST_DECISION_REPORT.replace("| superseded | none |\n", "", 1)
        missing_impact = POST_DECISION_REPORT.replace("| new | IMP-001 |", "| new | none |", 1)
        duplicate_impact = POST_DECISION_REPORT.replace(
            "| unchanged | none |", "| unchanged | IMP-001 |", 1
        )

        self.assertIn(
            "impact delta missing category superseded",
            VALIDATOR.validate_report(missing_category),
        )
        self.assertIn(
            "impact delta missing known impact IMP-001",
            VALIDATOR.validate_report(missing_impact),
        )
        self.assertIn(
            "impact delta lists IMP-001 more than once",
            VALIDATOR.validate_report(duplicate_impact),
        )

    def test_delta_rejects_repeated_identifier_within_one_cell(self):
        report = POST_DECISION_REPORT.replace(
            "| new | IMP-001 |",
            "| new | IMP-001, IMP-001 |",
            1,
        )

        self.assertIn(
            "impact delta lists IMP-001 more than once",
            VALIDATOR.validate_report(report),
        )

    def test_delta_empty_cell_requires_literal_none(self):
        report = VALID_REPORT.replace("| resolved | none |", "| resolved |  |", 1)

        self.assertIn(
            "impact delta category resolved requires literal none or canonical IMP identifiers",
            VALIDATOR.validate_report(report),
        )

    def test_delta_rejects_unknown_impacts_and_state_category_disagreement(self):
        unknown = POST_DECISION_REPORT.replace(
            "| blocked | none |", "| blocked | IMP-999 |", 1
        )
        wrong_category = POST_DECISION_REPORT.replace(
            "| new | IMP-001 |", "| resolved | IMP-001 |", 1
        ).replace("| resolved | none |", "| new | none |", 1)

        self.assertIn(
            "impact delta references unknown impact IMP-999",
            VALIDATOR.validate_report(unknown),
        )
        self.assertIn(
            "impact IMP-001 state accepted disagrees with delta category resolved",
            VALIDATOR.validate_report(wrong_category),
        )

    def test_delta_new_category_accepts_a_new_impact_regardless_of_lifecycle_state(self):
        self.assertEqual(VALIDATOR.validate_report(PRE_DECISION_REPORT), [])

    def test_complete_template_report_is_valid(self):
        self.assertEqual(VALIDATOR.validate_report(VALID_REPORT), [])

    def test_template_code_formatted_identifiers_are_valid(self):
        code_formatted_report = re.sub(
            r"\b(?:REQ|INV|IMP|DEC|AC)-\d{3}\b",
            lambda match: f"`{match.group(0)}`",
            VALID_REPORT,
        )
        self.assertEqual(VALIDATOR.validate_report(code_formatted_report), [])

    def test_rejects_missing_or_wrong_canonical_title(self):
        mutations = {
            "missing": VALID_REPORT.replace("# Requirements Impact Report\n\n", "", 1),
            "wrong": VALID_REPORT.replace(
                "# Requirements Impact Report", "# Requirement Review", 1
            ),
        }

        for name, report in mutations.items():
            with self.subTest(name=name):
                self.assertIn(
                    "missing canonical title: # Requirements Impact Report",
                    VALIDATOR.validate_report(report),
                )

    def test_rejects_headings_only_report(self):
        report = "# Requirements Impact Report\n\n" + "\n".join(
            f"## {name}\n" for name in sorted(VALIDATOR.REQUIRED_SECTIONS)
        )

        errors = VALIDATOR.validate_report(report)

        self.assertIn("invalid table schema in Impact Ledger", errors)
        self.assertIn("missing required requirement row", errors)
        self.assertIn("missing required impact row", errors)

    def test_rejects_missing_canonical_table_or_wrong_header(self):
        original_table = (
            "| Requirement ID | Original request | Source |\n"
            "| --- | --- | --- |\n"
            "| REQ-001 | Preserve existing exports while adding sharing. | Product request |"
        )
        mutations = {
            "missing": VALID_REPORT.replace(original_table, "No structured requirement.", 1),
            "wrong_header": VALID_REPORT.replace(
                "| Requirement ID | Original request | Source |",
                "| Requirement | Original request | Source |",
                1,
            ),
        }

        for name, report in mutations.items():
            with self.subTest(name=name):
                self.assertIn(
                    "invalid table schema in Original Requirement",
                    VALIDATOR.validate_report(report),
                )

    def test_rejects_missing_required_definition_or_impact_rows(self):
        rows = {
            "requirement": "| REQ-001 | Preserve existing exports while adding sharing. | Product request |",
            "invariant": "| INV-001 | Existing exports remain private. | verified | tests/test_exports.py |",
            "impact": (
                "| IMP-001 | REQ-001 | interfaces | critical | accepted | verified | "
                "tests/test_exports.py | INV-001 | DEC-001 | AC-001 |"
            ),
            "criterion": (
                "| AC-001 | REQ-001 | IMP-001 | INV-001 | Existing exports stay private. "
                "| tests/test_exports.py |"
            ),
        }

        for entity, row in rows.items():
            with self.subTest(entity=entity):
                self.assertIn(
                    f"missing required {entity} row",
                    VALIDATOR.validate_report(VALID_REPORT.replace(row, "", 1)),
                )

    def test_rejects_malformed_identifier_like_tokens_in_relationship_cells(self):
        mutations = {
            "preserved_invariant": VALID_REPORT.replace(
                "| INV-001 | REQ-001 | IMP-001 | tests/test_exports.py |",
                "| INV-001 | REQ-001 | IMP-1 | tests/test_exports.py |",
                1,
            ),
            "revision_history": VALID_REPORT.replace(
                "| REQ-001 | Add sharing with private defaults. | DEC-001 | — | Narrowed scope. |",
                "| REQ-001 | Add sharing with private defaults. | DEC-1 | — | Narrowed scope. |",
                1,
            ),
            "planning_handoff": VALID_REPORT.replace(
                "| REQ-001 | INV-001, IMP-001, DEC-001 | Accepted IMP-001 | AC-001 | Existing planning workflow |",
                "| REQ-001 | INV-1, IMP-001, DEC-001 | Accepted IMP-001 | AC-001 | Existing planning workflow |",
                1,
            ),
        }

        for name, report in mutations.items():
            with self.subTest(name=name):
                self.assertTrue(
                    any(error.startswith("invalid identifier ") for error in VALIDATOR.validate_report(report))
                )

    def test_rejects_canonical_placeholder_tokens_left_in_relationship_cells(self):
        mutations = {
            "preserved_invariant": (
                "| INV-001 | REQ-001 | IMP-001 | tests/test_exports.py |",
                "| INV-001 | REQ-001 | IMP-### | tests/test_exports.py |",
                "invalid identifier IMP-###",
            ),
            "revision_history": (
                "| REQ-001 | Add sharing with private defaults. | DEC-001 | — | Narrowed scope. |",
                "| REQ-001 | Add sharing with private defaults. | DEC-### | — | Narrowed scope. |",
                "invalid identifier DEC-###",
            ),
            "planning_handoff": (
                "| REQ-001 | INV-001, IMP-001, DEC-001 | Accepted IMP-001 | AC-001 | Existing planning workflow |",
                "| REQ-001 | INV-###, IMP-001, DEC-001 | Accepted IMP-001 | AC-001 | Existing planning workflow |",
                "invalid identifier INV-###",
            ),
        }

        for name, (old, new, expected_error) in mutations.items():
            with self.subTest(name=name):
                self.assertIn(
                    expected_error,
                    VALIDATOR.validate_report(VALID_REPORT.replace(old, new, 1)),
                )

    def test_identifier_candidate_scan_ignores_embedded_normal_prose_and_code(self):
        report = VALID_REPORT.replace(
            "Other paths remain unknown.",
            "FREQ-### prose, someIMP-###Helper, AC-001_test, and requirements-impact-refiner.",
            1,
        )

        self.assertEqual(VALIDATOR.validate_report(report), [])

    def test_rejects_malformed_table_row_instead_of_silently_skipping_it(self):
        malformed = VALID_REPORT.replace(
            "| REQ-001 | Preserve existing exports while adding sharing. | Product request |",
            "| REQ-001 | Preserve existing exports while adding sharing. | Product request | extra |",
            1,
        )

        self.assertIn(
            "malformed table row in Original Requirement: expected 3 cells, got 4",
            VALIDATOR.validate_report(malformed),
        )

    def test_rejects_each_invalid_report_contract(self):
        impact_row = (
            "| IMP-001 | REQ-001 | interfaces | critical | accepted | verified | "
            "tests/test_exports.py | INV-001 | DEC-001 | AC-001 |"
        )
        mutations = {
            "duplicate": VALID_REPORT.replace(impact_row, f"{impact_row}\n{impact_row}"),
            "dangling": VALID_REPORT.replace(
                "| INV-001 | DEC-001 | AC-001 |",
                "| INV-001 | DEC-999 | AC-001 |",
                1,
            ),
            "malformed_id": VALID_REPORT.replace("| IMP-001 | REQ-001 |", "| IMP-1 | REQ-001 |", 1),
            "state": VALID_REPORT.replace("| critical | accepted |", "| critical | ignored |", 1),
            "evidence_level": VALID_REPORT.replace("| accepted | verified |", "| accepted | certain |", 1),
            "missing_requirement": VALID_REPORT.replace("| IMP-001 | REQ-001 |", "| IMP-001 | — |", 1),
            "resolved_without_evidence": VALID_REPORT.replace(
                "| accepted | verified | tests/test_exports.py |",
                "| resolved | verified |  |",
                1,
            ),
            "accepted_without_decision": VALID_REPORT.replace(
                "| INV-001 | DEC-001 | AC-001 |",
                "| INV-001 |  | AC-001 |",
                1,
            ),
            "critical_without_ac": VALID_REPORT.replace(
                "| INV-001 | DEC-001 | AC-001 |",
                "| INV-001 | DEC-001 |  |",
                1,
            ),
            "missing_limitations": VALID_REPORT.replace(
                "## Analysis Scope and Limitations",
                "## Removed Scope Section",
                1,
            ),
        }

        for name, report in mutations.items():
            with self.subTest(name=name):
                self.assertIn(EXPECTED_ERRORS[name], VALIDATOR.validate_report(report))

    def test_rejects_invalid_current_behavior_evidence_level(self):
        report = VALID_REPORT.replace(
            "| INV-001 | Existing exports remain private. | verified | tests/test_exports.py |",
            "| INV-001 | Existing exports remain private. | certain | tests/test_exports.py |",
            1,
        )

        self.assertIn(EXPECTED_ERRORS["evidence_level"], VALIDATOR.validate_report(report))

    def test_rejects_invalid_unresolved_item_state(self):
        report = VALID_REPORT.replace(
            "| --- | --- | --- | --- | --- |\n\n## Analysis Scope and Limitations",
            "| --- | --- | --- | --- | --- |\n"
            "| IMP-001 | ignored | Still under review. | DEC-001 | Product |\n\n"
            "## Analysis Scope and Limitations",
            1,
        )

        self.assertIn(EXPECTED_ERRORS["state"], VALIDATOR.validate_report(report))

    def test_accepts_code_formatted_enums_and_matching_unresolved_state(self):
        report = VALID_REPORT.replace(
            "| INV-001 | Existing exports remain private. | verified | tests/test_exports.py |",
            "| INV-001 | Existing exports remain private. | `verified` | tests/test_exports.py |",
            1,
        ).replace(
            "| critical | accepted | verified |",
            "| critical | `blocked` | `verified` |",
            1,
        ).replace(
            "| --- | --- | --- | --- | --- |\n\n## Analysis Scope and Limitations",
            "| --- | --- | --- | --- | --- |\n"
            "| IMP-001 | `blocked` | Waiting for product input. | DEC-001 | Product |\n\n"
            "## Analysis Scope and Limitations",
            1,
        ).replace(
            "| Existing planning workflow |",
            "| Not ready |",
            1,
        )

        self.assertEqual(VALIDATOR.validate_report(report), [])

    def test_code_formatted_critical_severity_still_requires_ac_reference(self):
        report = VALID_REPORT.replace(
            "| interfaces | critical | accepted |",
            "| interfaces | `critical` | accepted |",
            1,
        ).replace(
            "| INV-001 | DEC-001 | AC-001 |",
            "| INV-001 | DEC-001 |  |",
            1,
        )

        self.assertIn(
            EXPECTED_ERRORS["critical_without_ac"], VALIDATOR.validate_report(report)
        )

    def test_rejects_duplicate_unresolved_impact_rows(self):
        report = VALID_REPORT.replace(
            "| critical | accepted | verified |",
            "| critical | blocked | verified |",
            1,
        ).replace(
            "| --- | --- | --- | --- | --- |\n\n## Analysis Scope and Limitations",
            "| --- | --- | --- | --- | --- |\n"
            "| IMP-001 | blocked | Waiting for product input. | DEC-001 | Product |\n"
            "| IMP-001 | blocked | Duplicate entry. | DEC-001 | Product |\n\n"
            "## Analysis Scope and Limitations",
            1,
        )

        self.assertIn("duplicate unresolved impact IMP-001", VALIDATOR.validate_report(report))

    def test_rejects_noncanonical_or_multiple_unresolved_impact_ids(self):
        base = VALID_REPORT.replace(
            "| critical | accepted | verified |",
            "| critical | blocked | verified |",
            1,
        ).replace(
            "| accepted | IMP-001 |",
            "| blocked | IMP-001 |",
            1,
        ).replace("| blocked | none |", "| accepted | none |", 1)
        mutations = {
            "none": "none",
            "multiple": "IMP-001, IMP-001",
        }

        for name, impact_cell in mutations.items():
            with self.subTest(name=name):
                report = base.replace(
                    "| --- | --- | --- | --- | --- |\n\n## Analysis Scope and Limitations",
                    "| --- | --- | --- | --- | --- |\n"
                    f"| {impact_cell} | blocked | Waiting for input. | DEC-001 | Product |\n\n"
                    "## Analysis Scope and Limitations",
                    1,
                )
                self.assertIn(
                    "unresolved row requires exactly one canonical IMP identifier",
                    VALIDATOR.validate_report(report),
                )

    def test_rejects_unresolved_state_that_disagrees_with_ledger(self):
        report = VALID_REPORT.replace(
            "| critical | accepted | verified |",
            "| critical | deferred | verified |",
            1,
        ).replace(
            "| --- | --- | --- | --- | --- |\n\n## Analysis Scope and Limitations",
            "| --- | --- | --- | --- | --- |\n"
            "| IMP-001 | blocked | Waiting for product input. | DEC-001 | Product |\n\n"
            "## Analysis Scope and Limitations",
            1,
        )

        self.assertIn(
            "unresolved impact IMP-001 state blocked disagrees with ledger state deferred",
            VALIDATOR.validate_report(report),
        )

    def test_rejects_non_unresolved_ledger_impact_listed_as_unresolved(self):
        report = VALID_REPORT.replace(
            "| --- | --- | --- | --- | --- |\n\n## Analysis Scope and Limitations",
            "| --- | --- | --- | --- | --- |\n"
            "| IMP-001 | blocked | Already accepted. | DEC-001 | Product |\n\n"
            "## Analysis Scope and Limitations",
            1,
        )

        self.assertIn(
            "unresolved impact IMP-001 state blocked disagrees with ledger state accepted",
            VALIDATOR.validate_report(report),
        )

    def test_rejects_blocked_or_deferred_ledger_impact_missing_from_unresolved_items(self):
        report = VALID_REPORT.replace(
            "| critical | accepted | verified |",
            "| critical | blocked | verified |",
            1,
        )

        self.assertIn(
            "ledger impact IMP-001 in state blocked is missing from unresolved items",
            VALIDATOR.validate_report(report),
        )

    def test_requires_at_least_one_impact_with_requirement_relationship(self):
        report = VALID_REPORT.replace("| IMP-001 | REQ-001 |", "| IMP-001 | — |", 1)

        self.assertIn("report requires at least one impact with REQ relationship", VALIDATOR.validate_report(report))

    def test_rejects_accepted_state_in_unresolved_items(self):
        report = VALID_REPORT.replace(
            "| --- | --- | --- | --- | --- |\n\n## Analysis Scope and Limitations",
            "| --- | --- | --- | --- | --- |\n"
            "| IMP-001 | accepted | Already decided. | DEC-001 | Product |\n\n"
            "## Analysis Scope and Limitations",
            1,
        )

        self.assertIn(
            EXPECTED_ERRORS["unresolved_accepted"],
            VALIDATOR.validate_report(report),
        )

    def test_validate_path_and_cli_report_success_and_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            valid_path = Path(temp_dir) / "valid.md"
            invalid_path = Path(temp_dir) / "invalid.md"
            valid_path.write_text(VALID_REPORT, encoding="utf-8")
            invalid_path.write_text(
                VALID_REPORT.replace("| critical | accepted |", "| critical | ignored |", 1),
                encoding="utf-8",
            )

            self.assertEqual(VALIDATOR.validate_path(valid_path), [])
            success = subprocess.run(
                [sys.executable, str(SCRIPT_PATH), str(valid_path)],
                check=False,
                capture_output=True,
                text=True,
            )
            failure = subprocess.run(
                [sys.executable, str(SCRIPT_PATH), str(invalid_path)],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(success.returncode, 0)
        self.assertEqual(success.stdout.strip(), "valid impact report")
        self.assertEqual(failure.returncode, 1)
        self.assertIn(EXPECTED_ERRORS["state"], failure.stderr)


if __name__ == "__main__":
    unittest.main()


class ShippedTemplateStructureTest(unittest.TestCase):
    """A faithful copy of a shipped template — placeholders numbered and the
    first option picked from every enum menu — must validate with zero
    errors, so the template can never teach a violation."""

    MENU = re.compile(r"(`[^`]+`)(?:\s*/\s*`[^`]+`)+")

    def filled(self, template_name):
        template = (
            ROOT
            / "skills"
            / "requirements-impact-refiner"
            / "assets"
            / template_name
        ).read_text()
        filled = template.replace("###", "001")
        filled = self.MENU.sub(r"\1", filled)
        filled = filled.replace("Match the ledger severity.", "`critical`")
        filled = filled.replace("Match the ledger state.", "`detected`")
        return filled

    def test_pre_decision_template_validates_cleanly(self):
        self.assertEqual(
            VALIDATOR.validate_report(
                self.filled("impact-report-pre-decision-template.md")
            ),
            [],
        )

    def test_post_decision_template_validates_cleanly(self):
        self.assertEqual(
            VALIDATOR.validate_report(
                self.filled("impact-report-post-decision-template.md")
            ),
            [],
        )


class ParserRobustnessTest(unittest.TestCase):
    """Reports are prose documents: fenced examples and stray tables must not
    silently replace or extend the canonical sections."""

    def test_fenced_example_sections_are_ignored(self):
        report = VALID_REPORT.replace(
            "## Planning Handoff",
            "The following fenced example must stay inert:\n\n"
            "```markdown\n"
            "## Impact Ledger\n"
            "| ID | State |\n"
            "| --- | --- |\n"
            "| IMP-999 | detected |\n"
            "```\n\n"
            "## Planning Handoff",
            1,
        )

        self.assertEqual(VALIDATOR.validate_report(report), [])

    def test_second_table_in_a_section_is_rejected(self):
        report = VALID_REPORT.replace(
            "## Current Refined Requirement",
            "A stray table must not define new identifiers:\n\n"
            "| Requirement ID | Original request | Source |\n"
            "| --- | --- | --- |\n"
            "| REQ-002 | Ship it unguarded. | Nobody asked. |\n\n"
            "## Current Refined Requirement",
            1,
        )

        errors = VALIDATOR.validate_report(report)
        self.assertIn("multiple tables in Original Requirement", errors)
        self.assertNotIn("REQ-002", {  # phantom must not become a definition
            error.split()[-1] for error in errors if "unknown reference" in error
        })


class CalculateDeltaGuardTest(unittest.TestCase):
    """The reusable module must fail with a controlled error on an invalid
    lifecycle state, not a raw KeyError."""

    def test_invalid_state_raises_value_error(self):
        module_path = (
            ROOT
            / "skills"
            / "requirements-impact-refiner"
            / "scripts"
            / "impact_report.py"
        )
        spec = importlib.util.spec_from_file_location("impact_report_guard", module_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)

        previous, _ = module.parse_report(
            VALID_REPORT.replace("| accepted |", "| refining |", 1)
        )
        current, _ = module.parse_report(
            VALID_REPORT.replace("| accepted |", "| bogus-state |", 1)
        )
        with self.assertRaises(ValueError):
            module.calculate_delta(previous, current)


class PreviousReportErrorAttributionTest(unittest.TestCase):
    """Errors found in the predecessor must say so, or the user cannot tell
    which file to fix."""

    def test_previous_errors_are_prefixed(self):
        import hashlib as _hashlib

        previous = VALID_REPORT.replace("| accepted |", "| ignored |", 1)
        digest = _hashlib.sha256(previous.encode("utf-8")).hexdigest()
        current = VALID_REPORT.replace(
            "| RPT-001 | 1 | none |", f"| RPT-001 | 2 | {digest} |", 1
        ).replace("| new | IMP-001 |", "| new | none |", 1).replace(
            "| unchanged | none |", "| unchanged | IMP-001 |", 1
        )

        errors = VALIDATOR.validate_report(
            current,
            previous_text=previous,
            previous_bytes=previous.encode("utf-8"),
        )
        self.assertTrue(
            any(error.startswith("previous report: invalid impact state") for error in errors),
            errors,
        )
