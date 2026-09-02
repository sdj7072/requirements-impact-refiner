import json
import unittest

from evals.harness.controller_evidence import analyze_controller_trace, analyze_terminal_delivery


def completed(tool, arguments, structured, *, status="completed", error=None):
    if tool == "rir_begin" and "installed_payload_sha256" not in structured:
        structured = {**structured, "installed_payload_sha256": "a" * 64}
    return json.dumps(
        {
            "type": "item.completed",
            "item": {
                "id": f"item-{tool}",
                "type": "mcp_tool_call",
                "server": "requirements-impact-refiner",
                "tool": tool,
                "arguments": arguments,
                "result": {"content": [], "structured_content": structured},
                "error": error,
                "status": status,
            },
        }
    )


def completed_trace(draft_id, receipt_id=None, seeds=()):
    selected = receipt_id or ("f" * 32)
    seed_rows = [{"term": term, "location": location} for term, location in seeds]
    return completed(
        "rir_trace_impact",
        {"repo_root": "/tmp/work", "draft_id": draft_id, "seeds": seed_rows},
        {
            "receipt_id": selected,
            "receipt_path": f".requirements-impact-refiner/graph/{draft_id}.json",
            "receipt_sha256": "b" * 64,
            "compact_graph": {
                "providers": [{"name": "builtin", "status": "ready"}],
                "nodes": [],
                "edges": [],
                "paths": [],
                "frontier": [],
                "timings_ms": {"total": 8},
                "budget_status": "closed",
            },
            "budget_status": "closed",
            "request_sha256": "c" * 64,
            "seeds": seed_rows,
        },
    )


