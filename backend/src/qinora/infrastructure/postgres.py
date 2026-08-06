from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from qinora.application import DEFAULT_AGENT_CONFIGS
from qinora.application.read_models import (
    AgentConfigRecord,
    AgentLogRecord,
    CarrierOfferRecord,
    CarrierRecord,
    ContactRecord,
    InboxDetailRecord,
    InboxRecord,
    InvoiceRecord,
    OperationalTaskRecord,
    OutboundReplyRecord,
    QuoteAcceptanceEventRecord,
    QuoteDetailRecord,
    QuoteLineItemRecord,
    QuoteRecord,
    QuoteResponseEventRecord,
    RequestCargoLineRecord,
    RequestDetailRecord,
    RequestRecord,
    ShipmentEventRecord,
    ShipmentRecord,
    StaleRequestRecord,
)
from qinora.domain import (
    CurrencyCode,
    Money,
    Quote,
    QuoteStatus,
    ShipmentStatus,
    TransportRequestInput,
    assert_shipment_transition,
    next_quote_revision,
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
            for config in DEFAULT_AGENT_CONFIGS:
                cursor.execute(
                    """
                    insert into public.agent_configs
                      (tenant_id, agent_key, is_enabled, config)
                    values (%s, %s, %s, %s)
                    on conflict (tenant_id, agent_key) do nothing
                    """,
                    (
                        self.tenant_id,
                        config.agent_key,
                        True,
                        Jsonb(
                            {
                                "agent_name": config.agent_name,
                                "auto_mode": config.auto_mode.value,
                                "min_confidence": config.min_confidence,
                            }
                        ),
                    ),
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

    async def get_request_detail(self, request_id: str) -> RequestDetailRecord | None:
        with self._database.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                select id, public_id, customer, lane, origin, destination, mode, status,
                  weight_kg, review_reason, created_at
                from public.transport_requests
                where tenant_id = %s and id = %s
                """,
                (self._database.tenant_id, request_id),
            )
            request_row = cursor.fetchone()
            if request_row is None:
                return None

            cursor.execute(
                """
                select id, description, quantity, weight_kg, length_cm, width_cm, height_cm,
                  hazardous, un_number
                from public.request_cargo
                where tenant_id = %s and request_id = %s
                order by created_at
                """,
                (self._database.tenant_id, request_id),
            )
            cargo_rows = cursor.fetchall()

        return RequestDetailRecord(
            request=RequestRecord(
                id=str(request_row["id"]),
                public_id=request_row["public_id"],
                customer=request_row["customer"] or "Unknown customer",
                lane=request_row["lane"]
                or _lane(request_row["origin"], request_row["destination"]),
                mode=request_row["mode"],
                status=request_row["status"],
                weight_kg=float(request_row["weight_kg"] or 0),
            ),
            review_reason=request_row["review_reason"],
            created_at=request_row["created_at"].isoformat(),
            cargo_lines=tuple(
                RequestCargoLineRecord(
                    id=str(row["id"]),
                    description=row["description"],
                    quantity=row["quantity"],
                    weight_kg=float(row["weight_kg"]) if row["weight_kg"] is not None else None,
                    length_cm=float(row["length_cm"]) if row["length_cm"] is not None else None,
                    width_cm=float(row["width_cm"]) if row["width_cm"] is not None else None,
                    height_cm=float(row["height_cm"]) if row["height_cm"] is not None else None,
                    hazardous=bool(row["hazardous"]),
                    un_number=row["un_number"],
                )
                for row in cargo_rows
            ),
        )

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
                select
                    id, status, version, customer_price, currency, parent_quote_id,
                    coalesce(request_id::text, request_id_text) as request_id
                from public.quotes
                where tenant_id = %s
                order by public_id
                """,
                (self._database.tenant_id,),
            )
        ]

    async def get_quote_detail(self, quote_id: str) -> QuoteDetailRecord | None:
        with self._database.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                select
                    id, status, version, customer_price, currency, parent_quote_id,
                    coalesce(request_id::text, request_id_text) as request_id
                from public.quotes
                where tenant_id = %s and id = %s
                """,
                (self._database.tenant_id, quote_id),
            )
            quote_row = cursor.fetchone()
            if quote_row is None:
                return None

            cursor.execute(
                """
                select id, quote_id, description, amount, currency
                from public.quote_line_items
                where tenant_id = %s and quote_id = %s
                order by description
                """,
                (self._database.tenant_id, quote_id),
            )
            line_rows = cursor.fetchall()

            cursor.execute(
                """
                select id, quote_id, event_type, detail, created_at
                from (
                  select
                    id,
                    quote_id,
                    'quote_sent' as event_type,
                    status || ' email to ' || recipient as detail,
                    created_at
                  from public.outbound_reply_queue
                  where tenant_id = %s and quote_id = %s
                  union all
                  select
                    id,
                    quote_id,
                    'reply_' || intent as event_type,
                    body_text as detail,
                    created_at
                  from public.quote_response_events
                  where tenant_id = %s and quote_id = %s
                ) events
                order by created_at desc
                """,
                (self._database.tenant_id, quote_id, self._database.tenant_id, quote_id),
            )
            event_rows = cursor.fetchall()

        return QuoteDetailRecord(
            quote=_quote_record(quote_row),
            line_items=tuple(
                QuoteLineItemRecord(
                    id=str(row["id"]),
                    quote_id=str(row["quote_id"]),
                    description=row["description"],
                    amount=float(row["amount"]),
                    currency=row["currency"],
                )
                for row in line_rows
            ),
            acceptance_events=tuple(
                QuoteAcceptanceEventRecord(
                    id=str(row["id"]),
                    quote_id=str(row["quote_id"]),
                    event_type=row["event_type"],
                    detail=row["detail"],
                    created_at=row["created_at"].isoformat(),
                )
                for row in event_rows
            ),
        )

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

    async def list_contacts(self) -> list[ContactRecord]:
        return [
            ContactRecord(
                id=str(row["id"]),
                public_id=row["public_id"],
                display_name=row["name"],
                email=row["email"],
                domain=row["domain"],
                default_markup_percent=float(row["default_markup_percent"] or 0),
                default_incoterms=row["default_incoterms"],
                payment_terms=row["payment_terms"],
            )
            for row in self._fetch_all(
                """
                select
                  id, public_id, name, email, domain, default_markup_percent,
                  default_incoterms, payment_terms
                from public.contacts
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

    async def get_inbox_detail(self, message_id: str) -> InboxDetailRecord | None:
        rows = self._fetch_all(
            """
            select id, sender, subject, created_at, classification, body_text
            from public.email_inbound
            where tenant_id = %s and id = %s
            """,
            (self._database.tenant_id, message_id),
        )
        if not rows:
            return None

        row = rows[0]
        return InboxDetailRecord(
            message=InboxRecord(
                id=str(row["id"]),
                sender=row["sender"],
                subject=row["subject"],
                received_at=row["created_at"].isoformat(),
                classification=row["classification"] or "pending",
            ),
            body_text=row["body_text"],
        )

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


