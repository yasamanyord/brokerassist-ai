"""Read-only synthetic Zendesk sandbox importer using OAuth.

Run: python -m app.integrations.zendesk TICKET_ID
Use a tickets:read OAuth client in a sandbox you control. No write calls.
"""
import base64, json, os, re, sys, urllib.request
from app import store

class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Do not forward authorization to a redirected destination."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def request_json(req):
    with urllib.request.build_opener(NoRedirect()).open(req,timeout=15) as response:
        return json.load(response)

def base_url():
    subdomain=os.environ["ZENDESK_SUBDOMAIN"]
    if not re.fullmatch(r"[a-zA-Z0-9-]+",subdomain): raise ValueError("Invalid Zendesk subdomain")
    return f"https://{subdomain}.zendesk.com"

def token_header(base):
    if os.getenv("ZENDESK_ACCESS_TOKEN"):
        return "Bearer "+os.environ["ZENDESK_ACCESS_TOKEN"]
    if os.getenv("ZENDESK_CLIENT_ID") and os.getenv("ZENDESK_CLIENT_SECRET"):
        payload={"grant_type":"client_credentials","client_id":os.environ["ZENDESK_CLIENT_ID"],
                 "client_secret":os.environ["ZENDESK_CLIENT_SECRET"],"scope":"tickets:read"}
        req=urllib.request.Request(base+"/oauth/tokens",data=json.dumps(payload).encode(),headers={"Content-Type":"application/json","Accept":"application/json"},method="POST")
        data=request_json(req)
        if not data.get("access_token") or data.get("token_type","bearer").lower()!="bearer":
            raise ValueError("Invalid OAuth token response")
        if set(data.get("scope","").split())!={"tickets:read"}:
            raise ValueError("OAuth response did not confirm the exact tickets:read scope")
        return "Bearer "+data["access_token"]
    # Backward compatibility only for existing active legacy credentials.
    if os.getenv("ZENDESK_EMAIL") and os.getenv("ZENDESK_API_TOKEN"):
        credentials=base64.b64encode(f"{os.environ['ZENDESK_EMAIL']}/token:{os.environ['ZENDESK_API_TOKEN']}".encode()).decode()
        return "Basic "+credentials
    raise ValueError("Configure read-only Zendesk OAuth credentials")

def fetch_ticket(ticket_id: int) -> dict:
    if not isinstance(ticket_id,int) or ticket_id<1: raise ValueError("Invalid ticket ID")
    base=base_url()
    req=urllib.request.Request(f"{base}/api/v2/tickets/{ticket_id}.json",headers={"Authorization":token_header(base),"Accept":"application/json"},method="GET")
    data=request_json(req)["ticket"]
    if data.get("id")!=ticket_id: raise ValueError("Unexpected ticket ID")
    return data

def normalize(ticket: dict) -> dict:
    return {"customer":"Sandbox requester "+str(ticket.get("requester_id","unknown")),
            "channel":"CRM","subject":str(ticket.get("subject") or "Zendesk ticket")[:180],
            "message":str(ticket.get("description") or "No description")[:5000],
            "event_id":"zendesk-ticket-"+str(ticket["id"])}

def ingest(ticket_id:int):
    store.initialize()
    return store.intake(**normalize(fetch_ticket(ticket_id)))

if __name__=="__main__":
    if os.getenv("ALLOW_ZENDESK_SANDBOX")!="yes":
        sys.exit("Set ALLOW_ZENDESK_SANDBOX=yes only for a synthetic, authorized sandbox.")
    if len(sys.argv)!=2: sys.exit("Usage: python -m app.integrations.zendesk TICKET_ID")
    try:
        ticket,duplicate=ingest(int(sys.argv[1]))
        print(json.dumps({"local_ticket_id":ticket["id"],"duplicate":duplicate}))
    except Exception:
        sys.exit("Sandbox import failed. Check credentials, permissions, and ticket ID.")
