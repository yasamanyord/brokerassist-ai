"""Restricted single-company pilot configuration and access boundaries.

Requires a private TLS reverse proxy, individual credentials, approved
client policy corpus, and a dedicated persistent database. Not multi-tenant SaaS.
"""
from __future__ import annotations
import base64, hashlib, hmac, json, os, re, time
from pathlib import Path
from urllib.parse import urlsplit
from fastapi import Request
from starlette.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

ROLES={"admin","operator","viewer"}
CLIENT_PATTERN=r"[a-zA-Z0-9_-]{3,64}"
USER_PATTERN=r"[a-zA-Z0-9_.@-]{2,100}"
SALT_BYTES=16
HASH_BYTES=32
MAX_WEBHOOK_BYTES=16_384
MAX_CLOCK_SKEW=300
_DECOY_SALT=b"\x00"*SALT_BYTES

def enabled():
    return os.getenv("BROKERASSIST_PILOT")=="yes"

def hash_password(password,salt):
    return hashlib.scrypt(password.encode("utf-8"),salt=salt,n=16384,r=8,p=1,dklen=HASH_BYTES)

def user_record(username,role,password):
    if not re.fullmatch(USER_PATTERN,username) or role not in ROLES or not 20<=len(password)<=256:
        raise ValueError("Valid username, role and 20–256 character password required")
    salt=os.urandom(SALT_BYTES)
    return {"username":username,"role":role,"salt":salt.hex(),"password_hash":hash_password(password,salt).hex()}

def load_users(path):
    raw=json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw,list) or not 1<=len(raw)<=100:
        raise RuntimeError("Pilot user roster must contain 1–100 users")
    users={}
    for r in raw:
        if not isinstance(r,dict) or set(r)!={"username","role","salt","password_hash"}:
            raise RuntimeError("Invalid pilot user record")
        name=r["username"]
        if not isinstance(name,str) or not re.fullmatch(USER_PATTERN,name) or name in users or r["role"] not in ROLES:
            raise RuntimeError("Invalid or duplicate pilot user")
        try: salt=bytes.fromhex(r["salt"]); digest=bytes.fromhex(r["password_hash"])
        except (ValueError,TypeError): raise RuntimeError("Invalid credential hash") from None
        if len(salt)!=SALT_BYTES or len(digest)!=HASH_BYTES: raise RuntimeError("Invalid credential hash size")
        users[name]={"role":r["role"],"salt":salt,"hash":digest}
    if not any(r["role"]=="admin" for r in users.values()):
        raise RuntimeError("Pilot must have a named admin")
    return users

def configuration():
    client=os.getenv("BROKERASSIST_CLIENT_ID","")
    db=os.getenv("BROKERASSIST_DB","")
    users_file=os.getenv("BROKERASSIST_PILOT_USERS_FILE","")
    knowledge_file=os.getenv("BROKERASSIST_PILOT_KNOWLEDGE_FILE","")
    origin=os.getenv("BROKERASSIST_PUBLIC_ORIGIN","")
    parsed=urlsplit(origin)
    if not re.fullmatch(CLIENT_PATTERN,client) or not Path(db).is_absolute():
        raise RuntimeError("Pilot requires a client ID and absolute dedicated persistent DB path")
    if not users_file or not Path(users_file).is_file() or not knowledge_file or not Path(knowledge_file).is_file():
        raise RuntimeError("Pilot requires private credential and approved knowledge files")
    if parsed.scheme!="https" or not parsed.netloc or parsed.path not in ("","/") or parsed.query or parsed.fragment or parsed.username:
        raise RuntimeError("Pilot requires an exact HTTPS origin")
    if os.getenv("BROKERASSIST_HOSTED")=="yes" or os.getenv("RENDER")=="true":
        raise RuntimeError("Pilot and public synthetic demo modes cannot be combined")
    try: limit=int(os.getenv("BROKERASSIST_DAILY_PROVIDER_CALLS","0"))
    except ValueError: raise RuntimeError("Invalid provider call limit") from None
    mode=os.getenv("BROKERASSIST_MODE","offline")
    if mode not in {"offline","llm"}:raise RuntimeError("Unsupported pilot model mode")
    llm=mode=="llm"
    if llm and (os.getenv("BROKERASSIST_PILOT_LLM_APPROVED")!="yes" or not os.getenv("OPENAI_API_KEY") or not 2<=limit<=10000):
        raise RuntimeError("Pilot LLM requires explicit data approval, API key and bounded daily provider calls")
    if not llm and os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("Do not load a provider key in offline pilot")
    secret=os.getenv("BROKERASSIST_SIGNING_SECRET","")
    if secret and len(secret)<32:
        raise RuntimeError("Integration signing secret must be at least 32 characters")
    return {"client":client,"origin":origin.rstrip("/"),"users":load_users(users_file),
            "knowledge":knowledge_file,"llm":llm,"call_limit":limit}

