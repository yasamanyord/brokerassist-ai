# Company pilot acceptance and forward-deployed delivery checklist

## Discovery (client call, before configuration)

| Question | Decision / owner to record |
|---|---|
| What repeated support task is expensive? | Target routine English-language policy questions; confirm ticket volume and current handling time. |
| Who is allowed to approve? | Client support owner and named operators; separate specialist escalation owner. |
| Which answers are authoritative? | Client policy owner supplies/version-controls all 12 policy slots and independently labels examples. |
| What is explicitly out of scope? | Funds, orders, financial advice, account changes, credential handling, identity verification, customer-message sending, CRM write-back. |
| What records are allowed? | Approved minimum-necessary fields; data processing, privacy, retention, security and access approvals. |
| What constitutes success? | Agree on routing, escalation recall, grounding, response quality, latency, fallback and human efficiency targets; do not invent production metrics. |
| When do we stop? | Any unauthorized action/access, missed safety-critical escalation, unsupported factual claim or privacy issue freezes rollout and triggers incident review. |

Assumption: one company, small controlled group of trained operators, HTTPS behind private access, dedicated persistent database, client-approved English policy corpus. Architecture and risk decisions are reusable with a new company-specific configuration and independent evals.

## Implemented vs. pending

| Area | Implementation/evidence | Pilot release gate |
|---|---|---|
| Scoping | Requirements, risk boundaries, this discovery checklist | Client sign-off still required |
| Working software | Python/FastAPI + JS UI, SQLite, local intake/analysis/review | Exercise staging with actual workflow owners |
| Retrieval + tools | Bounded lexical retrieval; scoped optional model tool calling; no sensitive model runs; no live transaction access | Client corpus, independent grounding review and live-model evaluation approved |
| Integration | HMAC-signed normalized intake, replay window, idempotency/conflict protection; synthetic OAuth CRM sandbox importer | Authorized real CRM relay, native event validation, retries and end-to-end test |
| Security | Individual scrypt credentials, admin/operator/viewer roles, dedicated client store, origin/JSON checks, stale revision protection, named audit | Private TLS proxy/rate limits, threat review, real access revocation and privacy approval |
| Release quality | Original 50 golden cases, 20 safety cases, 11 mocked provider scenarios; separate pilot integration/concurrency/recovery tests | Independent client evaluation; live sandbox and performance/abuse tests |
| Operations | Admin quota/blocked-decision metrics, consistent backup/restore CLI, deployment/runbook and local-only decisions | Monitoring alerts, retention policy, operator training, restore drill, rollback plan |
| Scalability | Single-company, single-node pilot | Load/soak testing, capacity planning, managed DB/queue/SSO if needed |
| Proof | Reproducible tests and CI evidence; public repository | Client pilot outcomes and production experience have not been demonstrated |

## Release process — proposed gates (agree with client)

1. Discovery and signoff; qualify data, use case, risk and scope.
2. Synthetic internal staging: all automated gates and real browser smoke; verify auth rejection, signed event retries, client database isolation, prohibited actions and backup/restore. Pin evaluated release commit, approve deployment config.
3. Independent acceptance dataset (proposed starting point 100–200 client-reviewed, anonymized cases, representative of supported intents and risk levels). Reserve held-out cases not used by implementers to tune rules. Include ambiguity, mixed intents, adversarial injection, unusual phrasing, unsupported languages, provider failure, incomplete or outdated policy, repeated events. The client can require more cases for infrequent high-risk scenarios. No universal test count proves safety.
4. Actual provider and CRM validation in authorized sandbox with synthetic content. Re-run a paired baseline/candidate LLM test across multiple runs; have independent human reviewers score factual grounding, completeness, policy compliance and escalations; capture actual latency/cost. Never treat a mock result as live accuracy.
5. Acceptance threshold proposal: no observed missed mandatory escalation, unauthorized access/tool/action, unsafe approved answer, or regression on held-out critical cases; agree with client on routine quality and latency targets; investigate false positives/negatives. Passing examples are evidence only, not a mathematical guarantee of zero risk.
6. Security and operations gate: company approves TLS/network/identity, privacy and retention, backups and restore drill, incident monitoring, owner and permissions; verify source-native CRM relay and credential revocation. Client reviews source and dependencies; run vulnerability scans, load and abuse tests against deployed environment.
7. Controlled pilot on approved minimum-necessary data (small named operator cohort, local approvals only). Compare human-reviewed outcomes to existing manual workflow, capture operator feedback, audit sample and review drift. No unattended decisions.
8. Expand only after signed acceptance. Any scope change (write-back, automated response, real money or account operation, multi-tenant hosting) requires new design authorization, risk assessment and release gates. Reuse policy schema, signed intake, release gate, safety cases and handoff templates.

## Handoff

Provide deployed commit, configuration/secret ownership, client policy revision, environment instructions, runbook, monitoring/on-call ownership, escalation list, access roster review, signed acceptance and rollback instructions. Record unresolved defects and measurable pilot outcomes with dates. A portfolio project, even with strong automation, is not proof of one year of operating LLM systems in real products.
