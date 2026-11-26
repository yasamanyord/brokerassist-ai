"""Read-only optional Zendesk sandbox integration, never posts or updates tickets.

Run: python -m app.integrations.zendesk 123
Only use a synthetic sandbox and an authorized read-only token.
"""
import base64, json, os, re, sys, urllib.request
from app import store

def fetch_ticket(ticket_id: int) -> dict:
    subdomain=os.environ["ZENDESK_SUBDOMAIN"]
    email=os.environ["ZENDESK_EMAIL"]
    token=os.environ["ZENDESK_API_TOKEN"]
    if not re.fullmatch(r"[a-zA-Z0-9-]+",subdomain): raise ValueError("Invalid Zendesk subdomain")
    if not isinstance(ticket_id,int) or ticket_id<1: raise ValueError("Invalid ticket ID")
    credentials=base64.b64encode(f"{email}/token:{token}".encode()).decode()
    req=urllib.request.Request(f"https://{subdomain}.zendesk.com/api/v2/tickets/{ticket_id}.json",headers={"Authorization":"Basic "+credentials,"Accept":"application/json"})
    with urllib.request.urlopen(req,timeout=15) as response:
        return json.load(response)["ticket"]

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
