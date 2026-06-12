# QiNora TMS Architecture

QiNora is implemented with a Python backend and TypeScript frontend, following clean architecture boundaries.

## Layers

- `backend/src/qinora/domain`: pure business rules, entities, value objects, status machines, validations, and deterministic scoring. It has no framework, database, HTTP, or LLM dependencies.
- `backend/src/qinora/application`: use cases and ports. Use cases depend on domain rules and abstract repositories/gateways.
- `backend/src/qinora/infrastructure`: adapters for SQLite/Postgres persistence, migrations, queues, LLM providers, email relays, and clocks.
- `backend/src/qinora/interfaces/http`: FastAPI routes, signed Bearer auth, HMAC webhooks, idempotency, and HTTP DTO mapping.
- `backend/src/qinora/interfaces/http/routers`: feature routers that keep HTTP endpoints modular.
- `backend/src/qinora/interfaces/http/container.py`: composition root for application use cases and infrastructure adapters.
- `backend/src/qinora/workers`: scheduled and queued job entrypoints for agents, outbound email, tracking simulation, invoice audit, and stale escalation.
- `frontend/src`: React/Vite operator interface with feature slices.
- `backend/migrations`: Postgres/Supabase schema migrations.
- `docker-compose.yml`: local full-stack deployment wiring Nginx, React, FastAPI, and SQLite volume persistence.

The local development adapter uses SQLite so the app runs without external services. Production
persistence uses the Postgres schema in `backend/migrations`, behind the same application ports.
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

- Backend API: Python 3.12+, FastAPI, Pydantic v2
- Backend tests: pytest
- Workers: Python async workers behind application ports
- Frontend: TypeScript, React, Vite
- Container runtime: Docker Compose with Nginx proxying `/api` to FastAPI
- Database target: Postgres 15+ with RLS

## Core Rules Captured First

- Shipment status transitions are encoded as a domain FSM.
- Request intake validation checks weight, dimensions, timing, and ADR UN-number detection.
- Incomplete request intake creates `operational_tasks` for Control Tower exception handling.
- Shipment status updates write `shipment_events` through an application workflow for case timeline auditability.
- Manual shipment overrides reuse the shipment workflow and require an operator reason in the timeline.
- Quote sending is blocked when the customer price is less than or equal to zero.
- Successful quote sending enqueues `outbound_reply_queue` records after the pricing gate passes.
- Quote replies are interpreted by `QuoteResponseWorkflow`, recording reply events and routing accepted, revised, or rejected quotes.
- Inbound email senders are matched to CRM contacts by `ContactMatchingUseCase`, with Miles Match decisions persisted to `agent_logs`.
- Agent runtime behavior is controlled through `AgentConfigService`, preserving enable flags, Auto Mode and confidence guard rails behind persistence ports.
- The outbound mail worker processes queued replies through an `OutboundMailer` port and records sent/failed status.
- The tracking simulator worker advances in-transit shipments, records shipment events, and creates invoice audits.
- Carrier intelligence is deterministic and stores confidence components for auditability.
- Email webhooks require HMAC and idempotency at the API boundary.
- HTTP auth accepts signed Bearer tokens and maps them into framework-free RBAC context.
- Frontend modules consume backend API endpoints through the Vite `/api` proxy.
- SQLite and Postgres repositories implement the same application ports, preserving the dependency rule.
