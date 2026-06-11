from dataclasses import dataclass, field

from qinora.domain import (
    CarrierCandidate,
    CurrencyCode,
    Money,
    Quote,
    QuoteStatus,
    ShipmentStatus,
    TransportMode,
)


@dataclass(frozen=True)
class RequestRecord:
    id: str
    public_id: str
    customer: str
    lane: str
    mode: TransportMode
    status: str
    weight_kg: float


@dataclass(frozen=True)
class ShipmentRecord:
    id: str
    public_id: str
    quote_id: str
    carrier_id: str | None
    lane: str
    status: ShipmentStatus
    eta: str


@dataclass(frozen=True)
class AgentLogRecord:
    agent_key: str
    agent_name: str
    step: str
    entity_id: str
    confidence: float


@dataclass(frozen=True)
class InboxRecord:
    id: str
    sender: str
    subject: str
    received_at: str
    classification: str


@dataclass
class SeedDataStore:
    requests: list[RequestRecord] = field(default_factory=list)
    quotes: list[Quote] = field(default_factory=list)
    shipments: list[ShipmentRecord] = field(default_factory=list)
    carriers: list[CarrierCandidate] = field(default_factory=list)
    agent_logs: list[AgentLogRecord] = field(default_factory=list)
    inbox: list[InboxRecord] = field(default_factory=list)

    @classmethod
    def create(cls) -> "SeedDataStore":
        carriers = [
            CarrierCandidate(
                id="car-001",
                display_name="Nordic Freight",
                aliases=("Nordic", "NF"),
                modes=(TransportMode.FTL, TransportMode.LTL),
                lane_score=91,
                max_weight_kg=24000,
                performance_score=94,
                preferred=True,
                sample_size=112,
            ),
            CarrierCandidate(
                id="car-002",
                display_name="Baltic Logistics",
                aliases=("Baltic",),
                modes=(TransportMode.FTL, TransportMode.RAIL),
                lane_score=76,
                max_weight_kg=28000,
                performance_score=82,
                sample_size=48,
            ),
            CarrierCandidate(
                id="car-003",
                display_name="SkyBridge Cargo",
                aliases=("SkyBridge",),
                modes=(TransportMode.AIR,),
                lane_score=88,
                max_weight_kg=3200,
                performance_score=89,
                sample_size=36,
            ),
        ]

        return cls(
            requests=[
                RequestRecord(
                    "req-001",
                    "REQ-0001",
                    "Volvo Parts",
                    "Gothenburg -> Hamburg",
                    TransportMode.LTL,
                    "quoted",
                    820,
                ),
                RequestRecord(
                    "req-002",
                    "REQ-0002",
                    "Northvolt",
                    "Skelleftea -> Rotterdam",
                    TransportMode.FTL,
                    "parsing",
                    15500,
                ),
                RequestRecord(
                    "req-003",
                    "REQ-0003",
                    "Astra Nordic",
                    "Stockholm -> Oslo",
                    TransportMode.AIR,
                    "needs_clarification",
                    480,
                ),
            ],
            quotes=[
                Quote("quo-001", QuoteStatus.SENT, 1, Money(18400, CurrencyCode.SEK)),
                Quote("quo-002", QuoteStatus.DRAFT, 1, Money(0, CurrencyCode.SEK)),
                Quote("quo-003", QuoteStatus.ACCEPTED, 2, Money(7290, CurrencyCode.SEK), "quo-001"),
            ],
            shipments=[
                ShipmentRecord(
                    "shp-001",
                    "SHP-0001",
                    "quo-003",
                    "car-001",
                    "Gothenburg -> Hamburg",
                    ShipmentStatus.BOOKED,
                    "2026-06-13 14:00",
                ),
                ShipmentRecord(
                    "shp-002",
                    "SHP-0002",
                    "quo-004",
                    "car-002",
                    "Malmo -> Copenhagen",
                    ShipmentStatus.IN_TRANSIT,
                    "2026-06-12 09:30",
                ),
                ShipmentRecord(
                    "shp-003",
                    "SHP-0003",
                    "quo-005",
                    None,
                    "Stockholm -> Oslo",
                    ShipmentStatus.NEEDS_REVIEW,
                    "Pending",
                ),
            ],
            carriers=carriers,
            agent_logs=[
                AgentLogRecord(
                    "intake_agent",
                    "Nora Intake",
                    "Classified inbound request",
                    "REQ-0001",
                    0.94,
                ),
                AgentLogRecord(
                    "quote_agent",
                    "Quinn Quote",
                    "Pricing gate passed",
                    "QUO-0001",
                    0.88,
                ),
                AgentLogRecord(
                    "carrier_intelligence",
                    "Carrier Intelligence",
                    "Selected preferred carrier",
                    "SHP-0001",
                    0.81,
                ),
            ],
            inbox=[
                InboxRecord(
                    "mail-001",
                    "logistics@volvo.example",
                    "Quote request Hamburg",
                    "2026-06-11 09:12",
                    "transport_request",
                ),
                InboxRecord(
                    "mail-002",
                    "ops@northvolt.example",
                    "FTL Skelleftea",
                    "2026-06-11 10:04",
                    "transport_request",
                ),
                InboxRecord(
                    "mail-003",
                    "finance@carrier.example",
                    "Invoice INV-0007",
                    "2026-06-11 10:49",
                    "invoice",
                ),
            ],
        )
