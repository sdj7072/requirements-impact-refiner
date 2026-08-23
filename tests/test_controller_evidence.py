import json
import unittest


from evals.harness.controller_evidence import analyze_controller_trace


def completed(tool, arguments, structured, *, status="completed", error=None):
    return json.dumps(
        {
            "type": "item.completed",
            "item": {
                "id": "item-%s" % tool,
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


class ControllerEvidenceTest(unittest.TestCase):
    def test_completed_begin_finalize_trace_binds_draft_and_display_bytes(self):
        draft_id = "0123456789abcdef0123456789abcdef"
        display = "## Change Impact Summary\n\n- safe"
        trace = "\n".join(
            (
                completed("rir_begin", {"repo_root": "/tmp/work"}, {"draft_id": draft_id}),
                completed(
                    "rir_finalize",
                    {"repo_root": "/tmp/work", "draft_id": draft_id, "analysis": {}},
                    {"status": "published", "draft_id": draft_id, "display_text": display},
                ),
            )
        )

        evidence = analyze_controller_trace((trace,), display, expected_turns=1)

        self.assertTrue(evidence.valid)
        self.assertEqual(evidence.tool_order, ("rir_begin", "rir_finalize"))
        self.assertEqual(evidence.begin_calls, 1)
        self.assertEqual(evidence.finalize_calls, 1)
        self.assertTrue(evidence.draft_ids_match)
        self.assertTrue(evidence.finalize_succeeded)
        self.assertTrue(evidence.display_text_matches)
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
            "output": (("\n".join((good_begin, completed("rir_finalize", {"draft_id": draft}, {"status": "published", "draft_id": draft, "display_text": "controller"}))),), "agent rewrite"),
            "error": (("\n".join((good_begin, completed("rir_finalize", {"draft_id": draft}, {}, status="failed", error={"message": "bad"}))),), "final"),
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
            rows.append(completed("rir_begin", {}, {"draft_id": draft}))
            rows.append(completed("rir_finalize", {"draft_id": draft}, {"status": "published", "draft_id": draft, "display_text": display}))

        lineage = analyze_controller_trace(("\n".join(rows[:2]), "\n".join(rows[2:])), ("first", "second"), expected_turns=2)
        negative = analyze_controller_trace(('{"type":"item.completed","item":{"type":"agent_message","text":"debug"}}',), "debug", expected_turns=0)

        self.assertTrue(lineage.valid)
        self.assertEqual((lineage.begin_calls, lineage.finalize_calls), (2, 2))
        self.assertTrue(negative.valid)
        self.assertEqual(negative.tool_order, ())

    def test_prose_and_in_progress_events_are_not_tool_evidence(self):
        prose = json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "I called rir_begin then rir_finalize"}})
        started = completed("rir_begin", {}, {"draft_id": "0" * 32}, status="in_progress")

        evidence = analyze_controller_trace(("\n".join((prose, started)),), "done", expected_turns=1)

        self.assertFalse(evidence.valid)
        self.assertEqual((evidence.begin_calls, evidence.finalize_calls), (1, 0))

    def test_failed_duplicate_call_cannot_disappear_from_attempt_inventory(self):
        draft = "0" * 32
        good_begin = completed("rir_begin", {}, {"draft_id": draft})
        failed_event = json.loads(completed(
            "rir_begin", {}, {}, status="failed", error={"message": "boom"}
        ))
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

    def test_lineage_binds_each_finalize_display_to_its_turn_output(self):
        rows = []
        for suffix, display in (("0", "wrong first"), ("1", "second")):
            draft = suffix * 32
            rows.append(completed("rir_begin", {}, {"draft_id": draft}))
            rows.append(completed("rir_finalize", {"draft_id": draft}, {"status": "published", "display_text": display}))

        evidence = analyze_controller_trace(
            ("\n".join(rows[:2]), "\n".join(rows[2:])),
            ("first", "second"),
            expected_turns=2,
        )

        self.assertFalse(evidence.valid)
        self.assertFalse(evidence.display_text_matches)

    def test_same_named_tools_from_another_server_cannot_satisfy_controller_gate(self):
        draft = "0" * 32
        begin = json.loads(completed("rir_begin", {}, {"draft_id": draft}))
        finalize = json.loads(completed("rir_finalize", {"draft_id": draft}, {"status": "published", "display_text": "done"}))
        begin["item"]["server"] = "unrelated"
        finalize["item"]["server"] = "unrelated"

        evidence = analyze_controller_trace(
            ("\n".join((json.dumps(begin), json.dumps(finalize))),),
            "done",
            expected_turns=1,
        )

        self.assertFalse(evidence.valid)
        self.assertEqual(evidence.tool_order, ())


if __name__ == "__main__":
    unittest.main()
