import sqlite3
from pathlib import Path
from typing import Any
from uuid import uuid4

from qinora.application.read_models import (
    AgentLogRecord,
    CarrierRecord,
    InboxRecord,
    QuoteRecord,
    RequestRecord,
    ShipmentRecord,
)
from qinora.domain import TransportRequestInput


class SQLiteDatabase:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                create table if not exists webhook_events (
                  id text primary key,
                  idempotency_key text not null unique,
                  event_type text not null,
                  created_at text not null default current_timestamp
                );

                create table if not exists email_inbound (
                  id text primary key,
                  idempotency_key text not null unique,
                  sender text not null,
                  subject text not null,
                  body_text text not null,
                  classification text,
                  created_at text not null default current_timestamp
                );

                create table if not exists transport_requests (
                  id text primary key,
                  public_id text not null unique,
                  customer text not null,
                  lane text not null,
                  mode text not null,
                  status text not null,
                  weight_kg real not null,
                  review_reason text
                );

                create table if not exists request_cargo (
                  id text primary key,
                  request_id text not null,
                  description text not null,
                  quantity integer,
                  weight_kg real,
                  length_cm real,
                  width_cm real,
                  height_cm real,
                  hazardous integer not null default 0,
                  un_number text
                );

                create table if not exists quotes (
                  id text primary key,
                  status text not null,
                  version integer not null,
                  customer_price real not null,
                  currency text not null,
                  parent_quote_id text
                );

                create table if not exists shipments (
                  id text primary key,
                  public_id text not null unique,
                  quote_id text not null,
                  carrier_id text,
                  lane text not null,
                  status text not null,
                  eta text not null
                );

                create table if not exists carriers (
                  id text primary key,
                  display_name text not null,
                  aliases text not null,
                  modes text not null,
                  lane_score real not null,
                  max_weight_kg real,
                  performance_score real,
                  preferred integer not null,
                  sample_size integer not null
                );

                create table if not exists agent_logs (
                  id text primary key,
                  agent_key text not null,
                  agent_name text not null,
                  step text not null,
                  entity_id text not null,
                  confidence real not null,
                  created_at text not null default current_timestamp
                );
                """
            )
            _add_column_if_missing(
                connection,
                "transport_requests",
                "review_reason",
                "text",
            )
            self._seed(connection)

    def _seed(self, connection: sqlite3.Connection) -> None:
        if _count(connection, "transport_requests") > 0:
            return

        connection.executemany(
            """
            insert into transport_requests
              (id, public_id, customer, lane, mode, status, weight_kg)
            values (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "req-001",
                    "REQ-0001",
                    "Volvo Parts",
                    "Gothenburg -> Hamburg",
                    "ltl",
                    "quoted",
                    820,
                ),
                (
                    "req-002",
                    "REQ-0002",
                    "Northvolt",
                    "Skelleftea -> Rotterdam",
                    "ftl",
                    "parsing",
                    15500,
                ),
                (
                    "req-003",
                    "REQ-0003",
                    "Astra Nordic",
                    "Stockholm -> Oslo",
                    "air",
                    "needs_clarification",
                    480,
                ),
            ],
        )
        connection.executemany(
            """
            insert into quotes
              (id, status, version, customer_price, currency, parent_quote_id)
            values (?, ?, ?, ?, ?, ?)
            """,
            [
                ("quo-001", "sent", 1, 18400, "SEK", None),
                ("quo-002", "draft", 1, 0, "SEK", None),
                ("quo-003", "accepted", 2, 7290, "SEK", "quo-001"),
            ],
        )
        connection.executemany(
            """
            insert into shipments
              (id, public_id, quote_id, carrier_id, lane, status, eta)
            values (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "shp-001",
                    "SHP-0001",
                    "quo-003",
                    "car-001",
                    "Gothenburg -> Hamburg",
                    "booked",
                    "2026-06-13 14:00",
                ),
                (
                    "shp-002",
                    "SHP-0002",
                    "quo-004",
                    "car-002",
                    "Malmo -> Copenhagen",
                    "in_transit",
                    "2026-06-12 09:30",
                ),
                (
                    "shp-003",
                    "SHP-0003",
                    "quo-005",
                    None,
                    "Stockholm -> Oslo",
                    "needs_review",
                    "Pending",
                ),
            ],
        )
        connection.executemany(
            """
            insert into carriers
              (
                id, display_name, aliases, modes, lane_score, max_weight_kg,
                performance_score, preferred, sample_size
              )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("car-001", "Nordic Freight", "Nordic,NF", "ftl,ltl", 91, 24000, 94, 1, 112),
                ("car-002", "Baltic Logistics", "Baltic", "ftl,rail", 76, 28000, 82, 0, 48),
                ("car-003", "SkyBridge Cargo", "SkyBridge", "air", 88, 3200, 89, 0, 36),
            ],
        )
        connection.executemany(
            """
            insert into agent_logs
              (id, agent_key, agent_name, step, entity_id, confidence)
            values (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "log-001",
                    "intake_agent",
                    "Nora Intake",
                    "Classified inbound request",
                    "REQ-0001",
                    0.94,
                ),
                (
                    "log-002",
                    "quote_agent",
                    "Quinn Quote",
                    "Pricing gate passed",
                    "QUO-0001",
                    0.88,
                ),
                (
                    "log-003",
                    "carrier_intelligence",
                    "Carrier Intelligence",
                    "Selected preferred carrier",
                    "SHP-0001",
                    0.81,
                ),
            ],
        )
        connection.executemany(
            """
            insert into email_inbound
              (id, idempotency_key, sender, subject, body_text, classification)
            values (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "mail-001",
                    "seed-mail-001",
                    "logistics@volvo.example",
                    "Quote request Hamburg",
                    "Need LTL pickup",
                    "transport_request",
                ),
                (
                    "mail-002",
                    "seed-mail-002",
                    "ops@northvolt.example",
                    "FTL Skelleftea",
                    "Battery equipment shipment",
                    "transport_request",
                ),
                (
                    "mail-003",
                    "seed-mail-003",
                    "finance@carrier.example",
                    "Invoice INV-0007",
                    "Carrier invoice attached",
                    "invoice",
                ),
            ],
        )


class SQLiteWebhookEventRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    async def exists(self, idempotency_key: str) -> bool:
        with self._database.connect() as connection:
            row = connection.execute(
                "select 1 from webhook_events where idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
        return row is not None

    async def record(self, idempotency_key: str, event_type: str) -> None:
        with self._database.connect() as connection:
            connection.execute(
                """
                insert or ignore into webhook_events (id, idempotency_key, event_type)
                values (?, ?, ?)
                """,
                (str(uuid4()), idempotency_key, event_type),
            )


class SQLiteInboundEmailRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    async def save(
        self,
        *,
        idempotency_key: str,
        sender: str,
        subject: str,
        body_text: str,
    ) -> str:
        email_id = str(uuid4())
        with self._database.connect() as connection:
            connection.execute(
                """
                insert into email_inbound
                  (id, idempotency_key, sender, subject, body_text, classification)
                values (?, ?, ?, ?, ?, ?)
                """,
                (email_id, idempotency_key, sender, subject, body_text, "pending"),
            )
        return email_id


class SQLiteOperationalReadRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    async def list_requests(self) -> list[RequestRecord]:
        return [
            RequestRecord(**dict(row))
            for row in self._fetch_all(
                """
                select id, public_id, customer, lane, mode, status, weight_kg
                from transport_requests
                order by public_id
                """
            )
        ]

    async def list_quotes(self) -> list[QuoteRecord]:
        return [
            QuoteRecord(**dict(row))
            for row in self._fetch_all(
                """
                select id, status, version, customer_price, currency, parent_quote_id
                from quotes
                order by id
                """
            )
        ]

    async def list_shipments(self) -> list[ShipmentRecord]:
        return [
            ShipmentRecord(**dict(row))
            for row in self._fetch_all(
                """
                select id, public_id, quote_id, carrier_id, lane, status, eta
                from shipments
                order by public_id
                """
            )
        ]

    async def list_carriers(self) -> list[CarrierRecord]:
        rows = self._fetch_all(
            """
            select
              id, display_name, aliases, modes, lane_score, max_weight_kg,
              performance_score, preferred, sample_size
            from carriers
            order by display_name
            """
        )

        return [
            CarrierRecord(
                id=row["id"],
                display_name=row["display_name"],
                aliases=_split_csv(row["aliases"]),
                modes=_split_csv(row["modes"]),
                lane_score=row["lane_score"],
                max_weight_kg=row["max_weight_kg"],
                performance_score=row["performance_score"],
                preferred=bool(row["preferred"]),
                sample_size=row["sample_size"],
            )
            for row in rows
        ]

    async def list_inbox(self) -> list[InboxRecord]:
        return [
            InboxRecord(**dict(row))
            for row in self._fetch_all(
                """
                select id, sender, subject, created_at as received_at, classification
                from email_inbound
                order by created_at desc
                """
            )
        ]

    async def list_agent_logs(self) -> list[AgentLogRecord]:
        return [
            AgentLogRecord(**dict(row))
            for row in self._fetch_all(
                """
                select agent_key, agent_name, step, entity_id, confidence
                from agent_logs
                order by created_at desc
                """
            )
        ]

    def _fetch_all(self, query: str, parameters: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        with self._database.connect() as connection:
            return list(connection.execute(query, parameters).fetchall())


class SQLiteRequestWriteRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    async def create_transport_request(
        self,
        *,
        customer: str,
        lane: str,
        request: TransportRequestInput,
        status: str,
        review_reason: str | None,
    ) -> RequestRecord:
        request_id = str(uuid4())

        with self._database.connect() as connection:
            public_id = _next_public_id(connection, "transport_requests", "REQ")
            total_weight = sum(line.weight_kg or 0 for line in request.cargo)
            connection.execute(
                """
                insert into transport_requests
                  (id, public_id, customer, lane, mode, status, weight_kg, review_reason)
                values (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request_id,
                    public_id,
                    customer,
                    lane,
                    request.mode.value,
                    status,
                    total_weight,
                    review_reason,
                ),
            )

            connection.executemany(
                """
                insert into request_cargo
                  (
                    id, request_id, description, quantity, weight_kg,
                    length_cm, width_cm, height_cm, hazardous, un_number
                  )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        str(uuid4()),
                        request_id,
                        line.description,
                        line.quantity,
                        line.weight_kg,
                        line.length_cm,
                        line.width_cm,
                        line.height_cm,
                        0,
                        None,
                    )
                    for line in request.cargo
                ],
            )

        return RequestRecord(
            id=request_id,
            public_id=public_id,
            customer=customer,
            lane=lane,
            mode=request.mode.value,
            status=status,
            weight_kg=total_weight,
        )


def _count(connection: sqlite3.Connection, table: str) -> int:
    row = connection.execute(f"select count(*) as count from {table}").fetchone()
    return int(row["count"])


def _next_public_id(connection: sqlite3.Connection, table: str, prefix: str) -> str:
    row = connection.execute(f"select count(*) as count from {table}").fetchone()
    sequence = int(row["count"]) + 1
    return f"{prefix}-{sequence:04d}"


def _add_column_if_missing(
    connection: sqlite3.Connection,
    table: str,
    column: str,
    definition: str,
) -> None:
    columns = {
        row["name"]
        for row in connection.execute(f"pragma table_info({table})").fetchall()
    }
    if column not in columns:
        connection.execute(f"alter table {table} add column {column} {definition}")


def _split_csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())
