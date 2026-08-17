from dataclasses import dataclass, field

import anyio

from qinora.application.agent_config import AgentAutoMode, AgentConfigService
from qinora.application.read_models import (
    AgentConfigRecord,
    AgentLogRecord,
    ParsedCargoLine,
    ParsedTransportRequestDraft,
    RequestRecord,
)
from qinora.application.request_intake import CreateRequestUseCase
from qinora.application.request_parsing_agent import (
    AGENT_KEY,
    ParseFreeTextRequestCommand,
    RequestParsingAgent,
)


@dataclass
class FakeRequestParsingLLM:
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


@dataclass
class FakeClarificationOutboundRepository:
    enqueued: list[dict] = field(default_factory=list)

    async def enqueue(self, *, inbound_email_id, recipient, subject, body_text):
        item = {
            "inbound_email_id": inbound_email_id,
            "recipient": recipient,
            "subject": subject,
            "body_text": body_text,
        }
        self.enqueued.append(item)
        return item

    async def next_queued(self, limit):
        return []

    async def mark_sent(self, item_id):
        raise NotImplementedError

    async def mark_failed(self, item_id, error_message):
        raise NotImplementedError


@dataclass
class FakeAgentConfigRepository:
    configs: list[AgentConfigRecord]

    async def list_configs(self) -> list[AgentConfigRecord]:
        return self.configs

    async def update_config(self, **kwargs):
        raise NotImplementedError


def _agent(
    draft: ParsedTransportRequestDraft,
    auto_mode: AgentAutoMode = AgentAutoMode.GUARDED_AUTO,
    min_confidence: float = 0.74,
    is_enabled: bool = True,
) -> tuple[RequestParsingAgent, FakeAgentLogWriteRepository]:
    request_repo = FakeRequestWriteRepository()
    create_request = CreateRequestUseCase(request_repo, FakeOperationalTaskWriteRepository())
    agent_logs = FakeAgentLogWriteRepository()
    agent_config = AgentConfigService(
        FakeAgentConfigRepository(
            configs=[
                AgentConfigRecord(
                    agent_key=AGENT_KEY,
                    agent_name="Parsek",
                    is_enabled=is_enabled,
                    auto_mode=auto_mode.value,
                    min_confidence=min_confidence,
                )
            ]
        )
    )
    agent = RequestParsingAgent(
        FakeRequestParsingLLM(draft), create_request, agent_logs, agent_config
    )
    return agent, agent_logs


def test_high_confidence_complete_draft_creates_request() -> None:
    draft = ParsedTransportRequestDraft(
        mode="ftl",
        origin="Gothenburg",
        destination="Malmo",
        cargo=(ParsedCargoLine("Pallets", 4, 800.0, 120, 100, 150),),
        loading_time=None,
        unloading_time=None,
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
    assert agent_logs.logs[0].agent_key == AGENT_KEY


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


def test_manual_mode_always_requires_review_regardless_of_confidence() -> None:
    draft = ParsedTransportRequestDraft(
        mode="ftl",
        origin="Gothenburg",
        destination="Malmo",
        cargo=(ParsedCargoLine("Pallets", 4, 800.0, 120, 100, 150),),
        loading_time=None,
        unloading_time=None,
        confidence=1.0,
        missing_fields=(),
    )
    agent, _ = _agent(draft, auto_mode=AgentAutoMode.MANUAL)

    async def run():
        return await agent.execute(
            ParseFreeTextRequestCommand(customer="Acme AB", raw_text="clear email")
        )

    result = anyio.run(run)

    assert result.needs_human_review is True
    assert result.request_result is None


def test_missing_fields_queues_clarification_email_to_sender() -> None:
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
    request_repo = FakeRequestWriteRepository()
    create_request = CreateRequestUseCase(request_repo, FakeOperationalTaskWriteRepository())
    agent_logs = FakeAgentLogWriteRepository()
    agent_config = AgentConfigService(
        FakeAgentConfigRepository(
            configs=[
                AgentConfigRecord(
                    agent_key=AGENT_KEY,
                    agent_name="Parsek",
                    is_enabled=True,
                    auto_mode=AgentAutoMode.GUARDED_AUTO.value,
                    min_confidence=0.74,
                )
            ]
        )
    )
    clarifications = FakeClarificationOutboundRepository()
    agent = RequestParsingAgent(
        FakeRequestParsingLLM(draft),
        create_request,
        agent_logs,
        agent_config,
        clarification_outbound=clarifications,
    )

    async def run():
        return await agent.execute(
            ParseFreeTextRequestCommand(
                customer="Acme AB",
                raw_text="partial info",
                inbound_email_id="email-1",
                sender_email="customer@example.com",
                subject="Fraktforfraga",
            )
        )

    result = anyio.run(run)

    assert result.request_result is None
    assert len(clarifications.enqueued) == 1
    item = clarifications.enqueued[0]
    assert item["inbound_email_id"] == "email-1"
    assert item["recipient"] == "customer@example.com"
    assert item["subject"] == "Re: Fraktforfraga"
    assert "lastningstid" in item["body_text"].lower()


def test_not_relevant_email_does_not_queue_clarification() -> None:
    draft = ParsedTransportRequestDraft(
        mode="ftl",
        origin="",
        destination="",
        cargo=(),
        loading_time=None,
        unloading_time=None,
        confidence=0.9,
        missing_fields=(),
        action="not_relevant",
    )
    request_repo = FakeRequestWriteRepository()
    create_request = CreateRequestUseCase(request_repo, FakeOperationalTaskWriteRepository())
    agent_logs = FakeAgentLogWriteRepository()
    agent_config = AgentConfigService(
        FakeAgentConfigRepository(
            configs=[
                AgentConfigRecord(
                    agent_key=AGENT_KEY,
                    agent_name="Parsek",
                    is_enabled=True,
                    auto_mode=AgentAutoMode.GUARDED_AUTO.value,
                    min_confidence=0.74,
                )
            ]
        )
    )
    clarifications = FakeClarificationOutboundRepository()
    agent = RequestParsingAgent(
        FakeRequestParsingLLM(draft),
        create_request,
        agent_logs,
        agent_config,
        task_repository=FakeOperationalTaskWriteRepository(),
        clarification_outbound=clarifications,
    )

    async def run():
        return await agent.execute(
            ParseFreeTextRequestCommand(
                customer="Acme AB",
                raw_text="unsubscribe please",
                inbound_email_id="email-2",
                sender_email="customer@example.com",
                subject="Re: newsletter",
            )
        )

    result = anyio.run(run)

    assert result.not_relevant is True
    assert clarifications.enqueued == []


def test_disabled_agent_always_requires_review() -> None:
    draft = ParsedTransportRequestDraft(
        mode="ftl",
        origin="Gothenburg",
        destination="Malmo",
        cargo=(ParsedCargoLine("Pallets", 4, 800.0, 120, 100, 150),),
        loading_time=None,
        unloading_time=None,
        confidence=1.0,
        missing_fields=(),
    )
    agent, _ = _agent(draft, is_enabled=False)

    async def run():
        return await agent.execute(
            ParseFreeTextRequestCommand(customer="Acme AB", raw_text="clear email")
        )

    result = anyio.run(run)

    assert result.needs_human_review is True
    assert result.request_result is None
