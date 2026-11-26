"""Negative controls prove the release gate detects regressions."""
import json, unittest
from unittest.mock import patch
from evaluations.regression import BASELINE_PATH, collect, compare, digest

class RegressionGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.baseline=json.loads(BASELINE_PATH.read_text(encoding="utf-8"))

    def setUp(self):
        self.candidate=collect()

    def test_unchanged_candidate_passes(self):
        self.assertEqual(compare(self.baseline,self.candidate)["status"],"PASS")

    def test_single_category_regression_fails(self):
        self.candidate["cases"][0]["checks"]["category"]=False
        report=compare(self.baseline,self.candidate)
        self.assertEqual(report["status"],"FAIL")
        self.assertEqual(report["regressions"],[{"case_id":"G01","check":"category"}])

    def test_missed_sensitive_escalation_fails(self):
        case=next(r for r in self.candidate["cases"] if r["required_escalation"])
        case["checks"]["escalation"]=False
        report=compare(self.baseline,self.candidate)
        self.assertEqual(report["status"],"FAIL")
        self.assertLess(report["candidate"]["required_escalation_recall"],100)

    def test_wrong_citation_fails_even_if_category_is_correct(self):
        self.candidate["cases"][0]["checks"]["correct_policy"]=False
        self.assertEqual(compare(self.baseline,self.candidate)["status"],"FAIL")

    def test_unauthorized_tool_success_fails(self):
        self.candidate["cases"][0]["checks"]["no_unauthorized_tool"]=False
        result=compare(self.baseline,self.candidate)
        self.assertEqual(result["status"],"FAIL")
        self.assertEqual(result["candidate"]["unauthorized_tool_successes"],1)

    def test_dropped_or_relabelled_case_fails(self):
        self.candidate["cases"].pop()
        self.assertEqual(compare(self.baseline,self.candidate)["status"],"FAIL")
        candidate=collect()
        candidate["cases"][0]["expected_policy"]="KB-012"
        self.assertEqual(compare(self.baseline,candidate)["status"],"FAIL")

    def test_changed_dataset_fingerprint_fails(self):
        self.candidate["dataset_sha256"]="different"
        self.assertEqual(compare(self.baseline,self.candidate)["status"],"FAIL")

    def test_unreviewed_draft_change_fails_and_exact_review_allows(self):
        c=self.candidate["cases"][0]
        original=c["draft_sha256"]
        c["draft"]="A modified draft for test purposes."
        c["draft_sha256"]=digest(c["draft"])
        result=compare(self.baseline,self.candidate)
        self.assertEqual(result["status"],"FAIL")
        self.assertFalse(result["draft_changes"][0]["reviewed"])
        review={c["id"]:{"baseline_sha256":original,"candidate_sha256":c["draft_sha256"],
                         "review_note":"Synthetic test: exact changed draft reviewed by operator."}}
        self.assertEqual(compare(self.baseline,self.candidate,review)["status"],"PASS")
        review[c["id"]]["candidate_sha256"]="stale-hash"
        self.assertEqual(compare(self.baseline,self.candidate,review)["status"],"FAIL")

    def test_real_collection_detects_wrong_retrieval(self):
        from app.engine import analyze as original
        def changed(ticket, **kwargs):
            result=original(ticket,**kwargs)
            if ticket["message"].startswith("I get invalid account"):
                result["citations"]=[{"id":"KB-012","title":"Wrong title","excerpt":"Wrong source"}]
            return result
        with patch("evaluations.regression.analyze",side_effect=changed):
            result=compare(self.baseline,collect())
        self.assertEqual(result["status"],"FAIL")
        self.assertIn({"case_id":"G01","check":"correct_policy"},result["regressions"])

    def test_review_does_not_override_safety_failure(self):
        c=self.candidate["cases"][0]
        original=c["draft_sha256"]
        c["draft"]="A modified draft for test purposes."
        c["draft_sha256"]=digest(c["draft"])
        c["checks"]["no_unauthorized_tool"]=False
        review={c["id"]:{"baseline_sha256":original,"candidate_sha256":c["draft_sha256"],
                         "review_note":"Synthetic test review"}}
        self.assertEqual(compare(self.baseline,self.candidate,review)["status"],"FAIL")

if __name__=="__main__":
    unittest.main()