class PostgresContactReadRepository:
    def __init__(self, database: PostgresDatabase) -> None:
        self._database = database

    async def find_by_sender(self, sender: str) -> ContactRecord | None:
        email = sender.strip().lower()
        domain = email.rsplit("@", 1)[1] if "@" in email else email
        with self._database.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                select
                  id, public_id, name, email, domain, default_markup_percent,
                  default_incoterms, payment_terms
                from public.contacts
                where tenant_id = %s
                  and is_active = true
                  and (
                    lower(coalesce(email, '')) = %s
                    or lower(coalesce(domain, '')) = %s
                  )
                order by case when lower(coalesce(email, '')) = %s then 0 else 1 end
                limit 1
                """,
                (self._database.tenant_id, email, domain, email),
            )
            row = cursor.fetchone()

        if row is None:
            return None
        return ContactRecord(
            id=str(row["id"]),
            public_id=row["public_id"],
            display_name=row["name"],
            email=row["email"],
            domain=row["domain"],
            default_markup_percent=float(row["default_markup_percent"] or 0),
            default_incoterms=row["default_incoterms"],
            payment_terms=row["payment_terms"],
        )


class PostgresAgentLogWriteRepository:
    def __init__(self, database: PostgresDatabase) -> None:
        self._database = database

    async def record(
        self,
        *,
        agent_key: str,
        agent_name: str,
        step: str,
        entity_id: str,
        confidence: float,
    ) -> AgentLogRecord:
        with self._database.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                insert into public.agent_logs
                  (tenant_id, agent_key, agent_name, step, entity_id, confidence)
                values (%s, %s, %s, %s, %s, %s)
                """,
                (
                    self._database.tenant_id,
                    agent_key,
                    agent_name,
                    step,
                    entity_id,
                    confidence,
                ),
            )

        return AgentLogRecord(
            agent_key=agent_key,
            agent_name=agent_name,
            step=step,
            entity_id=entity_id,
            confidence=confidence,
        )


