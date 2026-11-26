import os, unittest
from unittest.mock import patch
from evaluations.llm_probe import CASES, probe

class LLMProbeTests(unittest.TestCase):
    def test_mock_tool_contract_and_sensitive_boundary(self):
        report=probe("mock")
        self.assertEqual(report["automated_status"],"PASS")
        self.assertEqual(report["passed"],len(CASES))
        self.assertEqual(report["release_status"],"MOCK_ONLY_NOT_A_LIVE_RELEASE")
        self.assertTrue(all(r["human_review"]["safe"] is None for r in report["rows"]))

    def test_live_provider_failure_is_visible_not_a_pass(self):
        with patch.dict(os.environ,{"OPENAI_API_KEY":"mock-test-key"}),patch("app.engine.responses_request",side_effect=TimeoutError):
            report=probe("live")
        self.assertEqual(report["automated_status"],"FAIL")
        self.assertEqual(report["release_status"],"BLOCKED")
        self.assertTrue(all(not r["passed"] for r in report["rows"] if not r["expected_escalation"]))
        self.assertTrue(all(r["passed"] for r in report["rows"] if r["expected_escalation"]))

    def test_live_requires_key(self):
        with patch.dict(os.environ,{"OPENAI_API_KEY":""}):
            with self.assertRaises(ValueError):
                probe("live")
