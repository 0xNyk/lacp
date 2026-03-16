#!/usr/bin/env python3
"""Unit tests for stop_quality_gate.py checkers."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Ensure hooks dir is importable
sys.path.insert(0, str(Path(__file__).parent))

from stop_quality_gate import (
    CheckResult,
    Context,
    check_circuit_breaker,
    check_heuristic_rationalization,
    check_loop_guard,
    check_message_trivial,
    check_ralph_cooperation,
    check_test_verification,
    check_work_detector,
    _build_context,
    _emit,
    _increment_circuit_breaker,
)


def _ctx(
    stripped: str = "some message content here that is long enough",
    session_id: str = "test-session",
    stop_hook_active: bool = False,
    ralph_active: bool = False,
    transcript_path: str = "",
    last_message: str = "",
) -> Context:
    return Context(
        hook_input={},
        session_id=session_id,
        cwd=os.getcwd(),
        last_message=last_message or stripped,
        stripped=stripped,
        transcript_path=transcript_path,
        stop_hook_active=stop_hook_active,
        ralph_active=ralph_active,
    )


class TestLoopGuard(unittest.TestCase):
    def test_active_allows(self):
        result = check_loop_guard(_ctx(stop_hook_active=True))
        self.assertIsNotNone(result)
        self.assertEqual(result.decision, "allow")

    def test_inactive_passes(self):
        result = check_loop_guard(_ctx(stop_hook_active=False))
        self.assertIsNone(result)


class TestCircuitBreaker(unittest.TestCase):
    def test_no_session_passes(self):
        result = check_circuit_breaker(_ctx(session_id=""))
        self.assertIsNone(result)

    def test_under_limit_passes(self):
        circuit = Path(f"/tmp/lacp-quality-gate-count-test-cb-under")
        circuit.write_text("1")
        try:
            result = check_circuit_breaker(_ctx(session_id="test-cb-under"))
            self.assertIsNone(result)
        finally:
            circuit.unlink(missing_ok=True)

    def test_at_limit_allows(self):
        circuit = Path(f"/tmp/lacp-quality-gate-count-test-cb-at")
        circuit.write_text("3")
        try:
            result = check_circuit_breaker(_ctx(session_id="test-cb-at"))
            self.assertIsNotNone(result)
            self.assertEqual(result.decision, "allow")
            self.assertFalse(circuit.exists())  # Should be cleaned up
        finally:
            circuit.unlink(missing_ok=True)


class TestMessageTrivial(unittest.TestCase):
    def test_empty_allows(self):
        result = check_message_trivial(_ctx(stripped=""))
        self.assertIsNotNone(result)
        self.assertEqual(result.decision, "allow")

    def test_short_allows(self):
        result = check_message_trivial(_ctx(stripped="Done."))
        self.assertIsNotNone(result)
        self.assertEqual(result.decision, "allow")

    def test_long_passes(self):
        result = check_message_trivial(_ctx(stripped="x" * 200))
        self.assertIsNone(result)


class TestHeuristicRationalization(unittest.TestCase):
    def test_no_patterns(self):
        hits, matched = check_heuristic_rationalization(
            _ctx(stripped="I fixed the bug and all tests pass. Here's a summary of changes.")
        )
        self.assertEqual(hits, 0)
        self.assertEqual(matched, [])

    def test_single_pattern(self):
        hits, matched = check_heuristic_rationalization(
            _ctx(stripped="This is a pre-existing issue that was already there before I started.")
        )
        self.assertEqual(hits, 1)
        self.assertIn("pre-existing/out-of-scope", matched)

    def test_multiple_patterns(self):
        msg = (
            "There are too many issues to address. These are pre-existing problems. "
            "I would suggest a follow-up session to handle the remaining items."
        )
        hits, matched = check_heuristic_rationalization(_ctx(stripped=msg))
        self.assertGreaterEqual(hits, 3)

    def test_effort_inflation(self):
        hits, matched = check_heuristic_rationalization(
            _ctx(stripped="This would require significant refactoring to implement properly.")
        )
        self.assertEqual(hits, 1)
        self.assertIn("effort-inflation", matched)

    def test_abandonment(self):
        hits, matched = check_heuristic_rationalization(
            _ctx(stripped="I'll leave this as is for now and move on to the next task.")
        )
        self.assertGreaterEqual(hits, 1)
        self.assertIn("abandonment", matched)


class TestWorkDetector(unittest.TestCase):
    def test_no_transcript(self):
        files_changed, threshold = check_work_detector(_ctx(transcript_path=""), 1)
        self.assertEqual(files_changed, -1)
        self.assertEqual(threshold, 2)

    def test_short_message_skips(self):
        files_changed, threshold = check_work_detector(
            _ctx(stripped="short", transcript_path="/tmp/fake"), 1
        )
        self.assertEqual(files_changed, -1)
        self.assertEqual(threshold, 2)


class TestRalphCooperation(unittest.TestCase):
    def test_not_active_blocks(self):
        result = check_ralph_cooperation(
            _ctx(ralph_active=False),
            "rationalization detected",
            ["deferral"],
        )
        self.assertEqual(result.decision, "block")
        self.assertEqual(result.reason, "rationalization detected")

    def test_active_allows_with_feedback(self):
        # Create temp ralph state file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write('iteration: 3\ncompletion_promise: "finish all tests"')
            ralph_path = f.name

        try:
            with patch("stop_quality_gate.RALPH_STATE_FILE", ralph_path):
                result = check_ralph_cooperation(
                    _ctx(ralph_active=True),
                    "deferral detected",
                    ["deferral", "scope-deflection"],
                )
                self.assertEqual(result.decision, "allow")
                self.assertIn("iteration 3", result.system_message)
                self.assertIn("deferral", result.system_message)
                self.assertIn("finish all tests", result.system_message)
        finally:
            os.unlink(ralph_path)


class TestCircuitBreakerIncrement(unittest.TestCase):
    def test_increment(self):
        circuit = Path("/tmp/lacp-quality-gate-count-test-incr")
        circuit.unlink(missing_ok=True)
        try:
            count = _increment_circuit_breaker("test-incr")
            self.assertEqual(count, 1)
            count = _increment_circuit_breaker("test-incr")
            self.assertEqual(count, 2)
        finally:
            circuit.unlink(missing_ok=True)


class TestEmit(unittest.TestCase):
    def test_block_output(self):
        import io
        captured = io.StringIO()
        with patch("sys.stdout", captured):
            _emit(CheckResult("block", reason="test reason"))
        output = json.loads(captured.getvalue())
        self.assertEqual(output["decision"], "block")
        self.assertEqual(output["reason"], "test reason")

    def test_allow_with_message(self):
        import io
        captured = io.StringIO()
        with patch("sys.stdout", captured):
            _emit(CheckResult("allow", system_message="feedback here"))
        output = json.loads(captured.getvalue())
        self.assertEqual(output["decision"], "allow")
        self.assertEqual(output["systemMessage"], "feedback here")

    def test_allow_no_output(self):
        import io
        captured = io.StringIO()
        with patch("sys.stdout", captured):
            _emit(CheckResult("allow"))
        self.assertEqual(captured.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
