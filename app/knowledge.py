"""Approved, versioned knowledge boundary for a dedicated company pilot."""
import hashlib, json
from pathlib import Path
from .guardrails import unsafe_draft_reasons

# Stable IDs used by case routing. Individual client policy content is private.
REQUIRED={"KB-001":"MT5","KB-002":"Deposit","KB-003":"Withdrawal","KB-004":"KYC",
          "KB-005":"Accounts","KB-006":"Trading conditions","KB-007":"Bonus","KB-008":"Technical",
          "KB-009":"Partnerships","KB-010":"Security","KB-011":"Trading disputes","KB-012":"General"}

def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()

def approved(path,client):
    doc=json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(doc,dict) or doc.get("client_id")!=client or doc.get("approved") is not True:
        raise RuntimeError("Knowledge requires explicit client-specific approval")
    if not all(isinstance(doc.get(k),str) and doc[k].strip() for k in ("version","approved_by","approved_at")):
        raise RuntimeError("Knowledge version, approving owner and approval date required")
    policies=doc.get("policies")
    if not isinstance(policies,list) or len(policies)!=len(REQUIRED):raise RuntimeError("All required policies must be explicitly supplied")
    seen=set()
    for p in policies:
        if not isinstance(p,dict) or set(p)!={"id","category","title","policy","reply","keywords"} or not isinstance(p.get("id"),str) or p["id"] not in REQUIRED or p["id"] in seen or REQUIRED[p["id"]]!=p.get("category"):
            raise RuntimeError("Unknown, duplicate, or mismatched policy ID")
        seen.add(p["id"])
        if not all(isinstance(p.get(k),str) and 0<len(p[k].strip())<=8000 for k in ("title","policy","reply")):
            raise RuntimeError("Incomplete client policy")
        if not isinstance(p.get("keywords"),list) or not p["keywords"] or not all(isinstance(k,str) and k.strip() and len(k)<=100 for k in p["keywords"]):
            raise RuntimeError("Each policy requires valid retrieval keywords")
        if unsafe_draft_reasons(p["reply"]):raise RuntimeError("Approved draft violates a core response boundary")
    if seen!=set(REQUIRED):raise RuntimeError("Missing client policy")
    return policies,fingerprint(doc)
