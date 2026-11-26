"""FastAPI service and same-origin operator interface."""
from contextlib import asynccontextmanager
import os, hmac
from typing import Literal
from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from . import store, hosted
from .engine import analyze, POLICIES, ROOT

@asynccontextmanager
async def lifespan(app):
    if hosted.enabled(): hosted.configuration()
    store.initialize()
    yield

app=FastAPI(title="BrokerAssist AI",version="1.3.0",description="Local synthetic support portfolio demo; no live customer actions.",lifespan=lifespan)
app.middleware("http")(hosted.hosted_access)
app.mount("/static",StaticFiles(directory=ROOT/"app/static"),name="static")

class Intake(BaseModel):
    customer: str = Field(min_length=1,max_length=120)
    channel: Literal["Email","Live chat","Web ticket","CRM"] = "Web ticket"
    subject: str = Field(min_length=1,max_length=180)
    message: str = Field(min_length=1,max_length=5000)
class Webhook(Intake):
    event_id: str = Field(min_length=1,max_length=160)
class Decision(BaseModel):
    action: Literal["approve","escalate"]
    reply: str | None = Field(default=None,max_length=3000)

def required_ticket(id):
    t=store.get(id)
    if not t: raise HTTPException(404,"Ticket not found")
    return t

@app.get("/",include_in_schema=False)
def index(): return FileResponse(ROOT/"app/static/index.html")

@app.get("/api/health")
def health(): return {"status":"ok","demo":True,"mode":"llm-enabled" if os.getenv("BROKERASSIST_MODE")=="llm" and os.getenv("OPENAI_API_KEY") else "offline"}

@app.get("/api/tickets")
def list_tickets(): return store.tickets()

@app.get("/api/metrics")
def metrics(): return store.metrics()

@app.get("/api/knowledge")
def knowledge(): return POLICIES

@app.get("/api/tickets/{ticket_id}")
def ticket(ticket_id:str): return required_ticket(ticket_id)

@app.get("/api/tickets/{ticket_id}/audit")
def audit(ticket_id:str): required_ticket(ticket_id); return store.history(ticket_id)

@app.post("/api/tickets",status_code=201)
def intake(payload:Intake):
    return store.intake(**payload.model_dump())[0]

@app.post("/api/webhooks/ticket")
def webhook(payload:Webhook, x_webhook_secret:str|None=Header(default=None)):
    secret=os.getenv("BROKERASSIST_WEBHOOK_SECRET")
    if not secret: raise HTTPException(503,"Webhook disabled until a secret is configured")
    if not x_webhook_secret or not hmac.compare_digest(x_webhook_secret,secret):
        raise HTTPException(401,"Invalid webhook secret")
    ticket,duplicate=store.intake(**payload.model_dump())
    return {"ticket":ticket,"duplicate":duplicate}

@app.post("/api/tickets/{ticket_id}/analyze")
def process(ticket_id:str):
    ticket=required_ticket(ticket_id)
    if ticket["status"] in ("Approved","Escalated"): raise HTTPException(409,"Ticket already finalized")
    try: return store.record_analysis(ticket_id, analyze(ticket))
    except ValueError as e: raise HTTPException(409,str(e))

@app.post("/api/tickets/{ticket_id}/decision")
def decision(ticket_id:str,payload:Decision):
    required_ticket(ticket_id)
    try: return store.decide(ticket_id,payload.action,payload.reply)
    except ValueError as e: raise HTTPException(409,str(e))
