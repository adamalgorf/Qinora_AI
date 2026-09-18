# RFQ analysis

`POST /api/rfq/analyze` runs an RFQ document through a three-step
**extract -> compare -> recommend** analysis against a reference
specification, and returns the full `decision_path` alongside the result so
the reasoning is never a black box.

## How it fits the existing architecture

This follows the same ports-and-adapters shape as the rest of `qinora`
(compare Nora/Quinn/Orion, the existing OpenAI-backed agents):

| Layer | File | Role |
|---|---|---|
| Port | [`application/llm_ports.py`](../src/qinora/application/llm_ports.py) | `GraphExecutor` protocol + generic `LLMRequest`/`LLMResponse` |
| DTOs | [`application/llm_dtos.py`](../src/qinora/application/llm_dtos.py) | `RFQAnalysisRequest` / `RFQAnalysisResponse` |
| Use case | [`application/analyze_rfq.py`](../src/qinora/application/analyze_rfq.py) | `AnalyzeRFQUseCase` - translates DTOs to/from the port, has zero OpenAI imports |
| Adapters | [`infrastructure/llm/graph_executor.py`](../src/qinora/infrastructure/llm/graph_executor.py) | `StubGraphExecutor` (default), `OpenAIGraphExecutor` (real) |
| DI | [`interfaces/http/container.py`](../src/qinora/interfaces/http/container.py) | `build_graph_executor()` picks the adapter from `LLM_PROVIDER` |
| HTTP | [`interfaces/http/routers/rfq.py`](../src/qinora/interfaces/http/routers/rfq.py) | `POST /rfq/analyze` (reachable externally as `/api/rfq/analyze` through the nginx proxy, same as every other route) |

`AnalyzeRFQUseCase` only ever depends on the `GraphExecutor` protocol, so it
has no idea whether it's talking to the stub or to OpenAI.

## Configuration

This reuses the **same** `LLM_PROVIDER`/`OPENAI_API_KEY`/`OPENAI_MODEL`
settings as Nora, Quinn, and Orion - there's no separate
provider switch or extra credential for this feature:

```
LLM_PROVIDER=stub   # or openai
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
```

- `stub` (default): `StubGraphExecutor` - deterministic, zero credentials,
  always returns `decision: needs_human_review` at `confidence_score: 0.0`
  so it's unmistakable in development.
- `openai`: `OpenAIGraphExecutor` - three sequential structured calls
  through `OpenAIStructuredClient` (the same helper the other three agents
  use), no extra dependency beyond the `openai` package this project
  already requires.

## The graph

Each step is a structured OpenAI call, threaded into the next:

1. **extract** - pulls key fields + a summary out of `document_text`.
2. **compare** - checks the extraction against `reference_spec`, listing
   differences.
3. **recommend** - `approve` / `reject` / `needs_human_review`, with a reason
   and a confidence score.

`OpenAIGraphExecutor.run()` just awaits these three calls in order and
appends to `decision_path` as it goes - there's no separate graph library;
it's the same narrow, no-framework pattern already used by every other
LLM-backed agent in this codebase (see `infrastructure/llm/request_parsing.py`).

## Extending it

- **Add a step** (e.g. a `flag_compliance_risk` call between compare and
  recommend): add a schema, call `client.complete(...)` with it, append to
  `decision_path`. Mirror the new step in `StubGraphExecutor`'s
  `decision_path` too, so the two adapters' output shapes stay in sync for
  tests/consumers that don't care which one is live.
- **Add a new graph-based use case**: reuse the `GraphExecutor` port - don't
  add a second protocol. Give the new use case its own DTOs (mirror
  `llm_dtos.py`) and either add a method to `GraphExecutor` or, if the step
  sequence is genuinely different, build a second adapter pair (e.g.
  `StubXExecutor`/`OpenAIXExecutor`) behind the same protocol shape.
- **Swap models**: change `OPENAI_MODEL`, no code changes needed.

## Testing

[`tests/test_graph_executor.py`](../tests/test_graph_executor.py) covers
both adapters, using `anyio.run()` (this project's convention - not
`pytest.mark.asyncio`):

- `StubGraphExecutor` end-to-end, directly and via `AnalyzeRFQUseCase`.
- `OpenAIGraphExecutor` raises `RuntimeError` without `OPENAI_API_KEY`.
- `OpenAIGraphExecutor` runs the full extract/compare/recommend sequence
  with `OpenAIStructuredClient` monkeypatched to a fake that returns canned
  structured responses - no real OpenAI call, no API key needed to run the
  test suite.
