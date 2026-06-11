import sqlite3
from pathlib import Path
from typing import Any
from uuid import uuid4

from qinora.application.read_models import (
    AgentLogRecord,
    CarrierRecord,
    InboxRecord,
    InvoiceRecord,
    OperationalTaskRecord,
    OutboundReplyRecord,
    QuoteRecord,
    RequestRecord,
    ShipmentEventRecord,
    ShipmentRecord,
)
from qinora.domain import (
    CurrencyCode,
    Money,
    Quote,
    QuoteStatus,
    ShipmentStatus,
    TransportRequestInput,
    assert_shipment_transition,
)


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

                create table if not exists invoices (
                  id text primary key,
                  public_id text not null unique,
                  shipment_id text not null,
                  quote_id text not null,
                  invoice_amount real not null,
                  quote_amount real not null,
                  currency text not null,
                  status text not null,
                  discrepancy_amount real not null,
                  created_at text not null default current_timestamp
                );

                create table if not exists operational_tasks (
                  id text primary key,
                  entity_type text not null,
                  entity_id text not null,
                  priority text not null,
                  reason text not null,
                  status text not null default 'open',
                  created_at text not null default current_timestamp
                );

                create table if not exists shipment_events (
                  id text primary key,
                  shipment_id text not null,
                  from_status text,
                  to_status text not null,
                  reason text,
                  created_at text not null default current_timestamp
                );

                create table if not exists outbound_reply_queue (
                  id text primary key,
                  quote_id text not null,
                  recipient text not null,
                  subject text not null,
                  body_text text not null,
                  status text not null default 'queued',
                  created_at text not null default current_timestamp,
                  sent_at text,
                  error_message text
                );
                """
            )
            _add_column_if_missing(
                connection,
                "transport_requests",
                "review_reason",
                "text",
            )
            _add_column_if_missing(connection, "outbound_reply_queue", "sent_at", "text")
            _add_column_if_missing(connection, "outbound_reply_queue", "error_message", "text")
            self._seed(connection)
            self._seed_runtime_relationships(connection)
            self._seed_operational_tasks(connection)

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
                ("quo-004", "accepted", 1, 9800, "SEK", None),
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

    def _seed_runtime_relationships(self, connection: sqlite3.Connection) -> None:
        if _exists_by_id(connection, "quotes", "quo-004"):
            return

        connection.execute(
            """
            insert into quotes
              (id, status, version, customer_price, currency, parent_quote_id)
            values (?, ?, ?, ?, ?, ?)
            """,
            ("quo-004", "accepted", 1, 9800, "SEK", None),
        )

    def _seed_operational_tasks(self, connection: sqlite3.Connection) -> None:
        if _count(connection, "operational_tasks") > 0:
            return

        connection.execute(
            """
            insert into operational_tasks
              (id, entity_type, entity_id, priority, reason, status)
            values (?, ?, ?, ?, ?, ?)
            """,
            (
                "task-001",
                "transport_request",
                "req-003",
                "high",
                "Missing cargo dimensions and loading time",
                "open",
            ),
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

    async def list_invoices(self) -> list[InvoiceRecord]:
        return [
            InvoiceRecord(**dict(row))
            for row in self._fetch_all(
                """
                select
                  id, public_id, shipment_id, quote_id, invoice_amount, quote_amount,
                  currency, status, discrepancy_amount
                from invoices
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

    async def list_operational_tasks(self) -> list[OperationalTaskRecord]:
        return [
            OperationalTaskRecord(**dict(row))
            for row in self._fetch_all(
                """
                select id, entity_type, entity_id, priority, reason, status, created_at
                from operational_tasks
                order by created_at desc
                """
            )
        ]

    async def list_shipment_events(self, shipment_id: str) -> list[ShipmentEventRecord]:
        return [
            ShipmentEventRecord(**dict(row))
            for row in self._fetch_all(
                """
                select id, shipment_id, from_status, to_status, reason, created_at
                from shipment_events
                where shipment_id = ?
                order by created_at desc
                """,
                (shipment_id,),
            )
        ]

    async def list_outbound_replies(self) -> list[OutboundReplyRecord]:
        return [
            OutboundReplyRecord(**dict(row))
            for row in self._fetch_all(
                """
                select
                  id, quote_id, recipient, subject, body_text, status,
                  created_at, sent_at, error_message
                from outbound_reply_queue
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


class SQLiteQuoteWriteRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    async def create_quote(
        self,
        *,
        request_id: str,
        customer_price: float,
        currency: str,
    ) -> QuoteRecord:
        quote_id = str(uuid4())

        with self._database.connect() as connection:
            connection.execute(
                """
                insert into quotes
                  (id, status, version, customer_price, currency, parent_quote_id)
                values (?, ?, ?, ?, ?, ?)
                """,
                (quote_id, "draft", 1, customer_price, currency, None),
            )

        return QuoteRecord(
            id=quote_id,
            status="draft",
            version=1,
            customer_price=customer_price,
            currency=currency,
            parent_quote_id=None,
        )

    async def get_quote(self, quote_id: str) -> Quote | None:
        with self._database.connect() as connection:
            row = connection.execute(
                """
                select id, status, version, customer_price, currency, parent_quote_id
                from quotes
                where id = ?
                """,
                (quote_id,),
            ).fetchone()

        if row is None:
            return None

        return Quote(
            id=row["id"],
            status=QuoteStatus(row["status"]),
            version=row["version"],
            customer_price=Money(
                amount=row["customer_price"],
                currency=CurrencyCode(row["currency"]),
            ),
            parent_quote_id=row["parent_quote_id"],
        )

    async def mark_quote_sent(self, quote_id: str) -> QuoteRecord:
        with self._database.connect() as connection:
            connection.execute(
                "update quotes set status = ? where id = ?",
                ("sent", quote_id),
            )
            row = connection.execute(
                """
                select id, status, version, customer_price, currency, parent_quote_id
                from quotes
                where id = ?
                """,
                (quote_id,),
            ).fetchone()

        return QuoteRecord(**dict(row))

    async def mark_quote_accepted(self, quote_id: str) -> QuoteRecord:
        with self._database.connect() as connection:
            connection.execute(
                "update quotes set status = ? where id = ?",
                ("accepted", quote_id),
            )
            row = connection.execute(
                """
                select id, status, version, customer_price, currency, parent_quote_id
                from quotes
                where id = ?
                """,
                (quote_id,),
            ).fetchone()

        if row is None:
            raise LookupError(f"Quote not found: {quote_id}")

        return QuoteRecord(**dict(row))


class SQLiteShipmentWriteRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    async def get_shipment(self, shipment_id: str) -> ShipmentRecord | None:
        with self._database.connect() as connection:
            row = connection.execute(
                """
                select id, public_id, quote_id, carrier_id, lane, status, eta
                from shipments
                where id = ?
                """,
                (shipment_id,),
            ).fetchone()

        if row is None:
            return None
        return ShipmentRecord(**dict(row))

    async def create_shipment(
        self,
        *,
        quote_id: str,
        carrier_id: str | None,
        lane: str,
        status: str,
        eta: str,
    ) -> ShipmentRecord:
        shipment_id = str(uuid4())

        with self._database.connect() as connection:
            public_id = _next_public_id(connection, "shipments", "SHP")
            connection.execute(
                """
                insert into shipments
                  (id, public_id, quote_id, carrier_id, lane, status, eta)
                values (?, ?, ?, ?, ?, ?, ?)
                """,
                (shipment_id, public_id, quote_id, carrier_id, lane, status, eta),
            )

        return ShipmentRecord(
            id=shipment_id,
            public_id=public_id,
            quote_id=quote_id,
            carrier_id=carrier_id,
            lane=lane,
            status=status,
            eta=eta,
        )

    async def update_status(self, shipment_id: str, status: str) -> ShipmentRecord | None:
        with self._database.connect() as connection:
            row = connection.execute(
                """
                select id, public_id, quote_id, carrier_id, lane, status, eta
                from shipments
                where id = ?
                """,
                (shipment_id,),
            ).fetchone()

            if row is None:
                return None

            assert_shipment_transition(
                ShipmentStatus(row["status"]),
                ShipmentStatus(status),
            )
            connection.execute(
                "update shipments set status = ? where id = ?",
                (status, shipment_id),
            )

        return ShipmentRecord(
            id=row["id"],
            public_id=row["public_id"],
            quote_id=row["quote_id"],
            carrier_id=row["carrier_id"],
            lane=row["lane"],
            status=status,
            eta=row["eta"],
        )


class SQLiteInvoiceWriteRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    async def expected_invoice_amount(self, shipment_id: str) -> float:
        with self._database.connect() as connection:
            row = connection.execute(
                """
                select q.customer_price
                from shipments s
                join quotes q on q.id = s.quote_id
                where s.id = ?
                """,
                (shipment_id,),
            ).fetchone()

        if row is None:
            raise LookupError(f"Shipment not found: {shipment_id}")
        return float(row["customer_price"])

    async def create_invoice_audit(
        self,
        *,
        shipment_id: str,
        invoice_amount: float,
        max_discrepancy: float,
    ) -> InvoiceRecord:
        invoice_id = str(uuid4())

        with self._database.connect() as connection:
            shipment = connection.execute(
                """
                select quote_id
                from shipments
                where id = ?
                """,
                (shipment_id,),
            ).fetchone()

            if shipment is None:
                raise LookupError(f"Shipment not found: {shipment_id}")

            quote = connection.execute(
                """
                select id, customer_price, currency
                from quotes
                where id = ?
                """,
                (shipment["quote_id"],),
            ).fetchone()

            if quote is None:
                raise LookupError(f"Quote not found: {shipment['quote_id']}")

            public_id = _next_public_id(connection, "invoices", "INV")
            quote_amount = float(quote["customer_price"])
            discrepancy_amount = round(invoice_amount - quote_amount, 2)
            status = "approved" if abs(discrepancy_amount) <= max_discrepancy else "disputed"

            connection.execute(
                """
                insert into invoices
                  (
                    id, public_id, shipment_id, quote_id, invoice_amount, quote_amount,
                    currency, status, discrepancy_amount
                  )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    invoice_id,
                    public_id,
                    shipment_id,
                    quote["id"],
                    invoice_amount,
                    quote_amount,
                    quote["currency"],
                    status,
                    discrepancy_amount,
                ),
            )

        return InvoiceRecord(
            id=invoice_id,
            public_id=public_id,
            shipment_id=shipment_id,
            quote_id=quote["id"],
            invoice_amount=invoice_amount,
            quote_amount=quote_amount,
            currency=quote["currency"],
            status=status,
            discrepancy_amount=discrepancy_amount,
        )


class SQLiteOperationalTaskWriteRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    async def create_task(
        self,
        *,
        entity_type: str,
        entity_id: str,
        reason: str,
        priority: str = "normal",
    ) -> OperationalTaskRecord:
        task_id = str(uuid4())
        with self._database.connect() as connection:
            row = connection.execute(
                """
                insert into operational_tasks
                  (id, entity_type, entity_id, priority, reason, status)
                values (?, ?, ?, ?, ?, ?)
                returning id, entity_type, entity_id, priority, reason, status, created_at
                """,
                (task_id, entity_type, entity_id, priority, reason, "open"),
            ).fetchone()

        return OperationalTaskRecord(**dict(row))


class SQLiteShipmentEventRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    async def record_status_change(
        self,
        *,
        shipment_id: str,
        from_status: str | None,
        to_status: str,
        reason: str | None = None,
    ) -> ShipmentEventRecord:
        event_id = str(uuid4())
        with self._database.connect() as connection:
            row = connection.execute(
                """
                insert into shipment_events
                  (id, shipment_id, from_status, to_status, reason)
                values (?, ?, ?, ?, ?)
                returning id, shipment_id, from_status, to_status, reason, created_at
                """,
                (event_id, shipment_id, from_status, to_status, reason),
            ).fetchone()

        return ShipmentEventRecord(**dict(row))


class SQLiteOutboundReplyRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    async def enqueue_quote(
        self,
        *,
        quote_id: str,
        recipient: str,
        subject: str,
        body_text: str,
    ) -> OutboundReplyRecord:
        reply_id = str(uuid4())
        with self._database.connect() as connection:
            row = connection.execute(
                """
                insert into outbound_reply_queue
                  (id, quote_id, recipient, subject, body_text, status)
                values (?, ?, ?, ?, ?, ?)
                returning
                  id, quote_id, recipient, subject, body_text, status,
                  created_at, sent_at, error_message
                """,
                (reply_id, quote_id, recipient, subject, body_text, "queued"),
            ).fetchone()

        return OutboundReplyRecord(**dict(row))

    async def next_queued(self, limit: int) -> list[OutboundReplyRecord]:
        with self._database.connect() as connection:
            rows = connection.execute(
                """
                select
                  id, quote_id, recipient, subject, body_text, status,
                  created_at, sent_at, error_message
                from outbound_reply_queue
                where status = ?
                order by created_at
                limit ?
                """,
                ("queued", limit),
            ).fetchall()

        return [OutboundReplyRecord(**dict(row)) for row in rows]

    async def mark_sent(self, reply_id: str) -> OutboundReplyRecord:
        with self._database.connect() as connection:
            row = connection.execute(
                """
                update outbound_reply_queue
                set status = ?, sent_at = current_timestamp, error_message = null
                where id = ?
                returning
                  id, quote_id, recipient, subject, body_text, status,
                  created_at, sent_at, error_message
                """,
                ("sent", reply_id),
            ).fetchone()

        if row is None:
            raise LookupError(f"Outbound reply not found: {reply_id}")
        return OutboundReplyRecord(**dict(row))

    async def mark_failed(self, reply_id: str, error_message: str) -> OutboundReplyRecord:
        with self._database.connect() as connection:
            row = connection.execute(
                """
                update outbound_reply_queue
                set status = ?, error_message = ?
                where id = ?
                returning
                  id, quote_id, recipient, subject, body_text, status,
                  created_at, sent_at, error_message
                """,
                ("failed", error_message, reply_id),
            ).fetchone()

        if row is None:
            raise LookupError(f"Outbound reply not found: {reply_id}")
        return OutboundReplyRecord(**dict(row))


def _count(connection: sqlite3.Connection, table: str) -> int:
    row = connection.execute(f"select count(*) as count from {table}").fetchone()
    return int(row["count"])


def _exists_by_id(connection: sqlite3.Connection, table: str, record_id: str) -> bool:
    row = connection.execute(f"select 1 from {table} where id = ?", (record_id,)).fetchone()
    return row is not None


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