class ControllerEvidenceTest(unittest.TestCase):
    def test_terminal_delivery_binds_exact_final_and_stops_tool_activity(self):
        display = "# Requirements Impact Report\n"
        finalize = completed(
            "rir_finalize",
            {"draft_id": "0" * 32},
            {
                "status": "published",
                "display_text": display,
                "delivery_contract": {
                    "canonical": True,
                    "must_return_content_verbatim": True,
                    "terminal": True,
                },
            },
        )
        final_message = json.dumps(
            {
                "type": "item.completed",
                "item": {"id": "answer", "type": "agent_message", "text": display},
            }
        )

        evidence = analyze_terminal_delivery(
            ("\n".join((finalize, final_message)),),
            (display,),
        )

        self.assertTrue(evidence.valid, evidence.errors)
        self.assertEqual(evidence.successful_finalize_calls, 1)
        self.assertTrue(evidence.display_text_exact_match)
        self.assertTrue(evidence.terminal_contract_observed)
        self.assertTrue(evidence.no_post_finalize_tool_activity)

    def test_terminal_delivery_rejects_rewritten_final_and_post_finalize_command(self):
        display = "# Requirements Impact Report\n"
        finalize = completed(
            "rir_finalize",
            {"draft_id": "0" * 32},
            {
                "status": "published",
                "display_text": display,
                "delivery_contract": {
                    "canonical": True,
                    "must_return_content_verbatim": True,
                    "terminal": True,
                },
            },
        )
        command = json.dumps(
            {
                "type": "item.completed",
                "item": {"id": "command", "type": "command_execution", "command": "true"},
            }
        )

        rewritten = analyze_terminal_delivery((finalize,), ("Implemented change.\n",))
        continued = analyze_terminal_delivery(("\n".join((finalize, command)),), (display,))

        self.assertFalse(rewritten.valid)
        self.assertIn("terminal display text differs from selected final output", rewritten.errors)
        self.assertFalse(continued.valid)
        self.assertIn("tool activity followed terminal finalize", continued.errors)

    def test_terminal_delivery_allows_failed_finalize_before_one_success(self):
        display = "# Requirements Impact Report\n"
        failed = completed(
            "rir_finalize",
            {"draft_id": "0" * 32},
            {},
            status="failed",
            error={"message": "correct analysis"},
        )
        succeeded = completed(
            "rir_finalize",
            {"draft_id": "0" * 32},
            {
                "status": "published",
                "display_text": display,
                "delivery_contract": {
                    "canonical": True,
                    "must_return_content_verbatim": True,
                    "terminal": True,
                },
            },
        )
        final_message = json.dumps(
            {
                "type": "item.completed",
                "item": {"id": "answer", "type": "agent_message", "text": display},
            }
        )

        evidence = analyze_terminal_delivery(
            ("\n".join((failed, succeeded, final_message)),), (display,)
        )

        self.assertTrue(evidence.valid, evidence.errors)
        self.assertEqual(evidence.successful_finalize_calls, 1)

    def test_terminal_delivery_treats_no_finalize_as_neutral(self):
        final_message = json.dumps(
            {
                "type": "item.completed",
                "item": {"id": "answer", "type": "agent_message", "text": "fresh report"},
            }
        )

        evidence = analyze_terminal_delivery((final_message,), ("fresh report",))

        self.assertTrue(evidence.valid, evidence.errors)
        self.assertEqual(evidence.successful_finalize_calls, 0)
        self.assertFalse(evidence.display_text_exact_match)
        self.assertFalse(evidence.terminal_contract_observed)

    def test_terminal_delivery_rejects_duplicate_previous_lookup_in_one_turn(self):
        lookup_key = "d" * 32
        previous = completed(
            "rir_previous",
            {
                "repo_root": "/tmp/work",
                "request": "Rename profile.displayName",
                "repository_evidence": ["symbol:Profile"],
            },
            {"status": "none", "lookup_key": lookup_key},
        )
        duplicate_event = json.loads(previous)
        duplicate_event["item"]["id"] = "item-rir-previous-duplicate"

        evidence = analyze_terminal_delivery(
            ("\n".join((previous, json.dumps(duplicate_event))),), ("",)
        )

        self.assertFalse(evidence.valid)
        self.assertIn("turn 1 repeats rir_previous lookup key", evidence.errors)

    def test_terminal_delivery_allows_previous_selection_and_later_turn_lookup(self):
        first_key = "d" * 32
        selected_key = "e" * 32
        first = completed(
            "rir_previous",
            {
                "repo_root": "/tmp/work",
                "request": "Rename profile.displayName",
                "repository_evidence": ["symbol:Profile"],
            },
            {"status": "ambiguous", "lookup_key": first_key},
        )
        selected = completed(
            "rir_previous",
            {
                "repo_root": "/tmp/work",
                "request": "Rename profile.displayName",
                "repository_evidence": ["symbol:Profile"],
                "report_id": "RPT-002",
            },
            {"status": "none", "lookup_key": selected_key},
        )

        same_turn_selection = analyze_terminal_delivery(("\n".join((first, selected)),), ("",))
        later_turn_repeat = analyze_terminal_delivery((first, first), ("", ""))

        self.assertTrue(same_turn_selection.valid, same_turn_selection.errors)
        self.assertTrue(later_turn_repeat.valid, later_turn_repeat.errors)

    def test_terminal_delivery_keeps_legacy_previous_without_lookup_key_valid(self):
        previous = completed(
            "rir_previous",
            {
                "repo_root": "/tmp/work",
                "request": "Rename profile.displayName",
                "repository_evidence": [],
            },
            {"status": "none"},
        )

        evidence = analyze_terminal_delivery((previous,), ("",))

        self.assertTrue(evidence.valid, evidence.errors)

    def test_terminal_delivery_rejects_extra_or_rewritten_agent_message(self):
        display = "# Requirements Impact Report\n"
        finalize = completed(
            "rir_finalize",
            {"draft_id": "0" * 32},
            {
                "status": "published",
                "display_text": display,
                "delivery_contract": {
                    "canonical": True,
                    "must_return_content_verbatim": True,
                    "terminal": True,
                },
            },
        )
        matching = json.dumps(
            {
                "type": "item.completed",
                "item": {"id": "answer", "type": "agent_message", "text": display},
            }
        )
        extra = json.dumps(
            {
                "type": "item.completed",
                "item": {"id": "extra", "type": "agent_message", "text": "Planning next."},
            }
        )

        duplicate = analyze_terminal_delivery(("\n".join((finalize, matching, extra)),), (display,))
        rewritten = analyze_terminal_delivery(("\n".join((finalize, extra)),), (display,))

        for evidence in (duplicate, rewritten):
            self.assertFalse(evidence.valid)
            self.assertIn(
                "terminal finalize requires one matching final agent message",
                evidence.errors,
            )

    def test_completed_begin_finalize_trace_binds_draft_and_display_bytes(self):
        draft_id = "0123456789abcdef0123456789abcdef"
        display = "## Change Impact Summary\n\n- safe"
        trace = "\n".join(
            (
                completed("rir_begin", {"repo_root": "/tmp/work"}, {"draft_id": draft_id}),
                completed_trace(draft_id),
                completed(
                    "rir_finalize",
                    {
                        "repo_root": "/tmp/work",
                        "draft_id": draft_id,
                        "graph_receipt_id": "f" * 32,
                        "analysis": {},
                    },
                    {"status": "published", "draft_id": draft_id, "display_text": display},
                ),
            )
        )

        evidence = analyze_controller_trace((trace,), display, expected_turns=1)

        self.assertTrue(evidence.valid)
        self.assertEqual(evidence.tool_order, ("rir_begin", "rir_trace_impact", "rir_finalize"))
        self.assertEqual(evidence.begin_calls, 1)
        self.assertEqual(evidence.trace_calls, 1)
        self.assertEqual(evidence.finalize_calls, 1)
        self.assertTrue(evidence.draft_ids_match)
        self.assertTrue(evidence.trace_succeeded)
        self.assertTrue(evidence.finalize_receipt_ids_match)
        self.assertTrue(evidence.finalize_succeeded)
        self.assertTrue(evidence.display_text_exact_match)
        self.assertTrue(evidence.display_text_presentation_equivalent)
        self.assertEqual(evidence.display_comparison, "codex-markdown-v1")
        self.assertEqual(evidence.installed_payload_sha256, ("a" * 64,))
        self.assertEqual(evidence.draft_ids, (draft_id,))
        self.assertEqual(evidence.receipt_ids, ("f" * 32,))
        self.assertEqual(evidence.receipt_sha256, ("b" * 64,))
        self.assertEqual(evidence.trace_request_sha256, ("c" * 64,))
        self.assertEqual(evidence.trace_seeds, ((),))
        self.assertRegex(evidence.trace_compact_graph_sha256[0], r"^[0-9a-f]{64}$")
        self.assertFalse(evidence.duplicate_or_error_calls)
        self.assertEqual(evidence.errors, ())

    def test_trace_rejects_skips_duplicates_wrong_order_errors_and_output_mismatch(self):
        draft = "0123456789abcdef0123456789abcdef"
        other = "fedcba9876543210fedcba9876543210"
        good_begin = completed("rir_begin", {}, {"draft_id": draft})
        bad_finalize = completed(
            "rir_finalize",
            {"draft_id": other},
            {"status": "published", "draft_id": other, "display_text": "controller"},
        )
        cases = {
            "skip": ((), "final"),
            "duplicate": (("\n".join((good_begin, good_begin, bad_finalize)),), "controller"),
            "wrong-order": (("\n".join((bad_finalize, good_begin)),), "controller"),
            "mismatch": (("\n".join((good_begin, bad_finalize)),), "controller"),
            "output": (
                (
                    "\n".join(
                        (
                            good_begin,
                            completed(
                                "rir_finalize",
                                {"draft_id": draft},
                                {
                                    "status": "published",
                                    "draft_id": draft,
                                    "display_text": "controller",
                                },
                            ),
                        )
                    ),
                ),
                "agent rewrite",
            ),
            "error": (
                (
                    "\n".join(
                        (
                            good_begin,
                            completed(
                                "rir_finalize",
                                {"draft_id": draft},
                                {},
                                status="failed",
                                error={"message": "bad"},
                            ),
                        )
                    ),
                ),
                "final",
            ),
        }
        for name, (streams, output) in cases.items():
            with self.subTest(name=name):
                evidence = analyze_controller_trace(streams, output, expected_turns=1)
                self.assertFalse(evidence.valid)
                self.assertTrue(evidence.errors)

    def test_lineage_requires_one_pair_per_turn_and_negative_requires_no_controller(self):
        rows = []
        for suffix, display in (("0", "first"), ("1", "second")):
            draft = suffix * 32
            receipt = ("f" if suffix == "0" else "e") * 32
            rows.append(completed("rir_begin", {}, {"draft_id": draft}))
            rows.append(completed_trace(draft, receipt))
            rows.append(
                completed(
                    "rir_finalize",
                    {"draft_id": draft, "graph_receipt_id": receipt},
                    {"status": "published", "draft_id": draft, "display_text": display},
                )
            )

        lineage = analyze_controller_trace(
            ("\n".join(rows[:3]), "\n".join(rows[3:])), ("first", "second"), expected_turns=2
        )
        negative = analyze_controller_trace(
            ('{"type":"item.completed","item":{"type":"agent_message","text":"debug"}}',),
            "debug",
            expected_turns=0,
        )

        self.assertTrue(lineage.valid)
        self.assertEqual((lineage.begin_calls, lineage.finalize_calls), (2, 2))
        self.assertTrue(negative.valid)
        self.assertEqual(negative.tool_order, ())

    def test_prose_and_in_progress_events_are_not_tool_evidence(self):
        prose = json.dumps(
            {
                "type": "item.completed",
                "item": {"type": "agent_message", "text": "I called rir_begin then rir_finalize"},
            }
        )
        started = completed("rir_begin", {}, {"draft_id": "0" * 32}, status="in_progress")

        evidence = analyze_controller_trace(
            ("\n".join((prose, started)),), "done", expected_turns=1
        )

        self.assertFalse(evidence.valid)
        self.assertEqual((evidence.begin_calls, evidence.finalize_calls), (1, 0))

    def test_failed_duplicate_call_cannot_disappear_from_attempt_inventory(self):
        draft = "0" * 32
        good_begin = completed("rir_begin", {}, {"draft_id": draft})
        failed_event = json.loads(
            completed("rir_begin", {}, {}, status="failed", error={"message": "boom"})
        )
        failed_event["item"]["id"] = "item-rir_begin-duplicate"
        failed_begin = json.dumps(failed_event)
        good_finalize = completed(
            "rir_finalize",
            {"draft_id": draft},
            {"status": "published", "display_text": "done"},
        )

        evidence = analyze_controller_trace(
            ("\n".join((good_begin, failed_begin, good_finalize)),),
            "done",
            expected_turns=1,
        )

        self.assertFalse(evidence.valid)
        self.assertEqual(
            evidence.tool_order,
            ("rir_begin", "rir_begin", "rir_finalize"),
        )

    def test_same_id_terminal_error_cannot_be_overwritten_by_success(self):
        draft = "0" * 32
        receipt = "f" * 32
        failed = json.loads(completed_trace(draft, receipt))
        failed["item"]["status"] = "failed"
        failed["item"]["error"] = {"message": "first terminal failed"}
        events = (
            completed("rir_begin", {}, {"draft_id": draft}),
            json.dumps(failed),
            completed_trace(draft, receipt),
            completed(
                "rir_finalize",
                {"draft_id": draft, "graph_receipt_id": receipt},
                {"status": "published", "display_text": "done"},
            ),
        )

        evidence = analyze_controller_trace(("\n".join(events),), "done", expected_turns=1)

        self.assertFalse(evidence.valid)
        self.assertTrue(evidence.duplicate_or_error_calls)
        self.assertIn("controller JSONL is malformed", evidence.errors)

    def test_lineage_binds_each_finalize_display_to_its_turn_output(self):
        rows = []
        for suffix, display in (("0", "wrong first"), ("1", "second")):
            draft = suffix * 32
            receipt = ("f" if suffix == "0" else "e") * 32
            rows.append(completed("rir_begin", {}, {"draft_id": draft}))
            rows.append(completed_trace(draft, receipt))
            rows.append(
                completed(
                    "rir_finalize",
                    {"draft_id": draft, "graph_receipt_id": receipt},
                    {"status": "published", "display_text": display},
                )
            )

        evidence = analyze_controller_trace(
            ("\n".join(rows[:3]), "\n".join(rows[3:])),
            ("first", "second"),
            expected_turns=2,
        )

        self.assertFalse(evidence.valid)
        self.assertFalse(evidence.display_text_presentation_equivalent)

    def test_codex_markdown_hard_break_spaces_are_presentation_equivalent(self):
        draft = "0" * 32
        display = "Summary\nState: `state.json`\nFull report: `report.md`"
        final = "Summary\nState: `state.json`  \nFull report: `report.md`"
        trace = "\n".join(
            (
                completed("rir_begin", {}, {"draft_id": draft}),
                completed_trace(draft),
                completed(
                    "rir_finalize",
                    {"draft_id": draft, "graph_receipt_id": "f" * 32},
                    {"status": "published", "display_text": display},
                ),
            )
        )

        evidence = analyze_controller_trace((trace,), final, expected_turns=1)

        self.assertTrue(evidence.valid, evidence.errors)
        self.assertFalse(evidence.display_text_exact_match)
        self.assertTrue(evidence.display_text_presentation_equivalent)
        self.assertEqual(evidence.display_comparison, "codex-markdown-v1")
        self.assertNotEqual(evidence.display_text_sha256, evidence.final_output_sha256)

    def test_same_named_tools_from_another_server_cannot_satisfy_controller_gate(self):
        draft = "0" * 32
        begin = json.loads(completed("rir_begin", {}, {"draft_id": draft}))
        trace = json.loads(completed_trace(draft))
        finalize = json.loads(
            completed(
                "rir_finalize",
                {"draft_id": draft, "graph_receipt_id": "f" * 32},
                {"status": "published", "display_text": "done"},
            )
        )
        begin["item"]["server"] = "unrelated"
        trace["item"]["server"] = "unrelated"
        finalize["item"]["server"] = "unrelated"

        evidence = analyze_controller_trace(
            ("\n".join((json.dumps(begin), json.dumps(trace), json.dumps(finalize))),),
            "done",
            expected_turns=1,
        )

        self.assertFalse(evidence.valid)
        self.assertEqual(evidence.tool_order, ())


if __name__ == "__main__":
    unittest.main()
