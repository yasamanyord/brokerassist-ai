"""FastAPI service and same-origin operator interface."""
from contextlib import asynccontextmanager
import os, hmac
from typing import Literal
from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError, ConfigDict
from starlette.concurrency import run_in_threadpool
from . import store, hosted, pilot, engine, handoff
from .request_limits import WriteBodyLimit
from .engine import analyze, POLICIES, ROOT

@asynccontextmanager
async def lifespan(app):
    cfg=pilot.configuration() if pilot.enabled() else None
    if hosted.enabled() and not cfg: hosted.configuration()
    engine.configure_knowledge(cfg)
    app.state.pilot_config=cfg
    try:
        store.initialize()
        yield
    finally:
        app.state.pilot_config=None
        engine.configure_knowledge()

app=FastAPI(title="BrokerAssist AI",version="2.0.0",description="Synthetic demo or restricted company pilot; no automated customer actions.",lifespan=lifespan)
app.middleware("http")(hosted.hosted_access)
app.middleware("http")(pilot.access)
app.add_middleware(WriteBodyLimit)
app.mount("/static",StaticFiles(directory=ROOT/"app/static"),name="static")

@app.exception_handler(RequestValidationError)
async def validation_error(request,exc):
    # Never reflect private request values in validation errors.
    return JSONResponse({"detail":"Invalid request; check required fields and limits"},status_code=422)

class Intake(BaseModel):
    model_config=ConfigDict(str_strip_whitespace=True)
    customer: str = Field(min_length=1,max_length=120)
    channel: Literal["Email","Live chat","Web ticket","CRM"] = "Web ticket"
    subject: str = Field(min_length=1,max_length=180)
    message: str = Field(min_length=1,max_length=5000)
class Webhook(Intake):
    event_id: str = Field(min_length=1,max_length=160)
class Decision(BaseModel):
    action: Literal["approve","escalate"]
    reply: str | None = Field(default=None,max_length=3000)
    analysis_revision: int | None = Field(default=None,ge=0)

def actor(request): return getattr(request.state,"identity",{}).get("name","local-demo")
def required_ticket(id):
    t=store.get(id)
    if not t: raise HTTPException(404,"Ticket not found")
    return t

@app.get("/",include_in_schema=False)
def index(): return FileResponse(ROOT/"app/static/index.html")

@app.get("/api/health")
def health(): return {"status":"ok","demo":True,"mode":"llm-enabled" if os.getenv("BROKERASSIST_MODE")=="llm" and os.getenv("OPENAI_API_KEY") else "offline"}

@app.get("/api/session")
def session(request:Request):
    cfg=request.app.state.pilot_config
    identity=getattr(request.state,"identity",{"name":"local-demo","role":"operator"})
    return {"pilot":bool(cfg),"client":cfg["client"] if cfg else None,**identity}

@app.get("/api/ops")
def ops(): return store.ops()

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

@app.get("/api/tickets/{ticket_id}/handoff")
def specialist_handoff(ticket_id: str):
    ticket = required_ticket(ticket_id)
    try:
        return handoff.packet(ticket, store.history(ticket_id))
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None

@app.post("/api/tickets",status_code=201)
def intake(payload:Intake,request:Request):
    return store.intake(**payload.model_dump(),actor=actor(request))[0]

@app.post("/api/webhooks/ticket")
def webhook(payload:Webhook, x_webhook_secret:str|None=Header(default=None)):
    if pilot.enabled(): raise HTTPException(403,"Use signed integration endpoint")
    secret=os.getenv("BROKERASSIST_WEBHOOK_SECRET")
    if not secret: raise HTTPException(503,"Webhook disabled until a secret is configured")
    if not x_webhook_secret or not hmac.compare_digest(x_webhook_secret,secret):
        raise HTTPException(401,"Invalid webhook secret")
    ticket,duplicate=store.intake(**payload.model_dump(),actor="integration:demo")
    return {"ticket":ticket,"duplicate":duplicate}

@app.post("/api/webhooks/signed")
async def signed_webhook(request:Request):
    if not pilot.enabled():raise HTTPException(404,"Not available")
    if request.headers.get("content-type","").split(";")[0].strip().lower()!="application/json":
        raise HTTPException(415,"JSON required")
    chunks=[]; size=0
    async for chunk in request.stream():
        size+=len(chunk)
        if size>pilot.MAX_WEBHOOK_BYTES:raise HTTPException(413,"Event too large")
        chunks.append(chunk)
    body=b"".join(chunks)
    timestamp=request.headers.get("x-brokerassist-timestamp","")
    signature=request.headers.get("x-brokerassist-signature","")
    if not pilot.verify_event(body,timestamp,signature,os.getenv("BROKERASSIST_SIGNING_SECRET","")):
        raise HTTPException(401,"Invalid or expired event signature")
    try: payload=Webhook.model_validate_json(body)
    except ValidationError:raise HTTPException(422,"Invalid event schema") from None
    try: ticket,duplicate=await run_in_threadpool(store.intake,**payload.model_dump(),actor="integration:signed")
    except ValueError as e:raise HTTPException(409,str(e)) from None
    return {"id":ticket["id"],"duplicate":duplicate}

@app.post("/api/tickets/{ticket_id}/analyze")
def process(ticket_id:str,request:Request):
    ticket=required_ticket(ticket_id)
    if ticket["status"] in ("Approved","Escalated"): raise HTTPException(409,"Ticket already finalized")
    try: return store.record_analysis(ticket_id, analyze(ticket),actor=actor(request),expected_revision=ticket["analysis_revision"])
    except ValueError as e: raise HTTPException(409,str(e))

@app.post("/api/tickets/{ticket_id}/decision")
def decision(ticket_id:str,payload:Decision,request:Request):
    required_ticket(ticket_id)
    try: return store.decide(ticket_id,payload.action,payload.reply,actor=actor(request),expected_revision=payload.analysis_revision)
    except ValueError as e: raise HTTPException(409,str(e))
