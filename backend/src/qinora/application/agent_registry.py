"""The single source of truth for which AI agents exist and what they know.

Each agent is a *role* (Nora, Quinn, Orion - see qinora.se) that owns one or
more narrow LLM steps. The registry answers two questions for every role:

- which agent config row governs it (auto_mode / min_confidence), and
- which knowledge-base domains it reads before acting (application/knowledge.py).

Adding an agent is one AgentDefinition here plus its LLM adapter subclassing
KnowledgeGroundedLLM (infrastructure/llm/openai_client.py) - the agent config
row is seeded from DEFAULT_AGENT_CONFIGS (derived from AGENTS) and the
adapter reads its domains automatically. Moving a task between roles, or
widening what a role may read, is a one-line change here instead of a hunt
through prompts.
"""

from dataclasses import dataclass
from enum import StrEnum


class KnowledgeDomain(StrEnum):
    CUSTOMERS = "customers"
    ROUTES = "routes"
    CARRIERS = "carriers"
    TERMS = "terms"
    PROCEDURES = "procedures"
    GENERAL = "general"


@dataclass(frozen=True)
class KnowledgeDomainInfo:
    domain: KnowledgeDomain
    label: str
    description: str


KNOWLEDGE_DOMAINS: tuple[KnowledgeDomainInfo, ...] = (
    KnowledgeDomainInfo(
        KnowledgeDomain.CUSTOMERS,
        "Kunder",
        "Kundprofiler, fasta adresser, önskemål och särskilda krav.",
    ),
    KnowledgeDomainInfo(
        KnowledgeDomain.ROUTES,
        "Rutter",
        "Lanes, orter och terminaler, ledtider och restriktioner per sträcka.",
    ),
    KnowledgeDomainInfo(
        KnowledgeDomain.CARRIERS,
        "Transportörer",
        "Transportörernas kapacitet, styrkor, kontaktvägar och erfarenheter.",
    ),
    KnowledgeDomainInfo(
        KnowledgeDomain.TERMS,
        "Avtal & villkor",
        "Avtalsvillkor, betalningsvillkor, ansvar och tillägg. Priser hör hemma i "
        "prisprofilerna, inte här.",
    ),
    KnowledgeDomainInfo(
        KnowledgeDomain.PROCEDURES,
        "Rutiner",
        "Interna arbetssätt: hur ärenden hanteras, eskaleras och följs upp.",
    ),
    KnowledgeDomainInfo(
        KnowledgeDomain.GENERAL,
        "Allmänt",
        "Företagsinformation som alla agenter ska känna till.",
    ),
)

_DOMAIN_INFO = {info.domain: info for info in KNOWLEDGE_DOMAINS}


@dataclass(frozen=True)
class AgentDefinition:
    key: str
    name: str
    role: str
    knowledge_domains: frozenset[KnowledgeDomain]
    default_auto_mode: str
    default_min_confidence: float

    @property
    def readable_domains(self) -> frozenset[KnowledgeDomain]:
        """Every agent always reads GENERAL on top of its own domains."""
        return self.knowledge_domains | {KnowledgeDomain.GENERAL}


NORA = AgentDefinition(
    key="request_parsing_agent",
    name="Nora",
    role="Intake & validering",
    knowledge_domains=frozenset(
        {KnowledgeDomain.CUSTOMERS, KnowledgeDomain.ROUTES, KnowledgeDomain.PROCEDURES}
    ),
    default_auto_mode="guarded_auto",
    default_min_confidence=0.74,
)

QUINN = AgentDefinition(
    key="carrier_offer_agent",
    name="Quinn",
    role="Offert & bokning",
    knowledge_domains=frozenset(
        {
            KnowledgeDomain.CARRIERS,
            KnowledgeDomain.ROUTES,
            KnowledgeDomain.TERMS,
            KnowledgeDomain.CUSTOMERS,
        }
    ),
    default_auto_mode="guarded_auto",
    default_min_confidence=0.7,
)

ORION = AgentDefinition(
    key="quote_response_agent",
    name="Orion",
    role="Orkestrering & uppföljning",
    knowledge_domains=frozenset(
        {KnowledgeDomain.CUSTOMERS, KnowledgeDomain.TERMS, KnowledgeDomain.PROCEDURES}
    ),
    default_auto_mode="guarded_auto",
    default_min_confidence=0.7,
)

AGENTS: tuple[AgentDefinition, ...] = (NORA, QUINN, ORION)

_AGENTS_BY_KEY = {agent.key: agent for agent in AGENTS}


def get_agent(agent_key: str) -> AgentDefinition | None:
    return _AGENTS_BY_KEY.get(agent_key)


def agents_reading(domain: KnowledgeDomain) -> tuple[AgentDefinition, ...]:
    return tuple(agent for agent in AGENTS if domain in agent.readable_domains)


def domain_info(domain: KnowledgeDomain) -> KnowledgeDomainInfo:
    return _DOMAIN_INFO[domain]
