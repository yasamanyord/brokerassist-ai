# Operator runbook

## Start
Start with run_demo.bat (Windows), the quick-start commands, or Docker. Visit http://127.0.0.1:8000. /api/health should report ok and offline by default.

## Normal operations
1. Select or create a fictional ticket.
2. Analyze; inspect priority, team, retrieved source and tool status.
3. Edit the draft as needed. Only routine tickets can be locally approved. Sensitive tickets must be escalated.
4. Check ticket status and audit history. Nothing is sent externally.
5. Review the Operations counters.

## Troubleshooting
- Port already occupied: choose --port 8001 and use the matching URL.
- Dependency errors: confirm Python 3.11+ and pip install -r requirements.txt inside the virtual environment.
- Empty inbox: check server logs and BROKERASSIST_DB path. Startup initializes sample seed only for a fresh database.
- Model fallback: verify environment variables, access, model ID and network; use the offline draft meanwhile. Never print credentials or log API keys.
- Webhook 503: secret not configured; 401: incorrect secret; duplicate=true: existing event reused.
- Approval 409: ticket is not in review, is already finalized, or requires specialist escalation. Do not bypass.
- LLM draft inconsistent with policy: reject it by escalation. Investigate and add a regression case.

## Test and release gate
Run python -m unittest discover -s tests -v and python evaluations/run.py, then python -m evaluations.regression --reviewed-drafts evaluations/reviewed_drafts.json and python -m evaluations.llm_probe --mode mock. For prompt or model changes, also use the opt-in live probe and a paired human review. See [LLM release and operations](llm_release_and_operations.md). For UI checks, run tests/browser_smoke.py with a working Playwright Chromium, inspect desktop and mobile layout, test human actions. Review docs and actual test results. Do not deploy in a real brokerage without authentication, privacy review, client acceptance and tested integration.

## Maintenance
Policy owner should version approved policy and templates, re-run tests after changes, add examples for evolving support issues, review false escalations and missed escalation cases, and document observed failures. For live use, add health monitoring and alerting, restore drills, access reviews, incident handling, and controlled rollout.

## Backup and reset
The default database lives in runtime/brokerassist.db. Stop the server before backing it up. To start a clean synthetic demo, set BROKERASSIST_DB to a new path or move the existing database to a backup file while stopped. No real production data should be stored here.