class PostgresAgentConfigRepository:
    def __init__(self, database: PostgresDatabase) -> None:
        self._database = database

    async def list_configs(self) -> list[AgentConfigRecord]:
        with self._database.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                select agent_key, is_enabled, config
                from public.agent_configs
                where tenant_id = %s
                order by coalesce(config ->> 'agent_name', agent_key)
                """,
                (self._database.tenant_id,),
            )
            rows = cursor.fetchall()

        return [_agent_config_from_postgres_row(row) for row in rows]

    async def update_config(
        self,
        *,
        agent_key: str,
        is_enabled: bool,
        auto_mode: str,
        min_confidence: float,
    ) -> AgentConfigRecord:
        current = await self._get_config(agent_key)
        if current is None:
            raise LookupError(f"Agent config not found: {agent_key}")

        config = {
            **current["config"],
            "auto_mode": auto_mode,
            "min_confidence": min_confidence,
        }
        with self._database.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                update public.agent_configs
                set is_enabled = %s, config = %s
                where tenant_id = %s and agent_key = %s
                returning agent_key, is_enabled, config
                """,
                (
                    is_enabled,
                    Jsonb(config),
                    self._database.tenant_id,
                    agent_key,
                ),
            )
            row = cursor.fetchone()

        if row is None:
            raise LookupError(f"Agent config not found: {agent_key}")
        return _agent_config_from_postgres_row(row)

    async def _get_config(self, agent_key: str) -> dict[str, Any] | None:
        with self._database.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                select agent_key, is_enabled, config
                from public.agent_configs
                where tenant_id = %s and agent_key = %s
                """,
                (self._database.tenant_id, agent_key),
            )
            return cursor.fetchone()


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


class PostgresCarrierOfferWriteRepository:
    def __init__(self, database: PostgresDatabase) -> None:
        self._database = database

    async def create_offer(
        self,
        *,
        request_id: str,
        carrier_name: str,
        price: float | None,
        currency: str | None,
        transit_days: int | None,
        notes: str | None,
        confidence: float,
    ) -> CarrierOfferRecord:
        with self._database.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                insert into public.carrier_offers
                  (tenant_id, request_id, carrier_name, price, currency, transit_days,
                    notes, confidence)
                values (%s, %s, %s, %s, %s, %s, %s, %s)
                returning id, request_id, carrier_name, price, currency, transit_days,
                  notes, confidence, created_at
                """,
                (
                    self._database.tenant_id,
                    request_id,
                    carrier_name,
                    price,
                    currency,
                    transit_days,
                    notes,
                    confidence,
                ),
            )
            row = cursor.fetchone()
        return _carrier_offer_from_postgres_row(row)

    async def list_offers_for_request(self, request_id: str) -> list[CarrierOfferRecord]:
        with self._database.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                select id, request_id, carrier_name, price, currency, transit_days,
                  notes, confidence, created_at
                from public.carrier_offers
                where tenant_id = %s and request_id = %s
                order by created_at
                """,
                (self._database.tenant_id, request_id),
            )
            rows = cursor.fetchall()
        return [_carrier_offer_from_postgres_row(row) for row in rows]


def _carrier_offer_from_postgres_row(row: dict[str, Any]) -> CarrierOfferRecord:
    return CarrierOfferRecord(
        id=str(row["id"]),
        request_id=str(row["request_id"]),
        carrier_name=row["carrier_name"],
        price=float(row["price"]) if row["price"] is not None else None,
        currency=row["currency"],
        transit_days=row["transit_days"],
        notes=row["notes"],
        confidence=float(row["confidence"]),
        created_at=row["created_at"].isoformat(),
    )


class PostgresStaleRequestRepository:
    def __init__(self, database: PostgresDatabase) -> None:
        self._database = database

    async def list_stale_requests(self, cutoff: str) -> list[StaleRequestRecord]:
        with self._database.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                select id, public_id, customer, review_reason, created_at
                from public.transport_requests request
                where request.tenant_id = %s
                  and request.status = 'needs_clarification'
                  and request.created_at <= %s::timestamptz
                  and not exists (
                    select 1
                    from public.operational_tasks task
                    where task.tenant_id = request.tenant_id
                      and task.entity_type = 'transport_request'
                      and task.entity_id = request.id::text
                      and task.status = 'open'
                      and task.reason like 'Stale clarification request%%'
                  )
                order by request.created_at
                """,
                (self._database.tenant_id, cutoff),
            )
            rows = cursor.fetchall()

        return [
            StaleRequestRecord(
                id=str(row["id"]),
                public_id=row["public_id"],
                customer=row["customer"] or "Unknown customer",
                review_reason=row["review_reason"],
                created_at=row["created_at"].isoformat(),
            )
            for row in rows
        ]


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
                    returning
                        id, status, version, customer_price, currency, parent_quote_id,
                        coalesce(request_id::text, request_id_text) as request_id
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
            _insert_postgres_quote_line_item(
                cursor,
                self._database.tenant_id,
                str(row["id"]),
                customer_price,
                currency,
            )

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

    async def get_quote_record(self, quote_id: str) -> QuoteRecord | None:
        row = self._get_quote_row(quote_id)
        if row is None:
            return None
        return _quote_record(row)

    async def mark_quote_sent(self, quote_id: str) -> QuoteRecord:
        return self._set_status(quote_id, "sent")

    async def mark_quote_accepted(self, quote_id: str) -> QuoteRecord:
        return self._set_status(quote_id, "accepted")

    async def mark_quote_rejected(self, quote_id: str) -> QuoteRecord:
        return self._set_status(quote_id, "rejected")

    async def mark_quote_revision_requested(self, quote_id: str) -> QuoteRecord:
        return self._set_status(quote_id, "revision_requested")

    async def create_revision(
        self,
        *,
        previous_quote_id: str,
        customer_price: float,
        currency: str,
    ) -> QuoteRecord:
        previous = await self.get_quote(previous_quote_id)
        previous_record = await self.get_quote_record(previous_quote_id)
        if previous is None:
            raise LookupError(f"Quote not found: {previous_quote_id}")

        version, parent_quote_id = next_quote_revision(previous)
        with self._database.connect() as connection, connection.cursor() as cursor:
            public_id = _next_public_id(cursor, "public.quotes", "QUO", self._database.tenant_id)
            cursor.execute(
                """
                insert into public.quotes
                  (
                    tenant_id, public_id, request_id, request_id_text, parent_quote_id, version,
                    status, customer_price, currency
                  )
                values (
                  %s, %s,
                  case when %s ~ '^[0-9a-fA-F-]{36}$' then %s::uuid else null end,
                  %s, %s, %s, %s, %s, %s
                )
                returning
                    id, status, version, customer_price, currency, parent_quote_id,
                    coalesce(request_id::text, request_id_text) as request_id
                """,
                (
                    self._database.tenant_id,
                    public_id,
                    previous_record.request_id if previous_record else "",
                    previous_record.request_id if previous_record else "",
                    previous_record.request_id if previous_record else None,
                    parent_quote_id,
                    version,
                    "revised",
                    customer_price,
                    currency,
                ),
            )
            row = cursor.fetchone()
            _insert_postgres_quote_line_item(
                cursor,
                self._database.tenant_id,
                str(row["id"]),
                customer_price,
                currency,
            )

        return _quote_record(row)

    def _get_quote_row(self, quote_id: str) -> dict[str, Any] | None:
        with self._database.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                    select
                        id, status, version, customer_price, currency, parent_quote_id,
                        coalesce(request_id::text, request_id_text) as request_id
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
                    returning
                        id, status, version, customer_price, currency, parent_quote_id,
                        coalesce(request_id::text, request_id_text) as request_id
                    """,
                (status, self._database.tenant_id, quote_id),
            )
            row = cursor.fetchone()

        if row is None:
            raise LookupError(f"Quote not found: {quote_id}")
        return _quote_record(row)


class PostgresQuoteResponseEventRepository:
    def __init__(self, database: PostgresDatabase) -> None:
        self._database = database

    async def record_response(
        self,
        *,
        quote_id: str,
        intent: str,
        body_text: str,
    ) -> QuoteResponseEventRecord:
        with self._database.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                insert into public.quote_response_events
                  (tenant_id, quote_id, intent, body_text)
                values (%s, %s, %s, %s)
                returning id, quote_id, intent, body_text, created_at
                """,
                (self._database.tenant_id, quote_id, intent, body_text),
            )
            row = cursor.fetchone()

        return QuoteResponseEventRecord(
            id=str(row["id"]),
            quote_id=str(row["quote_id"]) if row["quote_id"] else "",
            intent=row["intent"],
            body_text=row["body_text"],
            created_at=row["created_at"].isoformat(),
        )


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
        request_id=str(row["request_id"]) if row.get("request_id") else None,
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


def _agent_config_from_postgres_row(row: dict[str, Any]) -> AgentConfigRecord:
    config = row["config"] or {}
    return AgentConfigRecord(
        agent_key=row["agent_key"],
        agent_name=str(config.get("agent_name", row["agent_key"])),
        is_enabled=bool(row["is_enabled"]),
        auto_mode=str(config.get("auto_mode", "manual")),
        min_confidence=float(config.get("min_confidence", 0)),
    )


def _insert_postgres_quote_line_item(
    cursor: psycopg.Cursor[dict[str, Any]],
    tenant_id: str,
    quote_id: str,
    amount: float,
    currency: str,
) -> None:
    cursor.execute(
        """
        insert into public.quote_line_items
          (tenant_id, quote_id, description, amount, currency)
        values (%s, %s, %s, %s, %s)
        """,
        (tenant_id, quote_id, "Freight charge", amount, currency),
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
