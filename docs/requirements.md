# Discovery and scoping — fictional engagement

## Client problem
A brokerage support lead wants to reduce repetitive drafting work while maintaining policy consistency and specialist routing. We are not replacing the operator or approving financial actions.

## Discovery checklist (questions to ask a real client)
- Which channels and CRM create requests? Which fields are reliable and permitted?
- What are the top ticket intents, volumes, time-to-first-response, resolution times and current QA rules?
- Who owns each policy? How are changes versioned and approved?
- Which cases must never be auto-resolved? Who can authenticate a customer and review a transaction?
- What is the failure mode if a CRM or model is unavailable?
- What privacy, audit, data retention and deployment obligations apply?
- What are measurable acceptance criteria, and who signs off?

## Assumptions
The demo uses synthetic data, English text, a small static approved corpus, one operator, a local database and no real account permissions. Finance/Compliance/Security/Trading Operations routes are internal simulations.

## In scope
- Receive/manual-create ticket; CRM-compatible webhook with deduplication
- Retrieve policy, classify risk, draft response, inspect evidence
- Read fictional transaction status only when seeded verified context matches
- Review/edit/approve routine drafts or escalate specialist cases
- Record operator decisions and exceptions; demonstrate metrics and tests
- Optional read-only LLM policy call and Zendesk sandbox import

## Explicitly out of scope
Live fund movements, trading advice, document verification, password reset, live sends, multi-tenant auth, public deployment, omnichannel voice, automated refund/withdrawal approval and production compliance certification.

## Acceptance criteria
1. An unknown request asks for clarification rather than inventing policy.
2. Deposit, withdrawal, KYC, security and execution dispute cases are escalated.
3. A routine MT5 case provides KB-001 evidence and approval is an explicit user action.
4. Repeated webhook IDs never create duplicate tickets.
5. Unverified customer text cannot authorize an account lookup.
6. All model tool calls are strictly limited to the selected fictional policy.
7. Provider failures produce the deterministic fallback.
8. Decisions and analysis are persisted locally with audit records.
9. The test dataset and results are reproducible. Real-world thresholds require separate independent evaluation.

## Milestones
M1: Requirements and fictional knowledge base. M2: API, retrieval and safe draft. M3: tool/review flow and CRM intake. M4: testing, runbook and demo. M5 (future): client sandbox and production rollout following client approval.
