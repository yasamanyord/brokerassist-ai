# Controlled company pilot — deployment and operator handoff

**Status:** implemented and tested locally with fictional fixtures. This is a single-company internal support copilot, **not a certified or deployed production brokerage system**. It starts with no tickets and cannot send replies, make transactions, or verify customers. Do not onboard real data until the client approves the scope, privacy and security controls, isolated infrastructure, operational responsibilities and acceptance results.

## 1. Discovery and sign-off

Use the [pilot acceptance checklist](pilot_acceptance.md) in a discovery call. Agree on supported languages/categories, policy owners, escalation destinations, allowed data fields/retention, incident owner and integration authentication. Begin with synthetic staging; use curated independent client cases before approval. No need for Zapier or a paid CRM subscription to run the internal workflow.

## 2. Prepare private configuration

Run the setup on a dedicated company-managed Linux host or private VM, behind a private HTTPS/load-balanced reverse proxy. One deployment and storage volume per client; use a unique Compose project name and do not share a volume, configuration folder or provider credential across companies. Do not use the free public Render demo for company records.

From the repository root, using Python 3.11+ and the dependencies in requirements.txt:

```bash
umask 077
mkdir -p client-config pilot-data backups
cp config/client_knowledge.template.json client-config/knowledge.json
python -m app.pilot_admin --file client-config/users.json --username pilot-admin --role admin
python -m app.pilot_admin --file client-config/users.json --username operator-one --role operator
python -m app.pilot_admin --file client-config/users.json --username reviewer-one --role viewer
```

Use independent strong passwords (20–256 characters) stored in the client's password manager; the CLI prompts without echoing and persists salted scrypt hashes, not passwords. Never publish these files or secrets. Remove departed accounts from the private roster, rotate passwords via the CLI, and restart the service to apply changes. Keep at least one named admin. All pilot users can read the company's queue and approved knowledge; only admin/operator can modify tickets and only admin can access /api/ops. This is not SSO, MFA, per-ticket authorization, or an enterprise identity platform.

Complete all 12 policy slots in the template with approved client material, stable IDs/categories, retrieval keywords, policy text and safe draft. Do not copy the fictional policies into a live deployment. Set the actual client ID, policy version, approving owner's name and approval date; set approved to true **only after** client authorization. Update the knowledge version, rerun client evals and restart after edits. Existing drafts with stale policy fingerprints cannot be approved until re-analyzed. The approval fields are administrative workflow metadata, not a cryptographic signature.

Create a private environment file, or inject values via your secret manager:

```dotenv
BROKERASSIST_CLIENT_ID=your-company-id
BROKERASSIST_PUBLIC_ORIGIN=https://private-pilot.example.com
BROKERASSIST_MODE=offline
BROKERASSIST_PILOT_LLM_APPROVED=no
BROKERASSIST_DAILY_PROVIDER_CALLS=0
```

Default offline mode requires no external provider. For company-specific testing of model mode, obtain approved data-processing terms and a scoped company-owned API account; enable BROKERASSIST_MODE=llm, BROKERASSIST_PILOT_LLM_APPROVED=yes, OPENAI_API_KEY and a daily request limit of 2–10,000; set OPENAI_MODEL to the evaluated model. Each routine generation uses at most two calls, with atomic UTC-day counting and safe fallback. This is a request cap, not a currency-based spend guarantee. Configure provider-level spend controls separately. Sensitive and unknown cases never enter LLM generation. Redaction is incomplete; the customer's approved data handling policy must control intake. Keep LLM disabled until authorized.

## 3. Launch and verify

Direct private service (no container required):

