import os,tempfile,unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app
from app import hosted

class HostedTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{"BROKERASSIST_HOSTED":"yes","BROKERASSIST_MODE":"offline","OPENAI_API_KEY":"",
            "BROKERASSIST_DEMO_USER":"reviewer","BROKERASSIST_DEMO_PASSWORD":"synthetic-long-demo-password",
            "BROKERASSIST_PUBLIC_ORIGIN":"https://demo.example.test","BROKERASSIST_DB":self.tmp.name+"/demo.db"})
        self.env.start()
        self.client=TestClient(app);self.client.__enter__()
        self.auth=("reviewer","synthetic-long-demo-password")
    def tearDown(self):
        self.client.__exit__(None,None,None);self.env.stop();self.tmp.cleanup()
    def test_health_only_is_public(self):
        self.assertEqual(self.client.get("/api/health").status_code,200)
        for path in ("/","/api/tickets","/docs","/openapi.json","/static/app.js"):
            self.assertEqual(self.client.get(path).status_code,401)
            self.assertEqual(self.client.get(path,auth=("reviewer","wrong")).status_code,401)
        self.assertEqual(self.client.get("/",auth=self.auth).status_code,200)
        r=self.client.get("/api/tickets",auth=self.auth)
        self.assertEqual(r.status_code,200);self.assertEqual(r.headers["cache-control"],"no-store")
    def test_json_and_origin_boundary(self):
        url="/api/tickets/BA-1041/analyze"
        self.assertEqual(self.client.post(url,auth=self.auth).status_code,415)
        self.assertEqual(self.client.post(url,auth=self.auth,headers={"Content-Type":"application/json","Origin":"https://other.example.test"}).status_code,403)
        self.assertEqual(self.client.post(url,auth=self.auth,headers={"Content-Type":"application/json","Origin":"https://demo.example.test"}).status_code,200)
    def test_webhooks_disabled(self):
        self.assertEqual(self.client.post("/api/webhooks/ticket",auth=self.auth,json={}).status_code,403)
    def test_no_live_key_or_weak_password(self):
        with patch.dict(os.environ,{"OPENAI_API_KEY":"not-real"}):
            with self.assertRaises(RuntimeError): hosted.configuration()
        with patch.dict(os.environ,{"BROKERASSIST_DEMO_PASSWORD":"weak"}):
            with self.assertRaises(RuntimeError):hosted.configuration()
