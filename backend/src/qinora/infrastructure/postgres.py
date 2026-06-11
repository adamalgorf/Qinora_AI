from typing import Any

import psycopg
from psycopg.rows import dict_row

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


class PostgresDatabase:
    def __init__(self, database_url: str, tenant_id: str) -> None:
        self._database_url = database_url
        self.tenant_id = tenant_id
        self.initialize()

    def connect(self) -> psycopg.Connection[dict[str, Any]]:
        return psycopg.connect(self._database_url, row_factory=dict_row)

    def initialize(self) -> None:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                    insert into public.tenants (id, name)
                    values (%s, %s)
                    on conflict (id) do nothing
                    """,
                (self.tenant_id, "QiNora Default Tenant"),
            )


class PostgresWebhookEventRepository:
    def __init__(self, database: PostgresDatabase) -> None:
        self._database = database

    async def exists(self, idempotency_key: str) -> bool:
        with self._database.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "select 1 from public.webhook_events where idempotency_key = %s",
                (idempotency_key,),
            )
            return cursor.fetchone() is not None

    async def record(self, idempotency_key: str, event_type: str) -> None:
        with self._database.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                    insert into public.webhook_events (idempotency_key, event_type)
                    values (%s, %s)
                    on conflict (idempotency_key) do nothing
                    """,
                (idempotency_key, event_type),
            )