```bash
export BROKERASSIST_PILOT=yes
export BROKERASSIST_CLIENT_ID=your-company-id
export BROKERASSIST_PUBLIC_ORIGIN=https://private-pilot.example.com
export BROKERASSIST_DB="$PWD/pilot-data/pilot.db"
export BROKERASSIST_PILOT_USERS_FILE="$PWD/client-config/users.json"
export BROKERASSIST_PILOT_KNOWLEDGE_FILE="$PWD/client-config/knowledge.json"
export BROKERASSIST_MODE=offline
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Alternative container configuration:

```bash
docker compose -p company-id -f docker-compose.pilot.yml up -d --build
```

Compose binds to loopback, uses a dedicated named data volume and read-only config mount, and runs as non-root with dropped capabilities. The company host administrator must ensure that the container UID can read the private config files and write the runtime volume; grant only that service UID access (do not make secrets world-readable). Docker configuration is provided but was not executed in this workspace. Run staging validation of the final image, proxy and volumes before using it.

**Network gate:** configure the reverse proxy for HTTPS only (valid certificate, HTTPS redirect, HSTS, no direct public Uvicorn access), exact public origin, strong request-size and connection/rate limits including Basic auth and webhooks, no request-body or Authorization logging, and network/VPN allowlisting. Restrict /docs and /openapi.json to internal access. The API enforces its own authentication; TLS and throttling are infrastructure responsibilities. The Docker port binding is not a TLS proxy. The pilot browser test uses an ephemeral self-signed loopback TLS certificate; it does not validate the company’s real proxy or certificate configuration.

Verify: health returns pilot; unauthenticated /api/tickets returns 401; named credentials work; viewer cannot write; admin can view /api/ops. Verify the database initially contains zero tickets and stays present across restart. Exercise synthetic intake, a routine approval, a high-risk escalation and a blocked unsafe draft. Do not import real data during this check.

## 4. Integration boundary

The pilot accepts manual intake and POST /api/webhooks/signed from a client-approved relay. It does not directly implement Zendesk's native webhook format or write-back. The existing OAuth Zendesk adapter is synthetic-sandbox-only and cannot open pilot storage. The client relay must authenticate the source, minimize permitted fields, preserve an idempotency key and sign the exact bytes it sends. Set BROKERASSIST_SIGNING_SECRET to a private random secret of at least 32 characters (use the client's vault). If unset, all signed events fail closed.

Example relay code for an authorized staging connection:

```python
# Use synthetic content for staging; do not log secret or payload.
import hashlib, hmac, json, os, time, urllib.request
body = json.dumps({
    "event_id": "crm-staging-event-001",
    "customer": "Synthetic tester",
    "channel": "CRM",
    "subject": "MT5 login",
    "message": "Invalid account on MT5."
}).encode()
timestamp = str(int(time.time()))
signature = hmac.new(os.environ["BROKERASSIST_SIGNING_SECRET"].encode(),
                     timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
# Only send to your approved private company HTTPS origin.
req = urllib.request.Request(os.environ["BROKERASSIST_PUBLIC_ORIGIN"] + "/api/webhooks/signed",
    data=body, method="POST", headers={"Content-Type": "application/json",
    "X-BrokerAssist-Timestamp": timestamp, "X-BrokerAssist-Signature": signature})
with urllib.request.urlopen(req, timeout=10) as response:
    print(response.status)
```

The receiver limits events to 16 KiB, verifies HMAC with a five-minute timestamp window, validates schema, and responds with local ticket ID and duplicate status. Exact same normalized content and event ID is idempotent; changed content with reused ID returns 409. No account verification is inferred from integration input. Retry 5xx and network failures with backoff and a **new timestamp/signature but same event ID and content**; don't retry validation/authorization errors blindly. Integration service queues, source-specific signature verification, delivery monitoring and native sync remain to be implemented against the client's actual CRM.

## 5. Operate and recover

- Operator training: intake only authorized data; inspect policy evidence and draft; edit only within approved policy; never treat the model as an authority. Locally approve routine cases or route uncertain/sensitive issues to the actual company's specialist using its approved separate workflow. In-app approval/escalation only records a local state; nothing is sent automatically.
- Daily: check /api/metrics, admin /api/ops (caller quota and blocked decisions), infrastructure health, fallback frequency, access logs and manual specialist backlog. Set proxy/infra alerts and ownership before rollout. No orchestration, SLA or paging service is bundled.
- Backup: run `python -m app.backup /secure/backups/pilot-YYYYMMDD.db` under the same BROKERASSIST_DB settings. For Compose, use a private mounted backup target or operator-approved volume snapshot; the CLI needs a writable protected destination. This creates a consistent SQLite backup without overwriting and verifies integrity. Encrypt storage and backups using company infrastructure; verify permissions; store a separate recovery copy. Test restore in isolated staging.
- Restore: stop service; retain original database and any journal safely; restore a validated snapshot to a fresh owner-only database file on the dedicated volume; keep the same client ID; restart and verify counts, audit and sample approval. Never overwrite the running database. Set recovery point/time objectives and drill with the client.
- Revoke/incident: disable ingress, disable provider traffic, revoke signing or API credentials as applicable, preserve authorized incident evidence, notify the named client owner, restore last approved configuration/release. Investigate and add regression tests. No customer response is sent by this app.
- Data lifecycle: company must approve storage region, data classes, retention/deletion/export and backup disposal. No automated retention or legal-hold service is bundled. Snapshot, export or delete records only under approved procedures. SQLite is a single-node store for a small controlled pilot; load-test and consider a managed database/queue before scaling.

See [acceptance gates](pilot_acceptance.md), [release and operations](llm_release_and_operations.md), and [safety boundaries](safety_boundaries.md).
