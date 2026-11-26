# Connect live services and host the synthetic portfolio

## 1. Live LLM validation

This is opt-in, synthetic only, and may incur API charges. Create an API project/key through https://platform.openai.com/api-keys with appropriate usage limits and legitimate access. Never paste the key into a GitHub commit, chat, issue, or screenshot.

Either export OPENAI_API_KEY locally and run:

```powershell
$env:OPENAI_API_KEY="YOUR_KEY"
$env:OPENAI_MODEL="gpt-4.1-mini"
python -m evaluations.llm_probe --mode live --confirm-synthetic-data --repeats 1
```

Or open the repository Settings > Environments, create environment `synthetic-validation`, and add environment secret `OPENAI_API_KEY`. Restrict deployment branches to main and review permissions. In Actions, select **Manual live validation (synthetic only)** > Run workflow, branch main, target llm, confirm synthetic-only and any API charges, then run. This workflow does not run on push. One repeat attempts up to 12 provider API requests across six routine cases; five sensitive cases bypass the model. Live results are downloaded from the workflow artifact; repository artifacts may be visible to users with repo access, so use synthetic data only. Review each actual draft for policy grounding, safety and helpfulness using the rubric in [release and operations guide](llm_release_and_operations.md). An automated PASS is still PENDING_HUMAN_REVIEW.

To try the actual model in the local UI, set BROKERASSIST_MODE=llm as well, then start the server from the same terminal. Do not use run_demo.bat for model mode: that script forces offline mode.

## 2. Zendesk read-only sandbox

Use a Zendesk trial/developer sandbox you control. New API token creation has been retired; use a confidential OAuth client for server-to-server client credentials with the minimum scope `tickets:read` and a minimally privileged account. Follow https://developer.zendesk.com/documentation/authentication/api-tokens-to-oauth/ and https://developer.zendesk.com/documentation/authentication/oauth-migration/. The adapter accepts an existing short-lived read-only access token locally as an alternative. It does not create/update tickets in Zendesk, and never stores a live credential.

Manually create this exact fictional test ticket in the sandbox:

- Subject: BrokerAssist synthetic MT5 test
- Description: SYNTHETIC: MT5 displays Invalid Account. How do I select the correct trading server?

Note its numeric ticket ID. Use the sandbox subdomain only (not the entire URL).

In the same GitHub environment, add secrets ZENDESK_SUBDOMAIN, ZENDESK_CLIENT_ID, ZENDESK_CLIENT_SECRET. Run the manual workflow with target zendesk, input the numeric ticket ID, and confirm synthetic data. The probe fetches one ticket, rejects any nonmatching content, imports only into a temporary database, checks deduplication and classification, produces a check-only artifact, and sends no customer message.

Local alternative, with the three variables exported:
```powershell
$env:ALLOW_ZENDESK_SANDBOX="yes"
python -m evaluations.crm_probe --ticket-id 123 --confirm-synthetic-data
python -m app.integrations.zendesk 123
```
Replace 123 with the actual synthetic ticket ID. The latter command persists to the local database; never use it on real tickets for this demo. To use short-lived OAuth token locally instead, export ZENDESK_ACCESS_TOKEN. The old active legacy token path is compatibility only, not recommended for new projects.

## 3. Password-protected online demo on Render

The current repository contains a Render Blueprint (`render.yaml`) for a restricted **synthetic offline** demo. It is not a production customer-service deployment. It enables a simple shared HTTP Basic credential on all UI/API routes except minimal health status, refuses live model keys, requires HTTPS origin configuration, disables hosted webhooks and limits browser writes to JSON and same origin. This is not multi-user authentication or industrial security. Share access only with intended reviewers, keep the password strong/random, rotate it after interviews, and never input real customer data.

1. Create/sign in to https://dashboard.render.com/ and connect GitHub. Select a Blueprint for yasamanyord/brokerassist-ai and main. Alternatively, configure a Python Web Service manually using the values below.
2. Choose the available plan with full awareness of costs, limits and terms. The Blueprint specifies a free demo instance where available (sleep/cold starts and ephemeral disk; no persistence guarantee).
3. Supply BROKERASSIST_DEMO_PASSWORD as a secret, using a random password of at least 20 characters. The username defaults to reviewer. Do not publish the password in the repository.
4. Render provides RENDER_EXTERNAL_URL for the HTTPS origin. For a custom host, explicitly set BROKERASSIST_PUBLIC_ORIGIN to the HTTPS origin without a path.
5. Deploy manually after reviewing CI. Once ready, visit the service's actual HTTPS URL and sign in with the demo credentials. Confirm /api/health returns OK and that / and /api/tickets return HTTP 401 without credentials. Exercise the MT5 and deposit flows using synthetic input.
6. Share the URL and password only with your intended interviewer through a secure channel.

Manual configuration:
- Runtime: Python
- Build: pip install -r requirements.txt
- Start: python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT
- Health: /api/health
- BROKERASSIST_HOSTED=yes
- BROKERASSIST_MODE=offline
- BROKERASSIST_DEMO_USER=reviewer
- BROKERASSIST_DEMO_PASSWORD=your-random-secret (secret environment variable)
- BROKERASSIST_DB=runtime/hosted-demo.db

https://render.com/docs/deploy-fastapi
https://render.com/docs/blueprint-spec

Free demo data may reset across deploys/restarts. A real production client system needs a managed database, proper auth/authorization, rate limiting, monitoring, private access, data retention and other safeguards, plus live-provider and CRM testing and sign-off. This deployment config is prepared but not yet deployed. Do not add an OpenAI key to the hosted demo.

## Release evidence

The standard CI checks remain network-free. Manual live validation is separately enabled by the operator; the actual live LLM and Zendesk probes have not yet been executed. The hosted-mode credential gate and OAuth transport are tested locally with synthetic and mocked fixtures.
