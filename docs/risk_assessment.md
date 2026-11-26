# Risk assessment and safety boundaries

| Risk | Mitigation implemented | Remaining work |
|---|---|---|
| Hallucinated company rule | Approved fictional templates, source excerpt, no auto-send | Independent factuality and policy adherence review |
| Customer claims account verification | New intake cannot set verified context, strict seed identity/reference check | Real identity/CRM permission validation |
| Financial or KYC action | Mandatory specialist escalation enforced server-side | Real specialist queue and verified identity |
| Prompt injection | Basic pattern detection and model tools limited to approved policy | broader adversarial/multilingual evaluations, stronger isolation |
| Model fails or calls wrong tool | Bounded call, strict validation, deterministic fallback | live provider testing, latency monitoring, spend controls |
| Duplicate CRM event | Unique event ID + SQLite transaction | source-native signature, replay/timestamp policy, retry/backoff |
| PII leakage | Basic redaction + synthetic-only instructions | DLP, encryption, classification, retention, secure audit storage |
| Unauthorized operator | Local loopback, no real actions | Auth, role-based permissions, tenancy, CSRF/rate limiting |
| Incorrect classification or multi-intent ticket | Explicit routes and mandatory review | independent, diverse evals and human quality review |
| Database loss | Local persistence; demo volume | backup/restore, migration, recovery objectives |

This demo is not authorized to use real brokerage information. An operator must never treat a simulated transaction result as a real status, interpret this demo as trading advice, or share real account records. Do not make the localhost service public without a full security redesign.

Evals measure synthetic route accuracy, required escalation recall, citation presence and blocked unverified tools. They do not validate semantic correctness or production-readiness.
