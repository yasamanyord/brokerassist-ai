"""Browser smoke in a restricted pilot using entirely fictional fixtures."""
import json,os,sys,tempfile,subprocess,time,urllib.request,ssl
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));os.chdir(ROOT)
from playwright.sync_api import sync_playwright
from app.pilot import user_record
PASSWORD="browser-test-password-123456"
with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp)
    (root/"users.json").write_text(json.dumps([user_record("alice","admin",PASSWORD),user_record("bob","operator",PASSWORD),user_record("carol","viewer",PASSWORD)]))
    (root/"knowledge.json").write_text(json.dumps({"client_id":"browser-test-company","approved":True,"approved_by":"fixture approver","approved_at":"2026-01-01","version":"fixture-1","policies":json.loads((ROOT/"data/knowledge.json").read_text())}))
    # Ephemeral self-signed TLS certificate for synthetic browser testing only.
    subprocess.run(["openssl","req","-x509","-newkey","rsa:2048","-keyout",str(root/"key.pem"),"-out",str(root/"cert.pem"),"-days","1","-nodes","-subj","/CN=localhost"],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    env={**os.environ,"BROKERASSIST_PILOT":"yes","BROKERASSIST_CLIENT_ID":"browser-test-company","BROKERASSIST_DB":str(root/"pilot.db"),"BROKERASSIST_PILOT_USERS_FILE":str(root/"users.json"),"BROKERASSIST_PILOT_KNOWLEDGE_FILE":str(root/"knowledge.json"),"BROKERASSIST_PUBLIC_ORIGIN":"https://127.0.0.1:8879","BROKERASSIST_MODE":"offline","OPENAI_API_KEY":""}
    proc=subprocess.Popen([sys.executable,"-m","uvicorn","app.main:app","--host","127.0.0.1","--port","8879","--ssl-keyfile",str(root/"key.pem"),"--ssl-certfile",str(root/"cert.pem")],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.STDOUT)
    try:
        for _ in range(60):
            try:urllib.request.urlopen("https://127.0.0.1:8879/api/health",timeout=1,context=ssl._create_unverified_context());break
            except Exception:time.sleep(.2)
        else:raise RuntimeError("Pilot server failed startup")
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True,executable_path=os.getenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE") or None)
            ctx=browser.new_context(http_credentials={"username":"bob","password":PASSWORD},ignore_https_errors=True)
            page=ctx.new_page();errors=[];page.on("pageerror",lambda e:errors.append(str(e)))
            page.goto("https://127.0.0.1:8879")
            page.get_by_text("Restricted company pilot",exact=True).wait_for()
            page.get_by_text("No matching tickets.").wait_for()
            page.get_by_role("button",name="New ticket").click()
            page.locator('[name="customer"]').fill("Synthetic customer")
            page.locator('[name="subject"]').fill("MT5 login")
            page.locator('[name="message"]').fill("Invalid account on MT5.")
            page.get_by_role("button",name="Create ticket").click()
            page.get_by_role("heading",name="MT5 login").wait_for()
            page.get_by_role("button",name="Analyze ticket").click()
            page.get_by_text("Operator review required",exact=False).wait_for()
            page.get_by_role("button",name="Approve local draft").click()
            page.get_by_text("Finalized locally: Approved",exact=False).wait_for()
            page.locator("#audit-rows").get_by_text("bob",exact=False).first.wait_for()
            page.get_by_role("button",name="New ticket").click()
            page.locator('[name="customer"]').fill("Synthetic customer")
            page.locator('[name="subject"]').fill("Withdrawal request")
            page.locator('[name="message"]').fill("Please review my withdrawal.")
            page.get_by_role("button",name="Create ticket").click()
            page.get_by_role("heading",name="Withdrawal request").wait_for()
            page.get_by_role("button",name="Analyze ticket").click()
            page.get_by_role("button",name="Escalate to Finance").click()
            packet=page.get_by_role("textbox",name="Specialist handoff")
            packet.wait_for()
            assert "Recorded by: bob" in packet.input_value()
            assert "Not sent to a specialist" in packet.input_value()
            assert not errors,errors
            ctx.close()
            viewer=browser.new_context(http_credentials={"username":"carol","password":PASSWORD},ignore_https_errors=True).new_page()
            viewer.goto("https://127.0.0.1:8879")
            viewer.get_by_text("Restricted company pilot",exact=True).wait_for()
            viewer.get_by_role("button",name="Withdrawal request",exact=False).click()
            viewer.get_by_role("heading",name="Withdrawal request").wait_for()
            viewer.get_by_role("textbox",name="Specialist handoff").wait_for()
            assert viewer.get_by_role("button",name="New ticket").is_hidden()
            assert viewer.get_by_role("button",name="Approve local draft").count()==0
            browser.close()
        print("Pilot browser smoke: PASS (named operator, empty company store, intake, analyze, approval and actor audit, viewer)")
    finally:proc.terminate();proc.wait(timeout=10)