def authenticate(header,users):
    try:
        scheme,encoded=header.split(" ",1)
        if scheme.lower()!="basic" or len(encoded)>1024:return None
        raw=base64.b64decode(encoded,validate=True).decode("utf-8")
        name,password=raw.split(":",1)
        if len(password)>256:return None
    except (ValueError,UnicodeError):return None
    row=users.get(name)
    digest=hash_password(password,row["salt"] if row else _DECOY_SALT)
    if not hmac.compare_digest(digest,row["hash"] if row else b"\x00"*HASH_BYTES) or row is None:return None
    return {"name":name,"role":row["role"]}

def sign_event(secret,timestamp,body):
    return hmac.new(secret.encode(),str(timestamp).encode()+b"."+body,hashlib.sha256).hexdigest()

def verify_event(body,timestamp,signature,secret,now=None):
    if len(body)>MAX_WEBHOOK_BYTES or not secret or len(secret)<32:return False
    if not re.fullmatch(r"[0-9]{10}",timestamp or "") or not re.fullmatch(r"[0-9a-f]{64}",signature or ""):return False
    if abs((time.time() if now is None else now)-int(timestamp))>MAX_CLOCK_SKEW:return False
    return hmac.compare_digest(sign_event(secret,timestamp,body),signature)

def headers(response):
    response.headers["Cache-Control"]="no-store"
    response.headers["X-Content-Type-Options"]="nosniff"
    response.headers["X-Frame-Options"]="DENY"
    response.headers["Referrer-Policy"]="no-referrer"
    return response

async def access(request:Request,call_next):
    if not enabled():return await call_next(request)
    cfg=getattr(request.app.state,"pilot_config",None)
    if not cfg:return JSONResponse({"detail":"Pilot configuration unavailable"},status_code=503)
    if request.method=="GET" and request.url.path=="/api/health":
        return headers(JSONResponse({"status":"ok","demo":False,"mode":"pilot"}))
    if request.url.path=="/api/webhooks/signed" and request.method=="POST":
        # HMAC is independently verified against the original raw body by the endpoint.
        return headers(await call_next(request))
    identity=await run_in_threadpool(authenticate,request.headers.get("authorization",""),cfg["users"])
    if not identity:
        return headers(JSONResponse({"detail":"Individual pilot credentials required"},status_code=401,headers={"WWW-Authenticate":'Basic realm="BrokerAssist company pilot", charset="UTF-8"'}))
    request.state.identity=identity
    if request.url.path=="/api/ops" and identity["role"]!="admin":
        return headers(JSONResponse({"detail":"Admin role required"},status_code=403))
    if request.method not in {"GET","HEAD","OPTIONS"}:
        if identity["role"] not in {"admin","operator"}:
            return headers(JSONResponse({"detail":"Read-only viewer cannot modify tickets"},status_code=403))
        if request.headers.get("origin") and request.headers["origin"]!=cfg["origin"]:
            return headers(JSONResponse({"detail":"Cross-origin request blocked"},status_code=403))
        if request.headers.get("content-type","").split(";")[0].strip().lower()!="application/json":
            return headers(JSONResponse({"detail":"JSON request required"},status_code=415))
        if request.url.path=="/api/webhooks/ticket":
            return headers(JSONResponse({"detail":"Use the signed integration endpoint"},status_code=403))
    return headers(await call_next(request))