class PostgresInboundEmailRepository:
    def __init__(self, database: PostgresDatabase) -> None:
        self._database = database

    async def save(
        self,
        *,
        idempotency_key: str,
        sender: str,
        subject: str,
        body_text: str,
    ) -> str:
        with self._database.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                    insert into public.email_inbound
                      (tenant_id, idempotency_key, sender, subject, body_text, classification)
                    values (%s, %s, %s, %s, %s, %s)
                    returning id
                    """,
                (self._database.tenant_id, idempotency_key, sender, subject, body_text, "pending"),
            )
            return str(cursor.fetchone()["id"])


class PostgresOperationalReadRepository:
    def __init__(self, database: PostgresDatabase) -> None:
        self._database = database

    async def list_requests(self) -> list[RequestRecord]:
        return [
            RequestRecord(
                id=str(row["id"]),
                public_id=row["public_id"],
                customer=row["customer"] or "Unknown customer",
                lane=row["lane"] or _lane(row["origin"], row["destination"]),
                mode=row["mode"],
                status=row["status"],
                weight_kg=float(row["weight_kg"] or 0),
            )
            for row in self._fetch_all(
                """
                select id, public_id, customer, lane, origin, destination, mode, status, weight_kg
                from public.transport_requests
                where tenant_id = %s
                order by public_id
                """,
                (self._database.tenant_id,),
            )
        ]

    async def list_quotes(self) -> list[QuoteRecord]:
        return [
            QuoteRecord(
                id=str(row["id"]),
                status=row["status"],
                version=row["version"],
                customer_price=float(row["customer_price"]),
                currency=row["currency"],
                parent_quote_id=str(row["parent_quote_id"]) if row["parent_quote_id"] else None,
            )
            for row in self._fetch_all(
                """
                select id, status, version, customer_price, currency, parent_quote_id
                from public.quotes
                where tenant_id = %s
                order by public_id
                """,
                (self._database.tenant_id,),
            )
        ]

    async def list_shipments(self) -> list[ShipmentRecord]:
        return [
            ShipmentRecord(
                id=str(row["id"]),
                public_id=row["public_id"],
                quote_id=str(row["quote_id"]) if row["quote_id"] else "",
                carrier_id=str(row["carrier_id"]) if row["carrier_id"] else None,
                lane=row["lane"] or "Pending lane confirmation",
                status=row["status"],
                eta=row["eta_label"] or (row["eta"].isoformat() if row["eta"] else "Pending"),
            )
            for row in self._fetch_all(
                """
                select id, public_id, quote_id, carrier_id, lane, status, eta, eta_label
                from public.shipments
                where tenant_id = %s
                order by public_id
                """,
                (self._database.tenant_id,),
            )
        ]

    async def list_invoices(self) -> list[InvoiceRecord]:
        return [
            InvoiceRecord(
                id=str(row["id"]),
                public_id=row["public_id"],
                shipment_id=str(row["shipment_id"]) if row["shipment_id"] else "",
                quote_id=str(row["quote_id"]) if row["quote_id"] else "",
                invoice_amount=float(row["invoice_amount"]),
                quote_amount=float(row["quote_amount"]),
                currency=row["currency"],
                status=row["status"],
                discrepancy_amount=float(row["discrepancy_amount"] or 0),
            )
            for row in self._fetch_all(
                """
                select
                  id, public_id, shipment_id, quote_id, invoice_amount, quote_amount,
                  currency, status, discrepancy_amount
                from public.invoices
                where tenant_id = %s
                order by public_id
                """,
                (self._database.tenant_id,),
            )
        ]

    async def list_carriers(self) -> list[CarrierRecord]:
        return [
            CarrierRecord(
                id=str(row["id"]),
                display_name=row["name"],
                aliases=tuple(row["aliases"] or ()),
                modes=tuple(row["modes"] or ()),
                lane_score=float(row["lane_score"]),
                max_weight_kg=(
                    float(row["max_weight_kg"])
                    if row["max_weight_kg"] is not None
                    else None
                ),
                performance_score=(
                    float(row["performance_score"])
                    if row["performance_score"] is not None
                    else None
                ),
                preferred=bool(row["is_preferred"]),
                sample_size=row["sample_size"],
            )
            for row in self._fetch_all(
                """
                select
                  id, name, aliases, modes, lane_score, max_weight_kg,
                  performance_score, is_preferred, sample_size
                from public.carriers
                where tenant_id = %s and is_active = true
                order by name
                """,
                (self._database.tenant_id,),
            )
        ]

    async def list_inbox(self) -> list[InboxRecord]:
        return [
            InboxRecord(
                id=str(row["id"]),
                sender=row["sender"],
                subject=row["subject"],
                received_at=row["created_at"].isoformat(),
                classification=row["classification"] or "pending",
            )
            for row in self._fetch_all(
                """
                select id, sender, subject, created_at, classification
                from public.email_inbound
                where tenant_id = %s
                order by created_at desc
                """,
                (self._database.tenant_id,),
            )
        ]

    async def list_agent_logs(self) -> list[AgentLogRecord]:
        return [
            AgentLogRecord(
                agent_key=row["agent_key"],
                agent_name=row["agent_name"] or row["agent_key"],
                step=row["step"],
                entity_id=row["entity_id"] or "",
                confidence=float(row["confidence"] or 0),
            )
            for row in self._fetch_all(
                """
                select agent_key, agent_name, step, entity_id, confidence
                from public.agent_logs
                where tenant_id = %s
                order by created_at desc
                """,
                (self._database.tenant_id,),
            )
        ]

    async def list_operational_tasks(self) -> list[OperationalTaskRecord]:
        return [
            OperationalTaskRecord(
                id=str(row["id"]),
                entity_type=row["entity_type"],
                entity_id=row["entity_id"],
                priority=row["priority"],
                reason=row["reason"],
                status=row["status"],
                created_at=row["created_at"].isoformat(),
            )
            for row in self._fetch_all(
                """
                select id, entity_type, entity_id, priority, reason, status, created_at
                from public.operational_tasks
                where tenant_id = %s
                order by created_at desc
                """,
                (self._database.tenant_id,),
            )
        ]

    async def list_shipment_events(self, shipment_id: str) -> list[ShipmentEventRecord]:
        return [
            ShipmentEventRecord(
                id=str(row["id"]),
                shipment_id=str(row["shipment_id"]),
                from_status=row["from_status"],
                to_status=row["to_status"],
                reason=row["reason"],
                created_at=row["created_at"].isoformat(),
            )
            for row in self._fetch_all(
                """
                select id, shipment_id, from_status, to_status, reason, created_at
                from public.shipment_events
                where tenant_id = %s and shipment_id = %s
                order by created_at desc
                """,
                (self._database.tenant_id, shipment_id),
            )
        ]

    async def list_outbound_replies(self) -> list[OutboundReplyRecord]:
        return [
            OutboundReplyRecord(
                id=str(row["id"]),
                quote_id=str(row["quote_id"]) if row["quote_id"] else "",
                recipient=row["recipient"],
                subject=row["subject"],
                body_text=row["body_text"],
                status=row["status"],
                created_at=row["created_at"].isoformat(),
                sent_at=row["sent_at"].isoformat() if row["sent_at"] else None,
                error_message=row["error_message"],
            )
            for row in self._fetch_all(
                """
                select
                  id, quote_id, recipient, subject, body_text, status,
                  created_at, sent_at, error_message
                from public.outbound_reply_queue
                where tenant_id = %s
                order by created_at desc
                """,
                (self._database.tenant_id,),
            )
        ]

    def _fetch_all(self, query: str, parameters: tuple[Any, ...]) -> list[dict[str, Any]]:
        with self._database.connect() as connection, connection.cursor() as cursor:
            cursor.execute(query, parameters)
            return list(cursor.fetchall())


class PostgresRequestWriteRepository:
    def __init__(self, database: PostgresDatabase) -> None:
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
        origin, destination = _split_lane(lane)
        total_weight = sum(line.weight_kg or 0 for line in request.cargo)

        with self._database.connect() as connection, connection.cursor() as cursor:
            public_id = _next_public_id(
                cursor,
                "public.transport_requests",
                "REQ",
                self._database.tenant_id,
            )
            cursor.execute(
                """
                insert into public.transport_requests
                  (
                    tenant_id, public_id, customer, lane, mode, status, origin,
                    destination, review_reason, weight_kg
                  )
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                returning id
                """,
                (
                    self._database.tenant_id,
                    public_id,
                    customer,
                    lane,
                    request.mode.value,
                    status,
                    origin,
                    destination,
                    review_reason,
                    total_weight,
                ),
            )
            request_id = str(cursor.fetchone()["id"])
            cursor.executemany(
                """
                insert into public.request_cargo
                  (
                    tenant_id, request_id, description, quantity, weight_kg,
                    length_cm, width_cm, height_cm, hazardous, un_number
                  )
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                [
                    (
                        self._database.tenant_id,
                        request_id,
                        line.description,
                        line.quantity,
                        line.weight_kg,
                        line.length_cm,
                        line.width_cm,
                        line.height_cm,
                        False,
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


class PostgresQuoteWriteRepository:
    def __init__(self, database: PostgresDatabase) -> None:
        self._database = database

    async def create_quote(
        self,
        *,
        request_id: str,
        customer_price: float,
        currency: str,
    ) -> QuoteRecord:
        with self._database.connect() as connection, connection.cursor() as cursor:
            public_id = _next_public_id(cursor, "public.quotes", "QUO", self._database.tenant_id)
            cursor.execute(
                """
                    insert into public.quotes
                      (
                        tenant_id, public_id, request_id, request_id_text, status,
                        version, customer_price, currency
                      )
                    values (
                      %s, %s,
                      case when %s ~ '^[0-9a-fA-F-]{36}$' then %s::uuid else null end,
                      %s, %s, %s, %s, %s
                    )
                    returning id, status, version, customer_price, currency, parent_quote_id
                    """,
                (
                    self._database.tenant_id,
                    public_id,
                    request_id,
                    request_id,
                    request_id,
                    "draft",
                    1,
                    customer_price,
                    currency,
                ),
            )
            row = cursor.fetchone()

        return _quote_record(row)

    async def get_quote(self, quote_id: str) -> Quote | None:
        row = self._get_quote_row(quote_id)
        if row is None:
            return None

        return Quote(
            id=str(row["id"]),
            status=QuoteStatus(row["status"]),
            version=row["version"],
            customer_price=Money(
                amount=float(row["customer_price"]),
                currency=CurrencyCode(row["currency"]),
            ),
            parent_quote_id=str(row["parent_quote_id"]) if row["parent_quote_id"] else None,
        )

    async def mark_quote_sent(self, quote_id: str) -> QuoteRecord:
        return self._set_status(quote_id, "sent")

    async def mark_quote_accepted(self, quote_id: str) -> QuoteRecord:
        return self._set_status(quote_id, "accepted")

    def _get_quote_row(self, quote_id: str) -> dict[str, Any] | None:
        with self._database.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                    select id, status, version, customer_price, currency, parent_quote_id
                    from public.quotes
                    where tenant_id = %s and id = %s
                    """,
                (self._database.tenant_id, quote_id),
            )
            return cursor.fetchone()

    def _set_status(self, quote_id: str, status: str) -> QuoteRecord:
        with self._database.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                    update public.quotes
                    set status = %s
                    where tenant_id = %s and id = %s
                    returning id, status, version, customer_price, currency, parent_quote_id
                    """,
                (status, self._database.tenant_id, quote_id),
            )
            row = cursor.fetchone()

        if row is None:
            raise LookupError(f"Quote not found: {quote_id}")
        return _quote_record(row)


class PostgresShipmentWriteRepository:
    def __init__(self, database: PostgresDatabase) -> None:
        self._database = database

    async def get_shipment(self, shipment_id: str) -> ShipmentRecord | None:
        with self._database.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                select id, public_id, quote_id, carrier_id, lane, status, eta_label, eta
                from public.shipments
                where tenant_id = %s and id = %s
                """,
                (self._database.tenant_id, shipment_id),
            )
            row = cursor.fetchone()

        if row is None:
            return None
        return ShipmentRecord(
            id=str(row["id"]),
            public_id=row["public_id"],
            quote_id=str(row["quote_id"]) if row["quote_id"] else "",
            carrier_id=str(row["carrier_id"]) if row["carrier_id"] else None,
            lane=row["lane"] or "Pending lane confirmation",
            status=row["status"],
            eta=row["eta_label"] or (row["eta"].isoformat() if row["eta"] else "Pending"),
        )

    async def create_shipment(
        self,
        *,
        quote_id: str,
        carrier_id: str | None,
        lane: str,
        status: str,
        eta: str,
    ) -> ShipmentRecord:
        with self._database.connect() as connection, connection.cursor() as cursor:
            public_id = _next_public_id(cursor, "public.shipments", "SHP", self._database.tenant_id)
            cursor.execute(
                """
                    insert into public.shipments
                      (
                        tenant_id, public_id, quote_id, carrier_id, lane,
                        status, eta_label, requires_manual_review
                      )
                    values (
                      %s, %s,
                      case when %s ~ '^[0-9a-fA-F-]{36}$' then %s::uuid else null end,
                      case when %s ~ '^[0-9a-fA-F-]{36}$' then %s::uuid else null end,
                      %s, %s, %s, %s
                    )
                    returning id
                    """,
                (
                    self._database.tenant_id,
                    public_id,
                    quote_id,
                    quote_id,
                    carrier_id or "",
                    carrier_id or "",
                    lane,
                    status,
                    eta,
                    status == "needs_review",
                ),
            )
            shipment_id = str(cursor.fetchone()["id"])

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
        with self._database.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                    select id, public_id, quote_id, carrier_id, lane, status, eta_label, eta
                    from public.shipments
                    where tenant_id = %s and id = %s
                    """,
                (self._database.tenant_id, shipment_id),
            )
            row = cursor.fetchone()
            if row is None:
                return None

            assert_shipment_transition(
                ShipmentStatus(row["status"]),
                ShipmentStatus(status),
            )
            cursor.execute(
                """
                    update public.shipments
                    set status = %s
                    where tenant_id = %s and id = %s
                    """,
                (status, self._database.tenant_id, shipment_id),
            )

        return ShipmentRecord(
            id=str(row["id"]),
            public_id=row["public_id"],
            quote_id=str(row["quote_id"]) if row["quote_id"] else "",
            carrier_id=str(row["carrier_id"]) if row["carrier_id"] else None,
            lane=row["lane"] or "Pending lane confirmation",
            status=status,
            eta=row["eta_label"] or (row["eta"].isoformat() if row["eta"] else "Pending"),
        )


