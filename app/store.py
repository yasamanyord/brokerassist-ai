"""Durable SQLite store: one deployment, one company, local decisions only."""
from __future__ import annotations
import json, os, sqlite3, uuid, hashlib
from datetime import datetime, timezone
from pathlib import Path
from contextlib import contextmanager
from . import engine, pilot
from .engine import ROOT, redact, analyze
from .guardrails import VERSION as GUARDRAIL_VERSION, unsafe_draft_reasons

def now(): return datetime.now(timezone.utc).isoformat(timespec="seconds")
def db_path(): return Path(os.getenv("BROKERASSIST_DB", str(ROOT/"runtime"/"brokerassist.db")))

@contextmanager
def connect():
    path=db_path(); path.parent.mkdir(parents=True,exist_ok=True)
    conn=sqlite3.connect(path,timeout=10); conn.row_factory=sqlite3.Row
    try:
        with conn: yield conn
    finally: conn.close()

def initialize():
    if pilot.enabled():
        path=db_path();path.parent.mkdir(parents=True,exist_ok=True)
        try:
            fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
        except FileExistsError:
            if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
                raise RuntimeError("Pilot requires a private owner-only database file")
    with connect() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS tickets (
          id TEXT PRIMARY KEY, customer TEXT NOT NULL, channel TEXT NOT NULL, subject TEXT NOT NULL,
          message TEXT NOT NULL, created_at TEXT NOT NULL, verified INTEGER NOT NULL DEFAULT 0,
          transaction_ref TEXT, status TEXT NOT NULL DEFAULT 'New', analysis TEXT, final_reply TEXT,
          event_id TEXT UNIQUE, event_digest TEXT, analysis_revision INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS audit (
          id INTEGER PRIMARY KEY AUTOINCREMENT, ticket_id TEXT NOT NULL, action TEXT NOT NULL,
          detail TEXT NOT NULL, created_at TEXT NOT NULL, actor TEXT NOT NULL DEFAULT 'legacy-demo'
        );
        CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS provider_usage (day TEXT PRIMARY KEY, calls INTEGER NOT NULL);
        """)
        c.execute("BEGIN IMMEDIATE")
        metadata=dict(c.execute("SELECT key,value FROM metadata").fetchall())
        owner="pilot:"+os.environ["BROKERASSIST_CLIENT_ID"] if pilot.enabled() else "demo"
        existing=metadata.get("deployment")
        if existing and existing!=owner:
            raise RuntimeError("Database belongs to a different deployment; use a dedicated database")
        if pilot.enabled() and not existing and (metadata or c.execute("SELECT 1 FROM tickets LIMIT 1").fetchone() or c.execute("SELECT 1 FROM audit LIMIT 1").fetchone()):
            raise RuntimeError("Pilot cannot adopt an existing unbound database")
        c.execute("INSERT OR IGNORE INTO metadata VALUES('deployment',?)",(owner,))
        for table,column,definition in (("tickets","event_digest","TEXT"),("tickets","analysis_revision","INTEGER NOT NULL DEFAULT 0"),("audit","actor","TEXT NOT NULL DEFAULT 'legacy-demo'")):
            if column not in {r["name"] for r in c.execute("PRAGMA table_info("+table+")")}:
                c.execute("ALTER TABLE "+table+" ADD COLUMN "+column+" "+definition)
        if not pilot.enabled() and "seeded" not in metadata:
            for t in json.loads((ROOT/"data/tickets.json").read_text(encoding="utf-8")):
                c.execute("INSERT OR IGNORE INTO tickets(id,customer,channel,subject,message,created_at,verified,transaction_ref) VALUES(?,?,?,?,?,?,?,?)",
                    (t["id"],t["customer"],t["channel"],t["subject"],t["message"],t["created_at"],int(t.get("verified",False)),t.get("transaction_ref")))
            c.execute("INSERT OR IGNORE INTO metadata VALUES('seeded','1')")

def deserialize(row):
    if row is None: return None
    d=dict(row); d.pop("event_digest",None); d["verified"]=bool(d["verified"]); d["analysis"]=json.loads(d["analysis"]) if d["analysis"] else None
    return d

def tickets():
    with connect() as c: return [deserialize(r) for r in c.execute("SELECT * FROM tickets ORDER BY created_at DESC, id DESC")]
def get(ticket_id):
    with connect() as c: return deserialize(c.execute("SELECT * FROM tickets WHERE id=?",(ticket_id,)).fetchone())
def audit(c,ticket_id,action,detail,actor="local-demo"):
    c.execute("INSERT INTO audit(ticket_id,action,detail,created_at,actor) VALUES(?,?,?,?,?)",(ticket_id,action,detail,now(),actor))
def history(ticket_id):
    with connect() as c: return [dict(r) for r in c.execute("SELECT * FROM audit WHERE ticket_id=? ORDER BY id DESC",(ticket_id,))]
def intake(customer,channel,subject,message,event_id=None,actor="local-demo"):
    digest=hashlib.sha256(json.dumps([customer,channel,subject,message],ensure_ascii=False,separators=(",",":")).encode()).hexdigest() if event_id and pilot.enabled() else None
    with connect() as c:
        c.execute("BEGIN IMMEDIATE")
        if event_id:
            row=c.execute("SELECT * FROM tickets WHERE event_id=?",(event_id,)).fetchone()
            if row:
                if pilot.enabled() and row["event_digest"]!=digest: raise ValueError("Event ID already used with different content")
                return deserialize(row),True
        tid="BA-"+uuid.uuid4().hex[:12].upper()
        c.execute("INSERT INTO tickets(id,customer,channel,subject,message,created_at,event_id,event_digest) VALUES(?,?,?,?,?,?,?,?)",
                  (tid,redact(customer),channel,redact(subject),redact(message),now(),event_id,digest))
        audit(c,tid,"received","Ticket received from "+channel+"; no verified account context.",actor)
        return deserialize(c.execute("SELECT * FROM tickets WHERE id=?",(tid,)).fetchone()),False
def record_analysis(ticket_id, result, actor="local-demo", expected_revision=None):
    with connect() as c:
        c.execute("BEGIN IMMEDIATE")
        row=c.execute("SELECT status,analysis_revision FROM tickets WHERE id=?",(ticket_id,)).fetchone()
        if not row: raise KeyError(ticket_id)
        if row["status"] in ("Approved","Escalated"): raise ValueError("Ticket already finalized")
        if pilot.enabled() and expected_revision!=row["analysis_revision"]: raise ValueError("Ticket changed; refresh and re-analyze")
        c.execute("UPDATE tickets SET analysis=?,status='In review',analysis_revision=analysis_revision+1 WHERE id=?",(json.dumps(result),ticket_id))
        audit(c,ticket_id,"analyzed",result["category"]+" • "+result["decision"]+" • "+result["mode"],actor)
    return get(ticket_id)
def decide(ticket_id,action,reply=None,actor="local-demo",expected_revision=None):
    if action not in ("approve","escalate"): raise ValueError("Unsupported decision")
    denial=None
    with connect() as c:
        c.execute("BEGIN IMMEDIATE")
        row=deserialize(c.execute("SELECT * FROM tickets WHERE id=?",(ticket_id,)).fetchone())
        if not row: raise KeyError(ticket_id)
        if row["status"] != "In review" or not row["analysis"]:
            denial="Analyze an open ticket before taking action"
        elif pilot.enabled() and expected_revision!=row["analysis_revision"]:
            denial="Analysis changed; refresh before recording a decision"
        elif action=="approve":
            current=analyze(row,allow_llm=False)
            if row["analysis"]["mandatory_escalation"] or current["mandatory_escalation"]:
                denial="Specialist escalation required; approval blocked"
            elif row["analysis"].get("guardrail_version") != GUARDRAIL_VERSION:
                denial="Analysis is outdated; re-analyze using the current safety rules"
            elif pilot.enabled() and row["analysis"].get("knowledge_revision")!=engine.KNOWLEDGE_REVISION:
                denial="Client knowledge changed; re-analyze before approval"
            else:
                final=(row["analysis"]["draft"] if reply is None else reply).strip()
                if not final: denial="Response cannot be empty"
                elif unsafe_draft_reasons(final): denial="Draft violates the safety boundary; edit or escalate"
                else: final=redact(final)
        if denial: audit(c,ticket_id,"decision_blocked",denial,actor)
        elif action=="approve":
            c.execute("UPDATE tickets SET status='Approved',final_reply=? WHERE id=?",(final,ticket_id))
            audit(c,ticket_id,"approved","Operator approved local draft; nothing sent externally.",actor)
        else:
            c.execute("UPDATE tickets SET status='Escalated',final_reply=NULL WHERE id=?",(ticket_id,))
            audit(c,ticket_id,"escalated","Assigned internally to "+row["analysis"]["team"]+"; no external action.",actor)
    if denial: raise ValueError(denial)
    return get(ticket_id)

def reserve_provider_request():
    day=now()[:10]
    limit=int(os.environ.get("BROKERASSIST_DAILY_PROVIDER_CALLS","0"))
    with connect() as c:
        c.execute("BEGIN IMMEDIATE")
        row=c.execute("SELECT calls FROM provider_usage WHERE day=?",(day,)).fetchone()
        if (row["calls"] if row else 0)>=limit:return False
        c.execute("INSERT INTO provider_usage VALUES(?,1) ON CONFLICT(day) DO UPDATE SET calls=calls+1",(day,))
        return True

def metrics():
    rows=tickets()
    return {"total":len(rows),"new":sum(t["status"]=="New" for t in rows),
            "review":sum(t["status"]=="In review" for t in rows),"approved":sum(t["status"]=="Approved" for t in rows),
            "escalated":sum(t["status"]=="Escalated" for t in rows),"analyzed":sum(bool(t["analysis"]) for t in rows)}

def ops():
    with connect() as c:
        row=c.execute("SELECT calls FROM provider_usage WHERE day=?",(now()[:10],)).fetchone()
        return {"utc_day":now()[:10],"provider_calls":row["calls"] if row else 0,
                "daily_call_limit":int(os.getenv("BROKERASSIST_DAILY_PROVIDER_CALLS","0")),
                "blocked_decisions":c.execute("SELECT COUNT(*) FROM audit WHERE action='decision_blocked'").fetchone()[0],
                "knowledge_revision":engine.KNOWLEDGE_REVISION}
