# Costly mistakes and explicit system boundaries

BrokerAssist is an executable, local-first portfolio product. It is not a production brokerage, and it is intentionally incapable of sending customer messages or moving funds. Every account, transaction, ticket and policy is synthetic. The LLM provider and CRM integrations require separate authorized testing before live adoption.

## Threat model and enforcement

| What can go wrong | Enforced behavior | Where implemented |
|---|---|---|
| An ordinary platform question hides a withdrawal, deposit or KYC issue | Separate high-risk scan runs before any model call; the case must go to specialist review | guardrails.py, engine.py |
| A customer attempts to bypass instructions or impersonate an administrator | Common prompt-injection patterns (including full-width text and zero-width characters) route to Security | guardrails.py |
| A customer claims to be verified or asks about another person's transaction | Verification comes from trusted synthetic context, not user input; the tool checks identity, reference, matching transaction type, and disallows multiple sensitive intents | engine.py |
| A request asks for account change, position mutation or bonus activation | Specialist escalation; no mutation tool exists | guardrails.py, engine.py |
| A model asks for a password or claims a payment was completed | Output rules block known unsafe patterns, retain safe offline fallback and record the blocked validation | guardrails.py, engine.py |
| An operator edits a draft to include an unsafe request or claim | API validates the final text independently; rejects with HTTP 409 and records a blocked-decision audit event | store.py |
| An analysis generated with old rules is reused | API recomputes deterministic risk at approval; stale routine analysis must be regenerated; sensitive requests stay blocked | store.py |
| A duplicated CRM event arrives | Unique event ID, shared secret, and transaction protect demo intake | store.py, main.py |
| A model/CRM call fails | Provider path fails safely to a deterministic draft; no automatic external actions | engine.py |

### Capability boundaries
- Routine account/platform/policy explanation: retrieve an approved fictional policy, optionally ask the LLM for a draft, require human approval. Approval only persists a local draft.
- Deposit, withdrawal, security, KYC, trading disputes, financial advice, changes to accounts/promotions or trade orders: specialist escalation, no LLM generation. A verified matching synthetic transaction status is read-only and permitted only in the bounded transaction path.
- Missing knowledge: clarification, not invented instructions. No financial advice.
- No tool exists to send a message, transfer funds, make trades, edit real balances, verify identities or reset credentials.
- Decisions are enforced in backend code regardless of the UI. Rules have a version; existing open tickets must be re-analyzed when their saved guardrail version is stale. Historical finalized tickets are unchanged.

The rule-based detector is deliberately conservative, English-focused and not exhaustive; it may over-escalate benign wording and fail to detect novel paraphrases, unsafe semantic statements or multilingual attacks. Even a candidate that passes every test must receive human review. Basic redaction is not comprehensive DLP. Authentication, access control, tenancy and native signed CRM webhooks remain required before operating on real records. Do not expose local mode. A separate restricted, password-protected hosted offline mode is available for synthetic portfolio reviewers only; see [live setup](live_setup.md).

## Measured release evidence

- 50 original synthetic golden cases, preserved unchanged; baseline regression gate has zero detected regressions.
- 20 additional adversarial/routine control cases, primarily tested through HTTP API and one trusted-context test. The suite tests mixed-intent masking, multiple sensitive intents, wrong transaction type, credential disclosure, common injection patterns, mandatory escalation, blocked approvals and normal approvals.
- Output-guardrail tests exercise intentionally unsafe mocked model responses and direct operator-edited drafts; negative controls show that valid safety warnings are not blocked.
- 11 synthetic mocked LLM contract cases; no live model credentials or customer data used.
- End-to-end browser smoke workflow exercises the operator UI with real browser automation; see GitHub Actions for the actual run result. A workflow configuration alone is not proof of a successful run.

Run the verification from the repository root:

```bash
python -m unittest discover -s tests -v
python -m evaluations.regression --reviewed-drafts evaluations/reviewed_drafts.json
python -m evaluations.safety
python -m evaluations.llm_probe --mode mock
python tests/browser_smoke.py  # after installing playwright and its Chromium browser
```

See [safety cases](../evaluations/safety_cases.json), [measured safety report](../evaluations/safety_report.json), [release operations](llm_release_and_operations.md), and [risk assessment](risk_assessment.md). For a real pilot, engage policy owners to create independent adversarial scenarios, review LLM outputs, obtain authorized CRM sandbox access, verify auth and privacy, and agree on incident/rollback procedures before deployment.
