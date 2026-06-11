# QiNora TMS Architecture

QiNora is implemented with a Python backend and TypeScript frontend, following clean architecture boundaries.

## Layers

- `backend/src/qinora/domain`: pure business rules, entities, value objects, status machines, validations, and deterministic scoring. It has no framework, database, HTTP, or LLM dependencies.
- `backend/src/qinora/application`: use cases and ports. Use cases depend on domain rules and abstract repositories/gateways.
- `backend/src/qinora/infrastructure`: adapters for persistence, queues, LLM providers, email relays, and clocks.
- `backend/src/qinora/interfaces/http`: FastAPI routes, auth, HMAC, idempotency, and HTTP DTO mapping.
- `backend/src/qinora/workers`: scheduled and queued job entrypoints for agents, outbound email, tracking simulation, invoice audit, and stale escalation.
- `frontend/src`: React/Vite operator interface with feature slices.
- `backend/migrations`: Postgres/Supabase schema migrations.

The local development adapter uses SQLite so the app runs without external services. Production
persistence is intended to use the Postgres schema in `backend/migrations`, behind the same
application ports.

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
- Database target: Postgres 15+ with RLS

## Core Rules Captured First

- Shipment status transitions are encoded as a domain FSM.
- Request intake validation checks weight, dimensions, timing, and ADR UN-number detection.
- Quote sending is blocked when the customer price is less than or equal to zero.
- Carrier intelligence is deterministic and stores confidence components for auditability.
- Email webhooks require HMAC and idempotency at the API boundary.
- Frontend modules consume backend API endpoints through the Vite `/api` proxy.