class PostgresInvoiceWriteRepository:
    def __init__(self, database: PostgresDatabase) -> None:
        self._database = database

    async def expected_invoice_amount(self, shipment_id: str) -> float:
        with self._database.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                select q.customer_price
                from public.shipments s
                join public.quotes q on q.id = s.quote_id
                where s.tenant_id = %s and s.id = %s
                """,
                (self._database.tenant_id, shipment_id),
            )
            row = cursor.fetchone()

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
        with self._database.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                    select quote_id
                    from public.shipments
                    where tenant_id = %s and id = %s
                    """,
                (self._database.tenant_id, shipment_id),
            )
            shipment = cursor.fetchone()
            if shipment is None:
                raise LookupError(f"Shipment not found: {shipment_id}")

            cursor.execute(
                """
                    select id, customer_price, currency
                    from public.quotes
                    where tenant_id = %s and id = %s
                    """,
                (self._database.tenant_id, shipment["quote_id"]),
            )
            quote = cursor.fetchone()
            if quote is None:
                raise LookupError(f"Quote not found: {shipment['quote_id']}")

            public_id = _next_public_id(cursor, "public.invoices", "INV", self._database.tenant_id)
            quote_amount = float(quote["customer_price"])
            discrepancy_amount = round(invoice_amount - quote_amount, 2)
            status = "approved" if abs(discrepancy_amount) <= max_discrepancy else "disputed"

            cursor.execute(
                """
                    insert into public.invoices
                      (
                        tenant_id, public_id, shipment_id, quote_id, invoice_amount,
                        quote_amount, currency, status, discrepancy_amount
                      )
                    values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    returning id
                    """,
                (
                    self._database.tenant_id,
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
            invoice_id = str(cursor.fetchone()["id"])

        return InvoiceRecord(
            id=invoice_id,
            public_id=public_id,
            shipment_id=shipment_id,
            quote_id=str(quote["id"]),
            invoice_amount=invoice_amount,
            quote_amount=quote_amount,
            currency=quote["currency"],
            status=status,
            discrepancy_amount=discrepancy_amount,
        )


class PostgresOperationalTaskWriteRepository:
    def __init__(self, database: PostgresDatabase) -> None:
        self._database = database

    async def create_task(
        self,
        *,
        entity_type: str,
        entity_id: str,
        reason: str,
        priority: str = "normal",
    ) -> OperationalTaskRecord:
        with self._database.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                insert into public.operational_tasks
                  (tenant_id, entity_type, entity_id, priority, reason, status)
                values (%s, %s, %s, %s, %s, %s)
                returning id, entity_type, entity_id, priority, reason, status, created_at
                """,
                (self._database.tenant_id, entity_type, entity_id, priority, reason, "open"),
            )
            row = cursor.fetchone()

        return OperationalTaskRecord(
            id=str(row["id"]),
            entity_type=row["entity_type"],
            entity_id=row["entity_id"],
            priority=row["priority"],
            reason=row["reason"],
            status=row["status"],
            created_at=row["created_at"].isoformat(),
        )


class PostgresShipmentEventRepository:
    def __init__(self, database: PostgresDatabase) -> None:
        self._database = database

    async def record_status_change(
        self,
        *,
        shipment_id: str,
        from_status: str | None,
        to_status: str,
        reason: str | None = None,
    ) -> ShipmentEventRecord:
        with self._database.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                insert into public.shipment_events
                  (tenant_id, shipment_id, from_status, to_status, reason)
                values (%s, %s, %s, %s, %s)
                returning id, shipment_id, from_status, to_status, reason, created_at
                """,
                (self._database.tenant_id, shipment_id, from_status, to_status, reason),
            )
            row = cursor.fetchone()

        return ShipmentEventRecord(
            id=str(row["id"]),
            shipment_id=str(row["shipment_id"]),
            from_status=row["from_status"],
            to_status=row["to_status"],
            reason=row["reason"],
            created_at=row["created_at"].isoformat(),
        )


class PostgresOutboundReplyRepository:
    def __init__(self, database: PostgresDatabase) -> None:
        self._database = database

    async def enqueue_quote(
        self,
        *,
        quote_id: str,
        recipient: str,
        subject: str,
        body_text: str,
    ) -> OutboundReplyRecord:
        with self._database.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                insert into public.outbound_reply_queue
                  (tenant_id, quote_id, recipient, subject, body_text, status)
                values (%s, %s, %s, %s, %s, %s)
                returning
                  id, quote_id, recipient, subject, body_text, status,
                  created_at, sent_at, error_message
                """,
                (self._database.tenant_id, quote_id, recipient, subject, body_text, "queued"),
            )
            row = cursor.fetchone()

        return OutboundReplyRecord(
            id=str(row["id"]),
            quote_id=str(row["quote_id"]) if row["quote_id"] else "",
            recipient=row["recipient"],
            subject=row["subject"],
            body_text=row["body_text"],
            status=row["status"],
            created_at=row["created_at"].isoformat(),
            sent_at=row["sent_at"].isoformat() if row["sent_at"] else None,
            error_message=row["error_message"],
        )

    async def next_queued(self, limit: int) -> list[OutboundReplyRecord]:
        with self._database.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                select
                  id, quote_id, recipient, subject, body_text, status,
                  created_at, sent_at, error_message
                from public.outbound_reply_queue
                where tenant_id = %s and status = %s
                order by created_at
                limit %s
                """,
                (self._database.tenant_id, "queued", limit),
            )
            rows = cursor.fetchall()

        return [_outbound_reply_record(row) for row in rows]

    async def mark_sent(self, reply_id: str) -> OutboundReplyRecord:
        with self._database.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                update public.outbound_reply_queue
                set status = %s, sent_at = now(), error_message = null
                where tenant_id = %s and id = %s
                returning
                  id, quote_id, recipient, subject, body_text, status,
                  created_at, sent_at, error_message
                """,
                ("sent", self._database.tenant_id, reply_id),
            )
            row = cursor.fetchone()

        if row is None:
            raise LookupError(f"Outbound reply not found: {reply_id}")
        return _outbound_reply_record(row)

    async def mark_failed(self, reply_id: str, error_message: str) -> OutboundReplyRecord:
        with self._database.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                update public.outbound_reply_queue
                set status = %s, error_message = %s
                where tenant_id = %s and id = %s
                returning
                  id, quote_id, recipient, subject, body_text, status,
                  created_at, sent_at, error_message
                """,
                ("failed", error_message, self._database.tenant_id, reply_id),
            )
            row = cursor.fetchone()

        if row is None:
            raise LookupError(f"Outbound reply not found: {reply_id}")
        return _outbound_reply_record(row)


