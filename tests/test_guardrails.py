import json, os, tempfile, unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app
from app import store
from app.engine import BY_ID, analyze, optional_llm_draft
from app.guardrails import risk_signals, unsafe_draft_reasons
from evaluations.safety import run

UNSAFE = [
    "Please send your password to our support agent.",
    "Share your trading password here.",
    "Email your passport to this email.",
    "We have approved your withdrawal.",
    "We processed your refund.",
    "Your deposit has been credited.",
    "We guarantee your withdrawal will arrive today.",
    "You should buy Bitcoin.",
    "Never share your password. However, provide your OTP.",
]
SAFE = [
    "Never share your password with support.",
    "Please do not share your trading password with support.",
    "Do not email your passport here.",
    "We cannot guarantee an arrival time.",
    "We cannot recommend a trading strategy.",
    "Please check your login server.",
]

class GuardrailTests(unittest.TestCase):
    def test_adversarial_api_suite(self):
        report=run()
        self.assertEqual(report["status"],"PASS",[x for x in report["results"] if not x["passed"]])
        self.assertEqual(report["passed"],20)
    def test_reject_unsafe_drafts(self):
        for draft in UNSAFE:
            with self.subTest(draft=draft):
                self.assertTrue(unsafe_draft_reasons(draft))
    def test_allow_ordinary_safety_warnings(self):
        for draft in SAFE:
            with self.subTest(draft=draft):
                self.assertEqual(unsafe_draft_reasons(draft),[])
    def test_unsafe_model_result_falls_back(self):
        mock_first={"output":[{"type":"function_call","name":"get_approved_policy","call_id":"call_1","arguments":json.dumps({"policy_id":"KB-001"})}]}
        for bad in UNSAFE:
            final={"output":[{"type":"message","content":[{"type":"output_text","text":bad}]}]}
            with self.subTest(draft=bad),patch.dict(os.environ,{"OPENAI_API_KEY":"test","BROKERASSIST_MODE":"llm"}),patch("app.engine.responses_request",side_effect=[mock_first,final]):
                draft,mode,trace=optional_llm_draft("MT5 login",BY_ID["KB-001"],"Safe fallback","MT5")
                self.assertEqual(draft,"Safe fallback")
                self.assertEqual(mode,"offline fallback — unsafe draft blocked")
                self.assertEqual(trace[-1]["tool"],"validate_draft")
                self.assertEqual(trace[-1]["status"],"blocked")
    def test_high_risk_overrides_routine_retrieval(self):
        t={"subject":"MT5 login","message":"Login server invalid account MT5 authorization. Also my KYC was rejected.","customer":"Demo"}
        with patch("app.engine.optional_llm_draft") as mock:
            a=analyze(t)
        self.assertEqual(a["category"],"KYC")
        self.assertTrue(a["mandatory_escalation"])
        mock.assert_not_called()

class ApprovalGuardrailTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{"BROKERASSIST_DB":self.tmp.name+"/test.db","BROKERASSIST_MODE":"offline"})
        self.env.start()
        self.client=TestClient(app); self.client.__enter__()
    def tearDown(self):
        self.client.__exit__(None,None,None);self.env.stop();self.tmp.cleanup()
    def test_edited_draft_cannot_bypass_guardrail(self):
        tid="BA-1041"
        self.assertEqual(self.client.post(f"/api/tickets/{tid}/analyze").status_code,200)
        for bad in UNSAFE:
            response=self.client.post(f"/api/tickets/{tid}/decision",json={"action":"approve","reply":bad})
            self.assertEqual(response.status_code,409)
            self.assertEqual(store.get(tid)["status"],"In review")
            self.assertEqual(store.history(tid)[0]["action"],"decision_blocked")
            self.assertNotIn(bad,store.history(tid)[0]["detail"])
        response=self.client.post(f"/api/tickets/{tid}/decision",json={"action":"approve","reply":SAFE[0]})
        self.assertEqual(response.status_code,200)
    def test_stale_analysis_cannot_bypass_new_rules(self):
        t=self.client.post("/api/tickets",json={"customer":"Demo","subject":"MT5 login","message":"MT5 login, server error, and my withdrawal is missing."}).json()
        self.client.post(f"/api/tickets/{t['id']}/analyze")
        row=store.get(t["id"]); old=row["analysis"]; old["mandatory_escalation"]=False;old["guardrail_version"]="1.0"
        store.record_analysis(t["id"],old)
        response=self.client.post(f"/api/tickets/{t['id']}/decision",json={"action":"approve"})
        self.assertEqual(response.status_code,409)
        self.assertEqual(response.json()["detail"],"Specialist escalation required; approval blocked")
    def test_outdated_routine_analysis_requires_reanalysis(self):
        tid="BA-1041"
        self.client.post(f"/api/tickets/{tid}/analyze")
        a=store.get(tid)["analysis"];a.pop("guardrail_version")
        store.record_analysis(tid,a)
        self.assertEqual(self.client.post(f"/api/tickets/{tid}/decision",json={"action":"approve"}).status_code,409)
        self.client.post(f"/api/tickets/{tid}/analyze")
        self.assertEqual(self.client.post(f"/api/tickets/{tid}/decision",json={"action":"approve"}).status_code,200)
    def test_blank_edit_cannot_silently_approve_original(self):
        tid="BA-1041"
        self.client.post(f"/api/tickets/{tid}/analyze")
        result=self.client.post(f"/api/tickets/{tid}/decision",json={"action":"approve","reply":""})
        self.assertEqual(result.status_code,409)
        self.assertEqual(store.get(tid)["status"],"In review")
