from dataclasses import dataclass, field

import anyio

from qinora.application.agent_config import AgentAutoMode, AgentConfigService
from qinora.application.carrier_offer_agent import (
    AGENT_KEY,
    CarrierOfferParsingAgent,
    ParseCarrierOfferCommand,
)
from qinora.application.read_models import (
    AgentConfigRecord,
    AgentLogRecord,
    CarrierOfferRecord,
    ParsedCarrierOfferDraft,
)


@dataclass
class FakeCarrierOfferParsingLLM:
    draft: ParsedCarrierOfferDraft

    async def parse(self, *, raw_text: str) -> ParsedCarrierOfferDraft:
        _ = raw_text
        return self.draft


@dataclass
class FakeCarrierOfferWriteRepository:
    created: list[dict] = field(default_factory=list)

    async def create_offer(
        self, *, request_id, carrier_name, price, currency, transit_days, notes, confidence
    ) -> CarrierOfferRecord:
        self.created.append({"request_id": request_id, "carrier_name": carrier_name})
        return CarrierOfferRecord(
            id="offer-1",
            request_id=request_id,
            carrier_name=carrier_name,
            price=price,
            currency=currency,
            transit_days=transit_days,
            notes=notes,
            confidence=confidence,
            created_at="2026-01-01T00:00:00",
        )

    async def list_offers_for_request(self, request_id: str) -> list[CarrierOfferRecord]:
        return [
            CarrierOfferRecord(
                id="offer-1",
                request_id=request_id,
                carrier_name="Nordic Freight",
                price=8500.0,
                currency="SEK",
                transit_days=2,
                notes=None,
                confidence=0.9,
                created_at="2026-01-01T00:00:00",
            )
        ]


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
class FakeAgentConfigRepository:
    configs: list[AgentConfigRecord]

    async def list_configs(self) -> list[AgentConfigRecord]:
        return self.configs

    async def update_config(self, **kwargs):
        raise NotImplementedError


def _agent(
    draft: ParsedCarrierOfferDraft,
    auto_mode: AgentAutoMode = AgentAutoMode.GUARDED_AUTO,
    min_confidence: float = 0.7,
) -> tuple[CarrierOfferParsingAgent, FakeAgentLogWriteRepository, FakeCarrierOfferWriteRepository]:
    offers = FakeCarrierOfferWriteRepository()
    agent_logs = FakeAgentLogWriteRepository()
    agent_config = AgentConfigService(
        FakeAgentConfigRepository(
            configs=[
                AgentConfigRecord(
                    agent_key=AGENT_KEY,
                    agent_name="Remy Rates",
                    is_enabled=True,
                    auto_mode=auto_mode.value,
                    min_confidence=min_confidence,
                )
            ]
        )
    )
    agent = CarrierOfferParsingAgent(
        FakeCarrierOfferParsingLLM(draft), offers, agent_logs, agent_config
    )
    return agent, agent_logs, offers


def test_high_confidence_offer_is_saved() -> None:
    draft = ParsedCarrierOfferDraft(
        carrier_name="Nordic Freight",
        price=8500.0,
        currency="SEK",
        transit_days=2,
        notes=None,
        confidence=0.9,
        missing_fields=(),
    )
    agent, agent_logs, offers = _agent(draft)

    async def run():
        return await agent.execute(
            ParseCarrierOfferCommand(request_id="req-1", raw_text="8500 SEK, 2 days")
        )

    result = anyio.run(run)

    assert result.needs_human_review is False
    assert result.offer is not None
    assert result.offer.carrier_name == "Nordic Freight"
    assert offers.created[0]["request_id"] == "req-1"
    assert agent_logs.logs[0].confidence == 0.9


def test_low_confidence_offer_is_flagged_not_saved() -> None:
    draft = ParsedCarrierOfferDraft(
        carrier_name="",
        price=None,
        currency=None,
        transit_days=None,
        notes=None,
        confidence=0.1,
        missing_fields=("carrier_name", "price"),
    )
    agent, agent_logs, offers = _agent(draft)

    async def run():
        return await agent.execute(
            ParseCarrierOfferCommand(request_id="req-1", raw_text="vague reply")
        )

    result = anyio.run(run)

    assert result.needs_human_review is True
    assert result.offer is None
    assert offers.created == []
    assert "flagged for review" in agent_logs.logs[0].step


def test_manual_mode_always_requires_review() -> None:
    draft = ParsedCarrierOfferDraft(
        carrier_name="Nordic Freight",
        price=8500.0,
        currency="SEK",
        transit_days=2,
        notes=None,
        confidence=1.0,
        missing_fields=(),
    )
    agent, _, offers = _agent(draft, auto_mode=AgentAutoMode.MANUAL)

    async def run():
        return await agent.execute(
            ParseCarrierOfferCommand(request_id="req-1", raw_text="clear reply")
        )

    result = anyio.run(run)

    assert result.needs_human_review is True
    assert result.offer is None
    assert offers.created == []


def test_list_for_request_returns_saved_offers() -> None:
    draft = ParsedCarrierOfferDraft(
        carrier_name="Nordic Freight",
        price=8500.0,
        currency="SEK",
        transit_days=2,
        notes=None,
        confidence=0.9,
        missing_fields=(),
    )
    agent, _, _ = _agent(draft)

    async def run():
        return await agent.list_for_request("req-1")

    offers = anyio.run(run)

    assert len(offers) == 1
    assert offers[0].carrier_name == "Nordic Freight"
