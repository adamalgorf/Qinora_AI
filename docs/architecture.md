# QiNora TMS Architecture

QiNora is implemented with a Python backend and TypeScript frontend, following clean architecture boundaries.
The product is workflow-first, not an always-on multi-agent system: deterministic use cases own
the core transport lifecycle, and AI should be introduced only for narrow tasks where it clearly
beats rules and structured parsing.

## Layers

- `backend/src/qinora/domain`: pure business rules, entities, value objects, status machines, validations, and deterministic scoring. It has no framework, database, HTTP, or LLM dependencies.
- `backend/src/qinora/application`: use cases and ports. Use cases depend on domain rules and abstract repositories/gateways.
- `backend/src/qinora/infrastructure`: adapters for SQLite/Postgres persistence, migrations, queues, email relays, and clocks.
- `backend/src/qinora/interfaces/http`: FastAPI routes, signed Bearer auth, HMAC webhooks, idempotency, and HTTP DTO mapping.
- `backend/src/qinora/interfaces/http/routers`: feature routers that keep HTTP endpoints modular.
- `backend/src/qinora/interfaces/http/container.py`: composition root for application use cases and infrastructure adapters.
- `backend/src/qinora/workers`: one-shot job entrypoints: Outlook mail bridge (inbound forwarding and real outbound sending), carrier RFQ collection, tracking simulation and invoice audit, and stale escalation. `outbound_mailer` is a test double, not a real sender.
- `frontend/src`: React/Vite operator interface with feature slices.
- `backend/migrations`: numbered Postgres schema migrations (the SQLite adapter mirrors the schema for local development).
- `docker-compose.yml`: local full-stack deployment wiring an Nginx container serving the React build, FastAPI, the workers and SQLite volume persistence (optional Postgres and Outlook-bridge profiles).
- `infra/gcp`: Terraform for production on Google Cloud (see `infra/gcp/README.md`).

The local development adapter uses SQLite so the app runs without external services. Production
persistence is Postgres (Cloud SQL) using the schema in `backend/migrations`, behind the same application ports.
`QINORA_PERSISTENCE` selects the adapter in the composition root; HTTP routes and use cases do
not know which database is active.

## Dependency Rule

Outer layers may depend inward. Inner layers must not import outer layers.

```text
interfaces/http -> application -> domain
infrastructure -> application/domain
workers -> application
frontend -> HTTP API contract
```

## Stack

- Backend API: Python 3.12+, FastAPI, Pydantic v2, psycopg 3 (raw SQL), bcrypt for passwords, OpenAI SDK for the agents (or a deterministic stub)
- Backend tests: pytest
- Workers: Python async workers behind application ports
- Frontend: TypeScript, React 19, Vite 7, Tailwind CSS 4, shadcn/Radix components, React Query, React Router
- Local container runtime: Docker Compose with Nginx proxying `/api` to FastAPI
- Production: Cloud Run (API and worker jobs), Cloud SQL Postgres, GCS + Cloud CDN for the static frontend and an external HTTPS load balancer routing `/api/*` to Cloud Run, all defined in Terraform
- Mail: Microsoft 365 / Outlook via Graph (`workers/outlook_bridge.py`); the Gmail Apps Script bridge is legacy

## Core Rules Captured First

- Shipment status transitions are encoded as a domain FSM.
- Request intake validation checks weight, dimensions, timing, and ADR UN-number detection.
- Incomplete request intake creates `operational_tasks` for Control Tower exception handling.
- Stale request escalation finds old `needs_clarification` requests and creates idempotent high-priority Control Tower tasks.
- Shipment status updates write `shipment_events` through an application workflow for case timeline auditability.
- Manual shipment overrides reuse the shipment workflow and require an operator reason in the timeline.
- Quote sending is blocked when the customer price is less than or equal to zero.
- Successful quote sending enqueues `outbound_reply_queue` records after the pricing gate passes.
- Quote details expose persistent line items and a commercial timeline built from outbound and customer reply events.
- Quote replies are interpreted by `QuoteResponseWorkflow`, recording reply events and routing accepted, revised, or rejected quotes.
- Inbound email senders are matched to CRM contacts by `ContactMatchingUseCase`, with Nora decisions persisted to `agent_logs`.
- Automation behavior is controlled through `AgentConfigService`, preserving enable flags, Auto Mode and confidence guard rails behind persistence ports.
- The outbound mail worker processes queued replies through an `OutboundMailer` port and records sent/failed status.
- The tracking simulator worker advances in-transit shipments, records shipment events, and creates invoice audits.
- Carrier intelligence is deterministic and stores confidence components for auditability.
- Email webhooks require HMAC and idempotency at the API boundary.
- HTTP auth accepts signed Bearer tokens and maps them into framework-free RBAC context.
- `/health` proves the HTTP process is alive; `/ready` verifies the active persistence adapter.
- The frontend calls the backend under `/api`: through the Vite proxy in development, Nginx in Docker Compose and the load balancer in production.
- SQLite and Postgres repositories implement the same application ports, preserving the dependency rule.

## Smoke-test flow

- `DemoFlowUseCase` is a thin application-layer orchestration over existing use cases.
- `POST /demo/flow` runs a complete request-to-invoice scenario as a backend smoke test. It is no longer exposed in the UI.
- The flow is deterministic: request validation, pricing gate, carrier scoring, shipment FSM and invoice audit all run through ordinary domain/application rules.