def _quote_record(row: dict[str, Any]) -> QuoteRecord:
    return QuoteRecord(
        id=str(row["id"]),
        status=row["status"],
        version=row["version"],
        customer_price=float(row["customer_price"]),
        currency=row["currency"],
        parent_quote_id=str(row["parent_quote_id"]) if row["parent_quote_id"] else None,
    )


def _outbound_reply_record(row: dict[str, Any]) -> OutboundReplyRecord:
    return OutboundReplyRecord(
        id=str(row["id"]),
        quote_id=str(row["quote_id"]) if row["quote_id"] else "",
        recipient=row["recipient"],
        subject=row["subject"],
        body_text=row["body_text"],
        status=row["status"],
        created_at=row["created_at"].isoformat(),
        sent_at=row["sent_at"].isoformat() if row["sent_at"] else None,
        error_message=row["error_message"],
    )


def _next_public_id(
    cursor: psycopg.Cursor[dict[str, Any]],
    table: str,
    prefix: str,
    tenant_id: str,
) -> str:
    cursor.execute(f"select count(*) as count from {table} where tenant_id = %s", (tenant_id,))
    sequence = int(cursor.fetchone()["count"]) + 1
    return f"{prefix}-{sequence:04d}"


def _lane(origin: str | None, destination: str | None) -> str:
    if origin and destination:
        return f"{origin} -> {destination}"
    return origin or destination or "Pending lane confirmation"


def _split_lane(lane: str) -> tuple[str | None, str | None]:
    if " -> " not in lane:
        return lane, None
    origin, destination = lane.split(" -> ", maxsplit=1)
    return origin or None, destination or None
