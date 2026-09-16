from pathlib import Path

import anyio
import pytest

import qinora.infrastructure.llm.graph_executor as graph_executor_module
from qinora.application.analyze_rfq import AnalyzeRFQUseCase
from qinora.application.llm_dtos import RFQAnalysisRequest
from qinora.application.llm_ports import LLMRequest
from qinora.infrastructure.llm.graph_executor import (
    NODE_COMPARE,
    NODE_EXTRACT,
    NODE_RECOMMEND,
    OpenAIGraphExecutor,
    StubGraphExecutor,
)
from qinora.infrastructure.settings import LLMProvider, PersistenceDriver, Settings

_CANNED_RESPONSES = {
    "_ExtractedFields": {"summary": "10 pallets, Stockholm to Hamburg", "fields": {"mode": "ftl"}},
    "_Comparison": {"matches_reference": True, "differences": []},
    "_Recommendation": {"decision": "approve", "reason": "matches spec", "confidence": 0.95},
}


class _FakeOpenAIStructuredClient:
    """Stands in for OpenAIStructuredClient so tests never make a real
    OpenAI call - returns a canned structured response keyed by the
    requested schema.
    """

    def __init__(self, *args, **kwargs) -> None:
        _ = args, kwargs

    async def complete(self, *, system_prompt: str, user_text: str, schema):
        _ = system_prompt, user_text
        canned = _CANNED_RESPONSES[schema.__name__]
        return schema(**canned)


def _settings(*, openai_api_key: str | None) -> Settings:
    return Settings(
        email_webhook_secret="secret",
        sqlite_path=Path("qinora.test.sqlite3"),
        auth_token_secret="auth-secret",
        persistence_driver=PersistenceDriver.SQLITE,
        database_url=None,
        postgres_tenant_id="11111111-1111-1111-1111-111111111111",
        cors_allowed_origins=("*",),
        require_auth=False,
        llm_provider=LLMProvider.OPENAI,
        openai_api_key=openai_api_key,
        openai_model="gpt-4o-mini",
        default_markup_percent=10.0,
        customer_mailbox=None,
        carrier_mailbox=None,
    )


def test_stub_graph_executor_flags_needs_human_review() -> None:
    async def run():
        return await StubGraphExecutor().run(
            LLMRequest(
                prompt="doc",
                input_data={"document_text": "10 pallets to Hamburg", "reference_spec": "FTL only"},
            )
        )

    result = anyio.run(run)

    assert result.decision_path == [NODE_EXTRACT, NODE_COMPARE, NODE_RECOMMEND]
    assert result.confidence_score == 0.0
    assert result.output_data["recommendation"]["decision"] == "needs_human_review"


def test_analyze_rfq_use_case_end_to_end_with_stub_adapter() -> None:
    use_case = AnalyzeRFQUseCase(StubGraphExecutor())

    async def run():
        return await use_case.execute(
            RFQAnalysisRequest(document_text="10 pallets to Hamburg", reference_spec="FTL only")
        )

    result = anyio.run(run)

    assert result.decision_path == [NODE_EXTRACT, NODE_COMPARE, NODE_RECOMMEND]
    assert result.confidence_score == 0.0
    assert "recommendation" in result.extracted_data


def test_openai_graph_executor_requires_api_key() -> None:
    executor = OpenAIGraphExecutor(_settings(openai_api_key=None))

    async def run():
        return await executor.run(LLMRequest(prompt="doc", input_data={"document_text": "x"}))

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY is not set"):
        anyio.run(run)


def test_openai_graph_executor_runs_full_graph_with_mocked_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        graph_executor_module, "OpenAIStructuredClient", _FakeOpenAIStructuredClient
    )
    executor = OpenAIGraphExecutor(_settings(openai_api_key="test-key"))

    async def run():
        return await executor.run(
            LLMRequest(
                prompt="doc",
                input_data={"document_text": "10 pallets to Hamburg", "reference_spec": "FTL only"},
            )
        )

    result = anyio.run(run)

    assert result.decision_path == [NODE_EXTRACT, NODE_COMPARE, NODE_RECOMMEND]
    assert result.confidence_score == 0.95
    assert result.output_data["recommendation"]["decision"] == "approve"
    assert result.output_data["comparison"]["matches_reference"] is True
