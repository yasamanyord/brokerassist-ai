import os,sys,tempfile,subprocess,time,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
os.chdir(ROOT)
from playwright.sync_api import sync_playwright
with tempfile.TemporaryDirectory() as tmp:
    env={**os.environ,"BROKERASSIST_DB":tmp+"/ui.db","BROKERASSIST_MODE":"offline"}
    proc=subprocess.Popen([sys.executable,"-m","uvicorn","app.main:app","--host","127.0.0.1","--port","8878"],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen("http://127.0.0.1:8878/api/health",timeout=1);break
            except Exception:time.sleep(.2)
        else:raise RuntimeError("Server failed to start")
        with sync_playwright() as p:
            b=p.chromium.launch(headless=True,executable_path=os.getenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE") or None)
            page=b.new_page(viewport={"width":1440,"height":1080})
            errors=[]
            page.on("pageerror",lambda error:errors.append(str(error)))
            page.goto("http://127.0.0.1:8878")
            page.get_by_role("button",name="Analyze ticket").click()
            page.get_by_text("Specialist review required",exact=False).wait_for()
            page.get_by_text("Risk flags:",exact=False).wait_for()
            assert page.get_by_role("button",name="Approve local draft").is_disabled()
            
            page.get_by_role("button",name="Escalate to Finance").click()
            page.get_by_text("Finalized locally: Escalated",exact=False).wait_for()
            page.locator('[data-ticket="BA-1041"]').click()
            page.get_by_role("button",name="Analyze ticket").click()
            page.get_by_text("Operator review required",exact=False).wait_for()
            page.locator("#draft").fill("Please send your password here.")
            page.get_by_role("button",name="Approve local draft").click()
            page.get_by_text("Draft violates the safety boundary",exact=False).wait_for()
            page.get_by_role("button",name="Approve local draft").wait_for()
            page.locator("#draft").fill("Reviewed demo reply. Please select the correct server.")
            page.get_by_role("button",name="Approve local draft").click()
            page.get_by_text("Finalized locally: Approved",exact=False).wait_for()
            page.get_by_role("button",name="Knowledge base").click()
            page.get_by_role("heading",name="MT5 sign-in troubleshooting").wait_for()
            page.get_by_role("button",name="Operations").click()
            page.get_by_role("heading",name="Ticket distribution").wait_for()
            page.get_by_role("button",name="Ticket inbox").click()
            page.get_by_role("button",name="New ticket").click()
            page.locator('input[name="subject"]').fill("Synthetic security case")
            page.locator('textarea[name="message"]').fill("I think my account was hacked.")
            page.get_by_role("button",name="Create ticket").click()
            page.get_by_role("heading",name="Synthetic security case").wait_for()
            page.get_by_role("button",name="Analyze ticket").click()
            page.get_by_text("Specialist review required",exact=False).wait_for()
            page.get_by_role("button",name="Escalate to Security").wait_for()
            assert not errors, errors
            page.set_viewport_size({"width":390,"height":844})
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            
            b.close()
        print("Browser smoke: PASS (desktop + mobile, analyze, approve, escalate, knowledge, analytics, intake; no page errors)")
    finally:
        proc.terminate();proc.wait(timeout=10)
