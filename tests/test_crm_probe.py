import json, os, unittest
from unittest.mock import patch
from app.integrations import zendesk
from evaluations.crm_probe import probe, EXPECTED_SUBJECT, EXPECTED_MESSAGE

class CRMProbeTests(unittest.TestCase):
    def test_oauth_get_and_deduplication(self):
        remote={"id":123,"requester_id":5,"subject":EXPECTED_SUBJECT,"description":EXPECTED_MESSAGE}
        env={"ZENDESK_SUBDOMAIN":"synthetic-sandbox","ZENDESK_CLIENT_ID":"mock-id","ZENDESK_CLIENT_SECRET":"mock-secret","ZENDESK_ACCESS_TOKEN":""}
        with patch.dict(os.environ,env),patch.object(zendesk,"request_json",side_effect=[{"access_token":"mock-token","token_type":"bearer","scope":"tickets:read"},{"ticket":remote}]) as transport:
            report=probe(123)
        self.assertEqual(report["status"],"PASS")
        token_req=transport.call_args_list[0].args[0]
        self.assertEqual(token_req.get_method(),"POST")
        self.assertEqual(json.loads(token_req.data)["scope"],"tickets:read")
        req=transport.call_args_list[1].args[0]
        self.assertEqual(req.get_method(),"GET");self.assertEqual(req.get_header("Authorization"),"Bearer mock-token")
        self.assertNotIn(EXPECTED_MESSAGE,json.dumps(report))
    def test_no_import_of_other_ticket(self):
        with patch.object(zendesk,"fetch_ticket",return_value={"id":123,"subject":"Other","description":"Unapproved content"}):
            with self.assertRaises(ValueError):probe(123)
    def test_oauth_rejects_excess_scope(self):
        with patch.dict(os.environ,{"ZENDESK_SUBDOMAIN":"sandbox","ZENDESK_CLIENT_ID":"mock-id","ZENDESK_CLIENT_SECRET":"mock-secret","ZENDESK_ACCESS_TOKEN":""}),patch.object(zendesk,"request_json",return_value={"access_token":"mock-token","scope":"read write"}) as transport:
            with self.assertRaises(ValueError):zendesk.fetch_ticket(123)
            self.assertEqual(transport.call_count,1)
    def test_reject_wrong_id(self):
        with patch.dict(os.environ,{"ZENDESK_SUBDOMAIN":"sandbox","ZENDESK_ACCESS_TOKEN":"mock-token"}),patch.object(zendesk,"request_json",return_value={"ticket":{"id":999}}):
            with self.assertRaises(ValueError):zendesk.fetch_ticket(123)
