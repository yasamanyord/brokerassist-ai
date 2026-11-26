"""Company pilot integration, identity, isolation, failure and concurrency tests.
All fixtures are fictional, including the approval metadata; no network access.
"""
import base64,json,os,sqlite3,tempfile,time,unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from app import engine, pilot, store
from app.main import app
from app.backup import backup

PASSWORD="fictional-test-password-12345"
SECRET="synthetic-signing-secret-0123456789"
DATA={"customer":"Fictional operator test","channel":"CRM","subject":"MT5 invalid account","message":"How do I select my MT5 server?"}
def authorization(name,password=PASSWORD):
    return {"Authorization":"Basic "+base64.b64encode(f"{name}:{password}".encode()).decode()}

class PilotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.users=[pilot.user_record(n,r,PASSWORD) for n,r in [("alice","admin"),("bob","operator"),("carol","viewer")]]

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.db=self.root/"pilot.db"
        self.knowledge=self.root/"approved.json";self.users_file=self.root/"users.json"
        self.doc={"client_id":"test-company","approved":True,"approved_by":"fictional approver","approved_at":"2026-01-01","version":"test-1","policies":json.loads((engine.ROOT/"data/knowledge.json").read_text())}
        self.knowledge.write_text(json.dumps(self.doc));self.users_file.write_text(json.dumps(self.users))
        self.env=patch.dict(os.environ,{"BROKERASSIST_PILOT":"yes","BROKERASSIST_CLIENT_ID":"test-company","BROKERASSIST_DB":str(self.db),"BROKERASSIST_PILOT_USERS_FILE":str(self.users_file),"BROKERASSIST_PILOT_KNOWLEDGE_FILE":str(self.knowledge),"BROKERASSIST_PUBLIC_ORIGIN":"https://pilot.example.test","BROKERASSIST_MODE":"offline","BROKERASSIST_SIGNING_SECRET":SECRET,"BROKERASSIST_DAILY_PROVIDER_CALLS":"3","OPENAI_API_KEY":"","BROKERASSIST_HOSTED":"","RENDER":""})
        self.env.start();self.addCleanup(self.env.stop)
        self.operator=authorization("bob");self.admin=authorization("alice");self.viewer=authorization("carol")

    def intake(self,c,data=None):
        r=c.post("/api/tickets",json=data or DATA,headers=self.operator);self.assertEqual(r.status_code,201,r.text);return r.json()
    def analyzed(self,c,data=None):
        t=self.intake(c,data);r=c.post("/api/tickets/"+t["id"]+"/analyze",json={},headers=self.operator);self.assertEqual(r.status_code,200,r.text);return r.json()
    def decision(self,c,t,action="approve",**body):
        return c.post("/api/tickets/"+t["id"]+"/decision",json={"action":action,"analysis_revision":t["analysis_revision"],**body},headers=self.operator)
    def event(self,c,data=None,stamp=None,signature=None):
        body=json.dumps(data or {**DATA,"event_id":"evt-1"}).encode();stamp=str(int(time.time()) if stamp is None else stamp)
        return c.post("/api/webhooks/signed",content=body,headers={"Content-Type":"application/json","X-BrokerAssist-Timestamp":stamp,"X-BrokerAssist-Signature":signature if signature is not None else pilot.sign_event(SECRET,stamp,body)})

    def test_pilot_empty_and_authenticated(self):
        with TestClient(app) as c:
            self.assertEqual(c.get("/api/health").json(),{"status":"ok","demo":False,"mode":"pilot"})
            for path in ("/","/docs","/openapi.json","/static/app.js","/api/tickets","/api/knowledge","/api/metrics","/api/ops"):
                self.assertEqual(c.get(path).status_code,401,path)
            self.assertEqual(c.get("/api/tickets",headers=authorization("bob","wrong")).status_code,401)
            r=c.get("/api/tickets",headers=self.operator);self.assertEqual(r.json(),[]);self.assertEqual(r.headers["Cache-Control"],"no-store")
            self.assertEqual(c.get("/api/session",headers=self.operator).json(),{"pilot":True,"client":"test-company","name":"bob","role":"operator"})

    def test_read_only_viewer_and_admin_operations(self):
        with TestClient(app) as c:
            t=self.intake(c)
            self.assertEqual(c.get("/api/tickets",headers=self.viewer).status_code,200)
            for path,body in [("/api/tickets",DATA),("/api/tickets/"+t["id"]+"/analyze",{}),("/api/tickets/"+t["id"]+"/decision",{"action":"approve"})]:
                self.assertEqual(c.post(path,json=body,headers=self.viewer).status_code,403)
            self.assertEqual(c.get("/api/ops",headers=self.operator).status_code,403)
            self.assertEqual(c.get("/api/ops",headers=self.admin).status_code,200)

    def test_actor_and_revision_audit(self):
        with TestClient(app) as c:
            t=self.analyzed(c);self.assertEqual(t["analysis_revision"],1)
            self.assertEqual(self.decision(c,t).status_code,200)
            rows=c.get("/api/tickets/"+t["id"]+"/audit",headers=self.viewer).json()
            self.assertEqual([r["action"] for r in rows],["approved","analyzed","received"])
            self.assertEqual({r["actor"] for r in rows},{"bob"})

    def test_handoff_protected_and_named(self):
        with TestClient(app) as c:
            t=self.analyzed(c,{**DATA,"subject":"Withdrawal","message":"Could you check my withdrawal?"})
            self.assertEqual(self.decision(c,t,"escalate").status_code,200)
            path="/api/tickets/"+t["id"]+"/handoff"
            self.assertEqual(c.get(path).status_code,401)
            response=c.get(path,headers=self.viewer)
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.json()["recorded_by"],"bob")
            self.assertEqual(response.json()["delivery_status"],"local_only_not_sent")
            self.assertEqual(response.json()["tool_attempts"][0]["status"],"blocked")

    def test_origin_and_content_type(self):
        with TestClient(app) as c:
            self.assertEqual(c.post("/api/tickets",json=DATA,headers={**self.operator,"Origin":"https://evil.example"}).status_code,403)
            self.assertEqual(c.post("/api/tickets",data=DATA,headers=self.operator).status_code,415)
            self.assertEqual(c.post("/api/tickets",json=DATA,headers={**self.operator,"Origin":"https://pilot.example.test"}).status_code,201)

    def test_missing_or_stale_revision_blocks(self):
        with TestClient(app) as c:
            t=self.analyzed(c)
            self.assertEqual(c.post("/api/tickets/"+t["id"]+"/decision",json={"action":"approve"},headers=self.operator).status_code,409)
            updated=c.post("/api/tickets/"+t["id"]+"/analyze",json={},headers=self.operator).json()
            self.assertEqual(self.decision(c,t).status_code,409)
            self.assertEqual(self.decision(c,updated).status_code,200)

    def test_concurrent_approval_only_once(self):
        with TestClient(app) as c:
            t=self.analyzed(c)
            with ThreadPoolExecutor(max_workers=2) as ex:
                results=list(ex.map(lambda _:self.decision(c,t).status_code,range(2)))
            self.assertEqual(sorted(results),[200,409])
            self.assertEqual(sum(r["action"]=="approved" for r in store.history(t["id"])),1)

    def test_concurrent_analysis_cannot_overwrite_newer_revision(self):
        with TestClient(app) as c:
            t=self.intake(c);a=engine.analyze(t)
            store.record_analysis(t["id"],a,actor="bob",expected_revision=0)
            with self.assertRaisesRegex(ValueError,"changed"):store.record_analysis(t["id"],a,expected_revision=0)

    def test_sensitive_and_unknown_fail_closed(self):
        with TestClient(app) as c:
            t=self.analyzed(c,{**DATA,"subject":"Withdrawal","message":"Please release withdrawal TX-2002.","verified":True,"transaction_ref":"TX-2002"})
            self.assertFalse(t["verified"]);self.assertTrue(t["analysis"]["mandatory_escalation"])
            self.assertEqual(t["analysis"]["tool_calls"][0]["status"],"blocked")
            self.assertEqual(self.decision(c,t).status_code,409)
            self.assertEqual(self.decision(c,t,"escalate").status_code,200)
            u=self.analyzed(c,{**DATA,"subject":"Unclear","message":"Hello there"})
            self.assertTrue(u["analysis"]["mandatory_escalation"]);self.assertEqual(self.decision(c,u).status_code,409)

    def test_draft_safety_after_analysis(self):
        with TestClient(app) as c:
            t=self.analyzed(c);self.assertEqual(self.decision(c,t,reply="Please send your password here.").status_code,409)
            self.assertEqual(store.get(t["id"])["status"],"In review")
            self.assertEqual(self.decision(c,t).status_code,200)

    def test_required_approval_and_client_match(self):
        for changes in ({"approved":False},{"client_id":"other-company"},{"approved_by":""},{"policies":[]}):
            self.knowledge.write_text(json.dumps({**self.doc,**changes}))
            with self.assertRaises(RuntimeError):
                with TestClient(app):pass

    def test_unapproved_policy_reply_rejected(self):
        self.doc["policies"][0]["reply"]="Please send your password here."
        self.knowledge.write_text(json.dumps(self.doc))
        with self.assertRaises(RuntimeError):
            with TestClient(app):pass

    def test_policy_revision_change_requires_reanalysis(self):
        with TestClient(app) as c:t=self.analyzed(c)
        self.doc["version"]="test-2";self.knowledge.write_text(json.dumps(self.doc))
        with TestClient(app) as c:
            self.assertEqual(self.decision(c,t).status_code,409)
            self.assertEqual(c.get("/api/tickets/"+t["id"],headers=self.operator).json()["status"],"In review")

    def test_reject_other_company_database(self):
        with TestClient(app) as c:self.intake(c)
        self.doc["client_id"]="other-company";self.knowledge.write_text(json.dumps(self.doc))
        with patch.dict(os.environ,{"BROKERASSIST_CLIENT_ID":"other-company"}):
            with self.assertRaisesRegex(RuntimeError,"different deployment"):
                with TestClient(app):pass

    def test_reject_demo_database_in_pilot(self):
        with patch.dict(os.environ,{"BROKERASSIST_PILOT":""}):
            with TestClient(app):pass
        with self.assertRaises(RuntimeError):
            with TestClient(app):pass

    def test_demo_cannot_read_pilot_database(self):
        with TestClient(app) as c:self.intake(c)
        with patch.dict(os.environ,{"BROKERASSIST_PILOT":""}):
            with self.assertRaises(RuntimeError):
                with TestClient(app):pass

    def test_signed_intake_replay_and_collision(self):
        with TestClient(app) as c:
            first=self.event(c);self.assertEqual(first.status_code,200);self.assertFalse(first.json()["duplicate"])
            retry=self.event(c);self.assertEqual(retry.json(),{"id":first.json()["id"],"duplicate":True})
            self.assertEqual(self.event(c,{**DATA,"event_id":"evt-1","message":"Changed content"}).status_code,409)
            self.assertEqual(len(store.tickets()),1);self.assertEqual(store.history(first.json()["id"])[0]["actor"],"integration:signed")

    def test_webhook_invalid_signature_expiry_and_size(self):
        with TestClient(app) as c:
            self.assertEqual(self.event(c,signature="0"*64).status_code,401)
            self.assertEqual(self.event(c,stamp=int(time.time())-301).status_code,401)
            self.assertEqual(self.event(c,stamp=int(time.time())+301).status_code,401)
            self.assertEqual(self.event(c,{**DATA,"event_id":"evt-1","message":"x"*17000}).status_code,413)
            self.assertEqual(self.event(c,{"event_id":"bad"}).status_code,422)
            self.assertEqual(c.post("/api/webhooks/ticket",json={**DATA,"event_id":"evt-1"},headers=self.operator).status_code,403)
            self.assertEqual(store.tickets(),[])

    def test_webhook_requires_secret(self):
        with patch.dict(os.environ,{"BROKERASSIST_SIGNING_SECRET":""}):
            with TestClient(app) as c:self.assertEqual(self.event(c).status_code,401)

    def test_concurrent_provider_quota_is_atomic(self):
        with TestClient(app) as c:
            with ThreadPoolExecutor(max_workers=8) as ex:results=list(ex.map(lambda _:store.reserve_provider_request(),range(8)))
            self.assertEqual(sum(results),3);self.assertFalse(store.reserve_provider_request())
            self.assertEqual(c.get("/api/ops",headers=self.admin).json()["provider_calls"],3)
        with TestClient(app):self.assertFalse(store.reserve_provider_request())

    def test_no_unapproved_llm_startup(self):
        with patch.dict(os.environ,{"BROKERASSIST_MODE":"llm","OPENAI_API_KEY":"fake","BROKERASSIST_PILOT_LLM_APPROVED":""}):
            with self.assertRaises(RuntimeError):
                with TestClient(app):pass
        with patch.dict(os.environ,{"OPENAI_API_KEY":"fake"}):
            with self.assertRaises(RuntimeError):
                with TestClient(app):pass

    def test_backup_integrity_and_restart(self):
        with TestClient(app) as c:
            t=self.analyzed(c);self.assertEqual(self.decision(c,t).status_code,200)
            dest=backup(self.db,self.root/"copy.db")
            with self.assertRaises(FileExistsError):backup(self.db,dest)
        with TestClient(app) as c:self.assertEqual(c.get("/api/tickets/"+t["id"],headers=self.operator).json()["status"],"Approved")
        with patch.dict(os.environ,{"BROKERASSIST_DB":str(dest)}):
            with TestClient(app) as c:self.assertEqual(c.get("/api/tickets/"+t["id"],headers=self.admin).json()["status"],"Approved")

    def test_error_does_not_echo_private_input(self):
        with TestClient(app) as c:
            r=c.post("/api/tickets",json={**DATA,"channel":"PRIVATE-MARKER"},headers=self.operator)
            self.assertEqual(r.status_code,422);self.assertNotIn("PRIVATE-MARKER",r.text)

    def test_weak_configuration_rejected(self):
        for changes in ({"BROKERASSIST_PUBLIC_ORIGIN":"http://example.test"},{"BROKERASSIST_DB":"relative.db"},{"BROKERASSIST_SIGNING_SECRET":"weak"},{"BROKERASSIST_HOSTED":"yes"}):
            with patch.dict(os.environ,changes):
                with self.assertRaises(RuntimeError):
                    with TestClient(app):pass

    def test_provider_quota_falls_back_and_sensitive_bypasses_network(self):
        # Exercise the actual reservation path but replace outbound HTTP with a fake response.
        import io
        from evaluations.llm_probe import fake_responses
        class FakeOpener:
            def open(self,request,timeout):
                return io.BytesIO(json.dumps(fake_responses(json.loads(request.data),"mock")).encode())
        with patch.dict(os.environ,{"BROKERASSIST_MODE":"llm","OPENAI_API_KEY":"fake","BROKERASSIST_PILOT_LLM_APPROVED":"yes","BROKERASSIST_DAILY_PROVIDER_CALLS":"2"}):
            with patch("app.engine.urllib.request.build_opener",return_value=FakeOpener()) as outbound:
                with TestClient(app) as c:
                    safe=self.analyzed(c);self.assertEqual(safe["analysis"]["mode"],"LLM draft — review required")
                    other=self.analyzed(c);self.assertIn("offline fallback",other["analysis"]["mode"])
                    sensitive=self.analyzed(c,{**DATA,"subject":"Deposit","message":"My deposit has not been credited"})
                    self.assertTrue(sensitive["analysis"]["mandatory_escalation"])
                    self.assertEqual(outbound.call_count,2)
                    self.assertEqual(store.ops()["provider_calls"],2)

    def test_sandbox_adapter_cannot_write_to_pilot(self):
        from app.integrations.zendesk import ingest
        with TestClient(app):
            with patch("app.integrations.zendesk.fetch_ticket") as fetch:
                with self.assertRaises(RuntimeError):ingest(1)
                fetch.assert_not_called()
            self.assertEqual(store.tickets(),[])

    def test_blank_intake_and_event_ids_rejected(self):
        with TestClient(app) as c:
            self.assertEqual(c.post("/api/tickets",headers=self.operator,json={**DATA,"message":"  "}).status_code,422)
            self.assertEqual(self.event(c,{**DATA,"event_id":"   "}).status_code,422)
            self.assertEqual(store.tickets(),[])
