from dataclasses import dataclass, field
from datetime import datetime

import anyio

from qinora.application.read_models import (
    AgentLogRecord,
    ParsedCargoLine,
    ParsedTransportRequestDraft,
    RequestRecord,
)
from qinora.application.request_intake import CreateRequestUseCase
from qinora.application.request_parsing_agent import (
    ParseFreeTextRequestCommand,
    RequestParsingAgent,
)


@dataclass
class FakeRequestParsingLLM:
    """Test double for RequestParsingLLM - returns a canned draft instead
    of calling LangChain/Azure OpenAI, so these tests run offline and fast.
    """

    draft: ParsedTransportRequestDraft

    async def parse(self, *, raw_text: str) -> ParsedTransportRequestDraft:
        _ = raw_text
        return self.draft


@dataclass
class FakeRequestWriteRepository:
    created: list[dict] = field(default_factory=list)

    async def create_transport_request(
        self, *, customer, lane, request, status, review_reason
    ) -> RequestRecord:
        self.created.append({"customer": customer, "lane": lane, "status": status})
        return RequestRecord(
            id="req-1",
            public_id="REQ-0001",
            customer=customer,
            lane=lane,
            mode=request.mode.value,
            status=status,
            weight_kg=sum(c.weight_kg or 0 for c in request.cargo),
        )


@dataclass
class FakeOperationalTaskWriteRepository:
    async def create_task(self, *, entity_type, entity_id, reason, priority="normal"):
        return None


@dataclass
class FakeAgentLogWriteRepository:
    logs: list[AgentLogRecord] = field(default_factory=list)

    async def record(self, *, agent_key, agent_name, step, entity_id, confidence):
        log = AgentLogRecord(
            agent_key=agent_key,
            agent_name=agent_name,
            step=step,
            entity_id=entity_id,
            confidence=confidence,
        )
        self.logs.append(log)
        return log


def _agent(
    draft: ParsedTransportRequestDraft,
) -> tuple[RequestParsingAgent, FakeAgentLogWriteRepository]:
    request_repo = FakeRequestWriteRepository()
    create_request = CreateRequestUseCase(request_repo, FakeOperationalTaskWriteRepository())
    agent_logs = FakeAgentLogWriteRepository()
    agent = RequestParsingAgent(FakeRequestParsingLLM(draft), create_request, agent_logs)
    return agent, agent_logs


def test_high_confidence_complete_draft_creates_request() -> None:
    draft = ParsedTransportRequestDraft(
        mode="ftl",
        origin="Gothenburg",
        destination="Malmo",
        cargo=(ParsedCargoLine("Pallets", 4, 800.0, 120, 100, 150),),
        loading_time=datetime(2026, 8, 1, 8, 0),
        unloading_time=datetime(2026, 8, 2, 8, 0),
        confidence=0.9,
        missing_fields=(),
    )
    agent, agent_logs = _agent(draft)

    async def run():
        return await agent.execute(
            ParseFreeTextRequestCommand(customer="Acme AB", raw_text="ignored by fake")
        )

    result = anyio.run(run)

    assert result.needs_human_review is False
    assert result.request_result is not None
    assert result.request_result.request.customer == "Acme AB"
    assert agent_logs.logs[0].confidence == 0.9
    assert agent_logs.logs[0].agent_key == "request_parsing_agent"


def test_low_confidence_draft_is_flagged_not_created() -> None:
    draft = ParsedTransportRequestDraft(
        mode="ftl",
        origin="",
        destination="",
        cargo=(),
        loading_time=None,
        unloading_time=None,
        confidence=0.1,
        missing_fields=("origin", "destination", "cargo"),
    )
    agent, agent_logs = _agent(draft)

    async def run():
        return await agent.execute(
            ParseFreeTextRequestCommand(customer="Acme AB", raw_text="vague email")
        )

    result = anyio.run(run)

    assert result.needs_human_review is True
    assert result.request_result is None
    assert "flagged for review" in agent_logs.logs[0].step


def test_missing_fields_forces_review_even_with_high_confidence() -> None:
    draft = ParsedTransportRequestDraft(
        mode="ftl",
        origin="Gothenburg",
        destination="Malmo",
        cargo=(ParsedCargoLine("Pallets", 4, 800.0, 120, 100, 150),),
        loading_time=None,
        unloading_time=None,
        confidence=0.95,
        missing_fields=("loading_time",),
    )
    agent, _ = _agent(draft)

    async def run():
        return await agent.execute(
            ParseFreeTextRequestCommand(customer="Acme AB", raw_text="partial info")
        )

    result = anyio.run(run)

    assert result.needs_human_review is True
    assert result.request_result is None
