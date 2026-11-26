"""Transport limits, evidence-only handoff and aggregate count regression tests."""
import asyncio
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from app import store
from app.main import app
from app.request_limits import WriteBodyLimit, MAX_WRITE_BYTES


class TransportTests(unittest.TestCase):
    def test_chunked_limit_without_length(self):
        async def run():
            downstream_called = False
            async def downstream(scope, receive, send):
                nonlocal downstream_called
                downstream_called = True
            messages = iter([
                {"type": "http.request", "body": b"a" * MAX_WRITE_BYTES, "more_body": True},
                {"type": "http.request", "body": b"b", "more_body": False},
            ])
            async def receive():
                return next(messages)
            sent = []
            async def send(message):
                sent.append(message)
            await WriteBodyLimit(downstream)(
                {"type": "http", "method": "POST", "path": "/api/tickets", "headers": []},
                receive, send,
            )
            self.assertFalse(downstream_called)
            self.assertEqual(sent[0]["status"], 413)
        asyncio.run(run())

    def test_lying_length_still_rejected(self):
        async def run():
            async def downstream(*args):
                self.fail("Over-limit body reached JSON handler")
            async def receive():
                return {"type": "http.request", "body": b"x" * (MAX_WRITE_BYTES + 1), "more_body": False}
            sent = []
            async def send(message):
                sent.append(message)
            await WriteBodyLimit(downstream)(
                {"type": "http", "method": "POST", "path": "/api/tickets",
                 "headers": [(b"content-length", b"1")]}, receive, send,
            )
            self.assertEqual(sent[0]["status"], 413)
        asyncio.run(run())


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = patch.dict(os.environ, {
            "BROKERASSIST_DB": self.tmp.name + "/test.db", "BROKERASSIST_MODE": "offline",
            "BROKERASSIST_PILOT": "", "BROKERASSIST_HOSTED": "", "RENDER": "",
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.client = self.enterContext(TestClient(app))

    def test_over_limit_has_no_side_effect(self):
        before = store.metrics()
        reply = self.client.post("/api/tickets", content=b" " * (MAX_WRITE_BYTES + 1),
                                 headers={"Content-Type": "application/json"})
        self.assertEqual(reply.status_code, 413)
        self.assertEqual(store.metrics(), before)

    def test_normal_request_and_validation_preserved(self):
        payload = {"customer": "Synthetic user", "subject": "MT5 login", "message": "Invalid account"}
        self.assertEqual(self.client.post("/api/tickets", json=payload).status_code, 201)
        self.assertEqual(self.client.post("/api/tickets", json={**payload, "message": "x" * 5001}).status_code, 422)

    def test_handoff_only_after_finalized_escalation(self):
        path = "/api/tickets/BA-1042"
        self.assertEqual(self.client.get(path + "/handoff").status_code, 409)
        response = self.client.post(path + "/analyze").json()
        self.assertEqual(self.client.get(path + "/handoff").status_code, 409)
        self.assertEqual(self.client.post(path + "/decision", json={"action": "escalate"}).status_code, 200)
        handoff = self.client.get(path + "/handoff").json()
        self.assertEqual(handoff["ticket_id"], "BA-1042")
        self.assertEqual(handoff["recommended_team"], "Finance")
        self.assertEqual(handoff["policy_ids"], ["KB-002"])
        self.assertEqual(handoff["tool_attempts"], [{"tool": "lookup_transaction", "status": "ok", "simulated": True}])
        self.assertEqual(handoff["analysis_revision"], response["analysis_revision"])
        self.assertEqual(handoff["delivery_status"], "local_only_not_sent")
        self.assertEqual(handoff["recorded_by"], "local-demo")
        self.assertNotIn("customer", handoff)
        self.assertNotIn("message", handoff)
        self.assertNotIn("state", handoff["tool_attempts"][0])
        self.assertEqual(self.client.get(path + "/handoff").json(), handoff)
        self.assertEqual(self.client.get("/api/tickets/unknown/handoff").status_code, 404)

    def test_approved_ticket_never_has_handoff(self):
        path = "/api/tickets/BA-1041"
        self.client.post(path + "/analyze")
        self.assertEqual(self.client.post(path + "/decision", json={"action": "approve"}).status_code, 200)
        self.assertEqual(self.client.get(path + "/handoff").status_code, 409)

    def test_metrics_do_not_materialize_ticket_records(self):
        self.client.post("/api/tickets/BA-1041/analyze")
        self.client.post("/api/tickets/BA-1041/decision", json={"action": "approve"})
        self.client.post("/api/tickets/BA-1042/analyze")
        self.client.post("/api/tickets/BA-1042/decision", json={"action": "escalate"})
        with patch("app.store.tickets", side_effect=AssertionError("Loaded ticket messages")):
            self.assertEqual(self.client.get("/api/metrics").json(), {
                "total": 8, "new": 6, "review": 0, "approved": 1, "escalated": 1, "analyzed": 2,
            })
