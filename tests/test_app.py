import json, os, tempfile, unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app
from app import store
from app.engine import analyze,lookup_transaction,redact, retrieve, optional_llm_draft,BY_ID
from app.integrations.zendesk import normalize
from evaluations.run import run

class EngineTests(unittest.TestCase):
    def test_golden_dataset(self):
        self.assertEqual(run()["summary"]["passed"],50)
    def test_retrieval(self):
        self.assertEqual(retrieve("MT5 invalid account")[0]["id"],"KB-001")
    def test_unknown(self):
        self.assertEqual(analyze({"subject":"","message":"Hello","customer":"Test"},False)["category"],"General")
    def test_authorized_transaction(self):
        query={"customer":"Alex Morgan","verified":True,"transaction_ref":"TX-2001","message":"My deposit TX-2001"}
        self.assertEqual(lookup_transaction(query)["status"],"ok")
    def test_unverified_and_mismatch_blocked(self):
        for fields in [{"verified":False},{"customer":"Not Alex"},{"message":"Other reference"}]:
            query={"customer":"Alex Morgan","verified":True,"transaction_ref":"TX-2001","message":"My deposit TX-2001",**fields}
            self.assertEqual(lookup_transaction(query)["status"],"blocked")
    def test_redaction(self):
        sample=redact("My email is guest@example.test, password: secret12 otp=123456 card 4111 1111 1111 1111")
        for term in ["guest@example.test","secret12","123456","4111"]: self.assertNotIn(term,sample)
    def test_llm_not_called_on_sensitive(self):
        with patch("app.engine.optional_llm_draft") as mock:
            analyze({"subject":"Withdrawal","message":"Pending withdrawal","customer":"Test"})
            mock.assert_not_called()
    def test_llm_tool_roundtrip_with_mock(self):
        first={"output":[{"type":"function_call","name":"get_approved_policy","call_id":"call_1","arguments":json.dumps({"policy_id":"KB-001"})}]}
        final={"output":[{"type":"message","content":[{"type":"output_text","text":"Please verify your trading server."}]}]}
        with patch.dict(os.environ,{"OPENAI_API_KEY":"test","BROKERASSIST_MODE":"llm"}),patch("app.engine.responses_request",side_effect=[first,final]) as provider:
            draft,mode,trace=optional_llm_draft("MT5 login",BY_ID["KB-001"],"Fallback","MT5")
            self.assertEqual(draft,"Please verify your trading server.")
            self.assertEqual(trace[0]["reference"],"KB-001")
            self.assertEqual(provider.call_args_list[1].args[0]["input"][-1]["call_id"],"call_1")
    def test_llm_unauthorized_tool_scope(self):
        output={"output":[{"type":"function_call","name":"get_approved_policy","call_id":"call_1","arguments":json.dumps({"policy_id":"KB-010"})}]}
        with patch.dict(os.environ,{"OPENAI_API_KEY":"test","BROKERASSIST_MODE":"llm"}),patch("app.engine.responses_request",return_value=output) as provider:
            draft,mode,trace=optional_llm_draft("MT5 login",BY_ID["KB-001"],"Fallback","MT5")
            self.assertEqual(draft,"Fallback");self.assertEqual(trace[0]["status"],"blocked");self.assertEqual(provider.call_count,1)
    def test_llm_failure_safe_fallback(self):
        with patch.dict(os.environ,{"OPENAI_API_KEY":"test","BROKERASSIST_MODE":"llm"}),patch("app.engine.responses_request",side_effect=TimeoutError):
            draft,mode,trace=optional_llm_draft("MT5 login",BY_ID["KB-001"],"Fallback","MT5")
            self.assertEqual(draft,"Fallback");self.assertIn("fallback",mode)
    def test_zendesk_normalize(self):
        normalized=normalize({"id":42,"requester_id":99,"subject":"Demo","description":"A ticket"})
        self.assertEqual(normalized["event_id"],"zendesk-ticket-42")
        self.assertEqual(normalized["channel"],"CRM")
        self.assertNotIn("verified",normalized)

class ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{"BROKERASSIST_DB":self.tmp.name+"/test.db","BROKERASSIST_MODE":"offline","BROKERASSIST_WEBHOOK_SECRET":"test-secret"})
        self.env.start()
        self.client=TestClient(app);self.client.__enter__()
    def tearDown(self):
        self.client.__exit__(None,None,None);self.env.stop();self.tmp.cleanup()
    def test_health_and_frontend(self):
        self.assertEqual(self.client.get("/api/health").json()["status"],"ok")
        self.assertEqual(self.client.get("/").status_code,200)
        self.assertEqual(self.client.get("/static/app.js").status_code,200)
        self.assertEqual(len(self.client.get("/api/knowledge").json()),12)
    def test_seed_and_metrics(self):
        self.assertEqual(self.client.get("/api/metrics").json()["total"],8)
        self.assertEqual(self.client.get("/api/tickets").json()[0]["id"],"BA-1042")
    def test_approve_routine_and_audit(self):
        ticket="BA-1041"
        self.assertEqual(self.client.post(f"/api/tickets/{ticket}/decision",json={"action":"approve"}).status_code,409)
        analysis=self.client.post(f"/api/tickets/{ticket}/analyze").json()
        self.assertEqual(analysis["analysis"]["category"],"MT5")
        response=self.client.post(f"/api/tickets/{ticket}/decision",json={"action":"approve","reply":"Reviewed by operator."})
        self.assertEqual(response.json()["status"],"Approved")
        self.assertEqual(response.json()["final_reply"],"Reviewed by operator.")
        self.assertEqual(self.client.get(f"/api/tickets/{ticket}/audit").json()[0]["action"],"approved")
        self.assertEqual(self.client.post(f"/api/tickets/{ticket}/analyze").status_code,409)
    def test_sensitive_approval_blocked_server_side(self):
        ticket="BA-1042"
        analysis=self.client.post(f"/api/tickets/{ticket}/analyze").json()["analysis"]
        self.assertTrue(analysis["mandatory_escalation"])
        self.assertEqual(analysis["tool_calls"][0]["status"],"ok")
        self.assertEqual(self.client.post(f"/api/tickets/{ticket}/decision",json={"action":"approve"}).status_code,409)
        self.assertEqual(self.client.post(f"/api/tickets/{ticket}/decision",json={"action":"escalate"}).json()["status"],"Escalated")
    def test_intake_does_not_trust_customer_verification(self):
        response=self.client.post("/api/tickets",json={"customer":"Alex Morgan","subject":"Deposit","message":"TX-2001; email test@example.com","verified":True,"transaction_ref":"TX-2001"})
        self.assertEqual(response.status_code,201)
        t=response.json();self.assertFalse(t["verified"]);self.assertNotIn("test@example.com",t["message"])
        result=self.client.post(f"/api/tickets/{t['id']}/analyze").json()
        self.assertEqual(result["analysis"]["tool_calls"][0]["status"],"blocked")
    def test_webhook_secret_and_idempotency(self):
        payload={"customer":"Test","subject":"Test","message":"Hello","channel":"CRM","event_id":"unique-event-1"}
        self.assertEqual(self.client.post("/api/webhooks/ticket",json=payload).status_code,401)
        one=self.client.post("/api/webhooks/ticket",json=payload,headers={"X-Webhook-Secret":"test-secret"}).json()
        two=self.client.post("/api/webhooks/ticket",json=payload,headers={"X-Webhook-Secret":"test-secret"}).json()
        self.assertFalse(one["duplicate"]);self.assertTrue(two["duplicate"]);self.assertEqual(one["ticket"]["id"],two["ticket"]["id"])
        self.assertEqual(self.client.get("/api/metrics").json()["total"],9)
    def test_webhook_disabled_without_secret(self):
        with patch.dict(os.environ,{"BROKERASSIST_WEBHOOK_SECRET":""}):
            response=self.client.post("/api/webhooks/ticket",json={"customer":"Test","subject":"Test","message":"Hello","event_id":"x"})
            self.assertEqual(response.status_code,503)
    def test_validation_and_missing_ticket(self):
        self.assertEqual(self.client.get("/api/tickets/unknown").status_code,404)
        self.assertEqual(self.client.post("/api/tickets",json={"customer":"","subject":"","message":""}).status_code,422)
    def test_persistence_across_connection(self):
        t=self.client.post("/api/tickets",json={"customer":"Demo","subject":"Help","message":"Hello"}).json()
        self.assertEqual(store.get(t["id"])["subject"],"Help")

if __name__=="__main__": unittest.main()
