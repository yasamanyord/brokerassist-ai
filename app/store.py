"""SQLite persistence for local demo. No live CRM or customer communication."""
from __future__ import annotations
import json, os, sqlite3, uuid
from datetime import datetime, timezone
from pathlib import Path
from contextlib import contextmanager
from .engine import ROOT, redact

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
    with connect() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS tickets (
          id TEXT PRIMARY KEY, customer TEXT NOT NULL, channel TEXT NOT NULL, subject TEXT NOT NULL,
          message TEXT NOT NULL, created_at TEXT NOT NULL, verified INTEGER NOT NULL DEFAULT 0,
          transaction_ref TEXT, status TEXT NOT NULL DEFAULT 'New', analysis TEXT, final_reply TEXT,
          event_id TEXT UNIQUE
        );
        CREATE TABLE IF NOT EXISTS audit (
          id INTEGER PRIMARY KEY AUTOINCREMENT, ticket_id TEXT NOT NULL, action TEXT NOT NULL,
          detail TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        """)
        if not c.execute("SELECT 1 FROM metadata WHERE key='seeded'").fetchone():
            for t in json.loads((ROOT/"data/tickets.json").read_text(encoding="utf-8")):
                c.execute("INSERT OR IGNORE INTO tickets(id,customer,channel,subject,message,created_at,verified,transaction_ref) VALUES(?,?,?,?,?,?,?,?)",
                    (t["id"],t["customer"],t["channel"],t["subject"],t["message"],t["created_at"],int(t.get("verified",False)),t.get("transaction_ref")))
            c.execute("INSERT OR IGNORE INTO metadata VALUES('seeded','1')")

def deserialize(row):
    if row is None: return None
    d=dict(row); d["verified"]=bool(d["verified"]); d["analysis"]=json.loads(d["analysis"]) if d["analysis"] else None
    return d

def tickets():
    with connect() as c: return [deserialize(r) for r in c.execute("SELECT * FROM tickets ORDER BY created_at DESC, id DESC")]
def get(ticket_id):
    with connect() as c: return deserialize(c.execute("SELECT * FROM tickets WHERE id=?",(ticket_id,)).fetchone())
def audit(c,ticket_id,action,detail):
    c.execute("INSERT INTO audit(ticket_id,action,detail,created_at) VALUES(?,?,?,?)",(ticket_id,action,detail,now()))
def history(ticket_id):
    with connect() as c: return [dict(r) for r in c.execute("SELECT * FROM audit WHERE ticket_id=? ORDER BY id DESC",(ticket_id,))]
def intake(customer,channel,subject,message,event_id=None):
    with connect() as c:
        c.execute("BEGIN IMMEDIATE")
        if event_id:
            row=c.execute("SELECT * FROM tickets WHERE event_id=?",(event_id,)).fetchone()
            if row: return deserialize(row),True
        tid="BA-"+uuid.uuid4().hex[:8].upper()
        c.execute("INSERT INTO tickets(id,customer,channel,subject,message,created_at,event_id) VALUES(?,?,?,?,?,?,?)",
                  (tid,redact(customer),channel,redact(subject),redact(message),now(),event_id))
        audit(c,tid,"received","Ticket received from "+channel+"; no verified account context.")
        return deserialize(c.execute("SELECT * FROM tickets WHERE id=?",(tid,)).fetchone()),False
def record_analysis(ticket_id, result):
    with connect() as c:
        c.execute("BEGIN IMMEDIATE")
        row=c.execute("SELECT status FROM tickets WHERE id=?",(ticket_id,)).fetchone()
        if not row: raise KeyError(ticket_id)
        if row["status"] in ("Approved","Escalated"): raise ValueError("Ticket already finalized")
        c.execute("UPDATE tickets SET analysis=?,status='In review' WHERE id=?",(json.dumps(result),ticket_id))
        audit(c,ticket_id,"analyzed",result["category"]+" • "+result["decision"]+" • "+result["mode"])
    return get(ticket_id)
def decide(ticket_id,action,reply=None):
    with connect() as c:
        c.execute("BEGIN IMMEDIATE")
        row=deserialize(c.execute("SELECT * FROM tickets WHERE id=?",(ticket_id,)).fetchone())
        if not row: raise KeyError(ticket_id)
        if row["status"] != "In review" or not row["analysis"]: raise ValueError("Analyze an open ticket before taking action")
        if action=="approve" and row["analysis"]["mandatory_escalation"]: raise ValueError("Specialist escalation required; approval blocked")
        if action=="approve":
            status="Approved"; final=redact((reply or row["analysis"]["draft"]).strip())
            if not final: raise ValueError("Response cannot be empty")
            audit(c,ticket_id,"approved","Operator approved local draft; nothing sent externally.")
        else:
            status="Escalated"; final=None
            audit(c,ticket_id,"escalated","Assigned internally to "+row["analysis"]["team"]+"; no external action.")
        c.execute("UPDATE tickets SET status=?,final_reply=? WHERE id=?",(status,final,ticket_id))
    return get(ticket_id)

def metrics():
    rows=tickets()
    return {"total":len(rows),"new":sum(t["status"]=="New" for t in rows),
            "review":sum(t["status"]=="In review" for t in rows),"approved":sum(t["status"]=="Approved" for t in rows),
            "escalated":sum(t["status"]=="Escalated" for t in rows),"analyzed":sum(bool(t["analysis"]) for t in rows)}
