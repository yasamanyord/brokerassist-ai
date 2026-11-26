"""Minimal hosted synthetic demo access gate (not enterprise auth).

The hosting provider must supply TLS. No real support data or live model calls are
allowed in hosted mode; one shared account is intended for a restricted demo.
"""
from __future__ import annotations
import os, base64, binascii, hmac
from urllib.parse import urlsplit
from fastapi import Request
from starlette.responses import JSONResponse

def enabled():
    return os.getenv("BROKERASSIST_HOSTED")=="yes" or os.getenv("RENDER")=="true"

def configuration():
    user=os.getenv("BROKERASSIST_DEMO_USER","reviewer")
    password=os.getenv("BROKERASSIST_DEMO_PASSWORD","")
    origin=os.getenv("BROKERASSIST_PUBLIC_ORIGIN","") or os.getenv("RENDER_EXTERNAL_URL","")
    parsed=urlsplit(origin)
    if (not user or ":" in user or len(password)<20 or parsed.scheme!="https" or
            not parsed.netloc or parsed.path not in ("","/") or parsed.query or parsed.fragment or parsed.username):
        raise RuntimeError("Hosted demo needs a username, a strong password (20+ chars), and an HTTPS origin")
    if os.getenv("BROKERASSIST_MODE","offline")!="offline" or os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("Hosted demo must use offline mode without a live model key")
    return user,password,origin.rstrip("/")

def valid_basic(header,user,password):
    try:
        scheme,encoded=header.split(" ",1)
        if scheme.lower()!="basic": return False
        raw=base64.b64decode(encoded,validate=True)
        expected=(user+":"+password).encode("utf-8")
        return hmac.compare_digest(raw,expected)
    except (ValueError,binascii.Error):
        return False

async def hosted_access(request:Request, call_next):
    if not enabled(): return await call_next(request)
    try: user,password,origin=configuration()
    except RuntimeError:
        return JSONResponse({"detail":"Hosted demo configuration unavailable"},status_code=503)
    if request.url.path=="/api/health" and request.method=="GET":
        return JSONResponse({"status":"ok","demo":True,"mode":"offline"})
    if not valid_basic(request.headers.get("authorization",""),user,password):
        return JSONResponse({"detail":"Demo access requires authentication"},status_code=401,
                            headers={"WWW-Authenticate":'Basic realm="BrokerAssist synthetic demo", charset="UTF-8"',"Cache-Control":"no-store"})
    if request.method not in {"GET","HEAD","OPTIONS"}:
        # Browser basic authentication may be sent automatically. Require
        # same-origin or a non-simple JSON request, no permissive CORS.
        if request.headers.get("origin") and request.headers["origin"]!=origin:
            return JSONResponse({"detail":"Cross-origin request blocked"},status_code=403)
        if request.headers.get("content-type","").split(";")[0].strip().lower()!="application/json":
            return JSONResponse({"detail":"JSON request required"},status_code=415)
        if request.url.path=="/api/webhooks/ticket":
            return JSONResponse({"detail":"Webhooks disabled in hosted synthetic demo"},status_code=403)
    response=await call_next(request)
    response.headers["Cache-Control"]="no-store"
    response.headers["X-Content-Type-Options"]="nosniff"
    response.headers["X-Frame-Options"]="DENY"
    response.headers["Referrer-Policy"]="no-referrer"
    return response
