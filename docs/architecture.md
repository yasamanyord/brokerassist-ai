# Architecture and flow

## Components
- app/main.py: FastAPI routes, validation, same-origin frontend, webhook secret.
- app/store.py: SQLite schema, seeded tickets, atomic state transitions and audit records.
- app/guardrails.py: independent sensitive-intent scanning, normalized injection patterns, draft safety checks and versioned rules.
- app/engine.py: local lexical retrieval, fixed routes, injection patterns, redaction, simulated tool, optional model call.
- app/integrations/zendesk.py: optional read-only sandbox import.
- app/static/: HTML/CSS/JS, no external scripts, escaping of all interpolated text.
- data/: stable policy IDs, fictional approved snippets and synthetic conversations.
- evaluations/: expected intent/escalation with reproducible evaluator.

## Data flow
Incoming text -> basic redaction -> store -> retrieval and risk rules -> authorized read-only tool if applicable -> draft + source IDs -> operator review -> local decision and audit.

## State machine
New → In review → Approved OR Escalated. Finalized tickets cannot be re-analyzed or finalized again. Re-analysis before finalization is allowed. The API enforces mandatory escalation independently of UI, recalculates current risk before approval, rejects stale analysis and unsafe edited drafts, and audits blocked decisions.

The optional model path runs only for routine supported categories. The first Responses call forces the get_approved_policy tool. The app validates tool name and exact policy ID; the second Responses call passes only the retrieved policy as tool output and disables further tool calls. The model cannot access the account tool or make state decisions.

## Retrieval
Phrase overlap + weighted word overlap. Retrieval score is a ranking signal, not calibrated confidence. The recognized top policy controls the default draft. Security/prompt injection patterns override routing; advice patterns require escalation. The General policy handles unmatched requests. No vector DB or embeddings are required for the initial version.

## Reusable configuration
Policy records contain ID, title, category, keywords, policy text, and template. Routes and mandatory escalation categories are in engine.py. Integrations normalize external ticket payloads into local intake fields. To adapt to a new client, update authorized policies and risk rules, add test cases for them and require operator sign-off before use.

## Production architecture evolution
Secure API gateway and auth -> validated webhook -> queue -> analysis worker -> managed database -> review UI -> permissioned CRM write-back only after human approval. Add tracing, alerting, retries, versioned knowledge, independent holdout evals, role-based access, secure credentials and tenant isolation.
