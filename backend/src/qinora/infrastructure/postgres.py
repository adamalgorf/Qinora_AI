import secrets
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
    CarrierRfqOutboundRecord,
    CarrierRfqRecord,
    ClarificationOutboundRecord,
    ContactRecord,
    InboundEmailRecord,
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
    RateProfileRecord,
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
        recipient: str = "",
        message_id: str | None = None,
        in_reply_to: str | None = None,
        references_header: str | None = None,
    ) -> str:
        with self._database.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                    insert into public.email_inbound
                      (
                        tenant_id, idempotency_key, sender, recipient, subject, body_text,
                        classification, message_id, in_reply_to, references_header
                      )
                    values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    returning id
                    """,
                (
                    self._database.tenant_id,
                    idempotency_key,
                    sender,
                    recipient,
                    subject,
                    body_text,
                    "pending",
                    message_id,
                    in_reply_to,
                    references_header,
                ),
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
                customer=row["customer"] or "Okänd kund",
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
                customer=request_row["customer"] or "Okänd kund",
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
                lane=row["lane"] or "Väntar på sträckbekräftelse",
                status=row["status"],
                eta=row["eta_label"] or (row["eta"].isoformat() if row["eta"] else "Väntar"),
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
                email=row["email"],
            )
            for row in self._fetch_all(
                """
                select
                  id, name, aliases, modes, lane_score, max_weight_kg,
                  performance_score, is_preferred, sample_size, email
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

    async def update_transport_request(
        self,
        *,
        request_id: str,
        customer: str,
        lane: str,
        request: TransportRequestInput,
        status: str,
        review_reason: str | None,
    ) -> RequestRecord:
        origin, destination = _split_lane(lane)
        total_weight = sum(line.weight_kg or 0 for line in request.cargo)

        with self._database.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                select public_id
                from public.transport_requests
                where tenant_id = %s and id = %s
                """,
                (self._database.tenant_id, request_id),
            )
            row = cursor.fetchone()
            if row is None:
                raise LookupError(f"Transport request not found: {request_id}")
            public_id = row["public_id"]

            cursor.execute(
                """
                update public.transport_requests
                set customer = %s, lane = %s, mode = %s, status = %s, origin = %s,
                  destination = %s, review_reason = %s, weight_kg = %s
                where tenant_id = %s and id = %s
                """,
                (
                    customer,
                    lane,
                    request.mode.value,
                    status,
                    origin,
                    destination,
                    review_reason,
                    total_weight,
                    self._database.tenant_id,
                    request_id,
                ),
            )
            cursor.execute(
                "delete from public.request_cargo where tenant_id = %s and request_id = %s",
                (self._database.tenant_id, request_id),
            )
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

    async def update_request_status(self, request_id: str, status: str) -> None:
        with self._database.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                update public.transport_requests
                set status = %s
                where tenant_id = %s and id = %s
                """,
                (status, self._database.tenant_id, request_id),
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
        carrier_rfq_id: str | None = None,
    ) -> CarrierOfferRecord:
        with self._database.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                insert into public.carrier_offers
                  (
                    tenant_id, request_id, carrier_name, price, currency, transit_days,
                    notes, confidence, carrier_rfq_id
                  )
                values (
                  %s, %s, %s, %s, %s, %s, %s, %s,
                  case when %s ~ '^[0-9a-fA-F-]{36}$' then %s::uuid else null end
                )
                returning id, request_id, carrier_name, price, currency, transit_days,
                  notes, confidence, created_at, carrier_rfq_id
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
                    carrier_rfq_id or "",
                    carrier_rfq_id or "",
                ),
            )
            row = cursor.fetchone()
        return _carrier_offer_from_postgres_row(row)

    async def list_offers_for_request(self, request_id: str) -> list[CarrierOfferRecord]:
        with self._database.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                select id, request_id, carrier_name, price, currency, transit_days,
                  notes, confidence, created_at, carrier_rfq_id
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
        carrier_rfq_id=str(row["carrier_rfq_id"]) if row["carrier_rfq_id"] else None,
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
                customer=row["customer"] or "Okänd kund",
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
            lane=row["lane"] or "Väntar på sträckbekräftelse",
            status=row["status"],
            eta=row["eta_label"] or (row["eta"].isoformat() if row["eta"] else "Väntar"),
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
            lane=row["lane"] or "Väntar på sträckbekräftelse",
            status=status,
            eta=row["eta_label"] or (row["eta"].isoformat() if row["eta"] else "Väntar"),
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
        in_reply_to_message_id: str | None = None,
    ) -> OutboundReplyRecord:
        with self._database.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                insert into public.outbound_reply_queue
                  (tenant_id, quote_id, recipient, subject, body_text, status,
                   in_reply_to_message_id)
                values (%s, %s, %s, %s, %s, %s, %s)
                returning
                  id, quote_id, recipient, subject, body_text, status,
                  created_at, sent_at, error_message, in_reply_to_message_id
                """,
                (
                    self._database.tenant_id,
                    quote_id,
                    recipient,
                    subject,
                    body_text,
                    "queued",
                    in_reply_to_message_id,
                ),
            )
            row = cursor.fetchone()

        return _outbound_reply_record(row)

    async def next_queued(self, limit: int) -> list[OutboundReplyRecord]:
        with self._database.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                select
                  id, quote_id, recipient, subject, body_text, status,
                  created_at, sent_at, error_message, in_reply_to_message_id
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
                  created_at, sent_at, error_message, in_reply_to_message_id
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
                  created_at, sent_at, error_message, in_reply_to_message_id
                """,
                ("failed", error_message, self._database.tenant_id, reply_id),
            )
            row = cursor.fetchone()

        if row is None:
            raise LookupError(f"Outbound reply not found: {reply_id}")
        return _outbound_reply_record(row)


_EMAIL_THREAD_COLUMNS = """
    id, sender, recipient, subject, body_text, classification, message_id,
    in_reply_to, references_header, request_id, quote_id, created_at
"""


class PostgresEmailThreadRepository:
    def __init__(self, database: PostgresDatabase) -> None:
        self._database = database

    async def get(self, email_id: str) -> InboundEmailRecord | None:
        with self._database.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""
                select {_EMAIL_THREAD_COLUMNS}
                from public.email_inbound
                where tenant_id = %s and id = %s
                """,
                (self._database.tenant_id, email_id),
            )
            row = cursor.fetchone()
        return _inbound_email_from_postgres_row(row) if row else None

    async def find_candidates_by_message_ids(
        self, message_ids: tuple[str, ...]
    ) -> list[InboundEmailRecord]:
        if not message_ids:
            return []
        with self._database.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""
                select {_EMAIL_THREAD_COLUMNS}
                from public.email_inbound
                where tenant_id = %s and message_id = any(%s)
                order by created_at desc
                """,
                (self._database.tenant_id, list(message_ids)),
            )
            rows = cursor.fetchall()
        return [_inbound_email_from_postgres_row(row) for row in rows]

    async def find_candidates_by_sender(
        self, sender: str, limit: int = 200
    ) -> list[InboundEmailRecord]:
        with self._database.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""
                select {_EMAIL_THREAD_COLUMNS}
                from public.email_inbound
                where tenant_id = %s and lower(sender) = %s
                order by created_at desc
                limit %s
                """,
                (self._database.tenant_id, sender.strip().lower(), limit),
            )
            rows = cursor.fetchall()
        return [_inbound_email_from_postgres_row(row) for row in rows]

    async def find_candidates_by_domain(
        self, domain: str, limit: int = 200
    ) -> list[InboundEmailRecord]:
        with self._database.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""
                select {_EMAIL_THREAD_COLUMNS}
                from public.email_inbound
                where tenant_id = %s and lower(sender) like %s
                order by created_at desc
                limit %s
                """,
                (self._database.tenant_id, f"%@{domain.strip().lower()}", limit),
            )
            rows = cursor.fetchall()
        return [_inbound_email_from_postgres_row(row) for row in rows]

    async def list_thread_history(
        self, *, request_id: str | None, quote_id: str | None
    ) -> list[InboundEmailRecord]:
        if not request_id and not quote_id:
            return []
        with self._database.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""
                select {_EMAIL_THREAD_COLUMNS}
                from public.email_inbound
                where tenant_id = %s
                  and ((%s::text is not null and request_id = %s)
                    or (%s::text is not null and quote_id = %s))
                order by created_at asc
                """,
                (self._database.tenant_id, request_id, request_id, quote_id, quote_id),
            )
            rows = cursor.fetchall()
        return [_inbound_email_from_postgres_row(row) for row in rows]

    async def link_thread(
        self, email_id: str, *, request_id: str | None, quote_id: str | None
    ) -> None:
        with self._database.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                update public.email_inbound
                set request_id = %s, quote_id = %s
                where tenant_id = %s and id = %s
                """,
                (request_id, quote_id, self._database.tenant_id, email_id),
            )

    async def mark_classification(self, email_id: str, classification: str) -> None:
        with self._database.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                update public.email_inbound
                set classification = %s
                where tenant_id = %s and id = %s
                """,
                (classification, self._database.tenant_id, email_id),
            )


class PostgresRateProfileRepository:
    def __init__(self, database: PostgresDatabase) -> None:
        self._database = database

    async def find_matching(
        self, *, mode: str, origin: str | None, destination: str | None
    ) -> RateProfileRecord | None:
        with self._database.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                select id, mode, origin, destination, base_price, price_per_kg, currency
                from public.rate_profiles
                where tenant_id = %s and mode = %s and origin is not distinct from %s
                  and destination is not distinct from %s
                """,
                (self._database.tenant_id, mode, origin, destination),
            )
            row = cursor.fetchone()
            if row is None and (origin is not None or destination is not None):
                cursor.execute(
                    """
                    select id, mode, origin, destination, base_price, price_per_kg, currency
                    from public.rate_profiles
                    where tenant_id = %s and mode = %s
                      and origin is null and destination is null
                    """,
                    (self._database.tenant_id, mode),
                )
                row = cursor.fetchone()
        return _rate_profile_from_postgres_row(row) if row else None

    async def list_all(self) -> list[RateProfileRecord]:
        with self._database.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                select id, mode, origin, destination, base_price, price_per_kg, currency
                from public.rate_profiles
                where tenant_id = %s
                order by mode, origin, destination
                """,
                (self._database.tenant_id,),
            )
            rows = cursor.fetchall()
        return [_rate_profile_from_postgres_row(row) for row in rows]

    async def create(
        self,
        *,
        mode: str,
        origin: str | None,
        destination: str | None,
        base_price: float,
        price_per_kg: float,
        currency: str,
    ) -> RateProfileRecord:
        with self._database.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                insert into public.rate_profiles
                  (tenant_id, mode, origin, destination, base_price, price_per_kg, currency)
                values (%s, %s, %s, %s, %s, %s, %s)
                returning id, mode, origin, destination, base_price, price_per_kg, currency
                """,
                (
                    self._database.tenant_id,
                    mode,
                    origin,
                    destination,
                    base_price,
                    price_per_kg,
                    currency,
                ),
            )
            row = cursor.fetchone()
        return _rate_profile_from_postgres_row(row)

    async def update(
        self,
        rate_profile_id: str,
        *,
        mode: str,
        origin: str | None,
        destination: str | None,
        base_price: float,
        price_per_kg: float,
        currency: str,
    ) -> RateProfileRecord:
        with self._database.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                update public.rate_profiles
                set mode = %s, origin = %s, destination = %s, base_price = %s,
                  price_per_kg = %s, currency = %s
                where tenant_id = %s and id = %s
                returning id, mode, origin, destination, base_price, price_per_kg, currency
                """,
                (
                    mode,
                    origin,
                    destination,
                    base_price,
                    price_per_kg,
                    currency,
                    self._database.tenant_id,
                    rate_profile_id,
                ),
            )
            row = cursor.fetchone()
        if row is None:
            raise LookupError(f"Rate profile not found: {rate_profile_id}")
        return _rate_profile_from_postgres_row(row)


class PostgresCarrierRfqRepository:
    def __init__(self, database: PostgresDatabase) -> None:
        self._database = database

    async def create_batch(
        self,
        *,
        request_id: str,
        carrier_ids: tuple[str, ...],
        window_hours: int = 24,
    ) -> list[CarrierRfqRecord]:
        records: list[CarrierRfqRecord] = []
        with self._database.connect() as connection, connection.cursor() as cursor:
            for carrier_id in carrier_ids:
                row = None
                for _ in range(5):
                    token = secrets.token_hex(4)
                    cursor.execute(
                        """
                        insert into public.carrier_rfqs
                          (tenant_id, request_id, carrier_id, correlation_token, status, expires_at)
                        values (%s, %s, %s, %s, 'sent', now() + (%s || ' hours')::interval)
                        on conflict (correlation_token) do nothing
                        returning id, request_id, carrier_id, correlation_token, status,
                          sent_at, responded_at, expires_at
                        """,
                        (
                            self._database.tenant_id,
                            request_id,
                            carrier_id,
                            token,
                            str(window_hours),
                        ),
                    )
                    row = cursor.fetchone()
                    if row is not None:
                        break
                if row is None:
                    raise RuntimeError("Could not generate a unique RFQ correlation token")
                records.append(_carrier_rfq_from_postgres_row(row))
        return records

    async def find_by_token(self, token: str) -> CarrierRfqRecord | None:
        with self._database.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                select id, request_id, carrier_id, correlation_token, status, sent_at,
                  responded_at, expires_at
                from public.carrier_rfqs
                where tenant_id = %s and correlation_token = %s
                """,
                (self._database.tenant_id, token),
            )
            row = cursor.fetchone()
        return _carrier_rfq_from_postgres_row(row) if row else None

    async def find_by_carrier_email(self, sender_address: str) -> CarrierRfqRecord | None:
        with self._database.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                select rfq.id, rfq.request_id, rfq.carrier_id, rfq.correlation_token,
                  rfq.status, rfq.sent_at, rfq.responded_at, rfq.expires_at
                from public.carrier_rfqs rfq
                join public.carriers c on c.id = rfq.carrier_id
                where rfq.tenant_id = %s and rfq.status = 'sent'
                  and lower(c.email) = %s
                order by rfq.sent_at desc
                limit 1
                """,
                (self._database.tenant_id, sender_address.strip().lower()),
            )
            row = cursor.fetchone()
        return _carrier_rfq_from_postgres_row(row) if row else None

    async def mark_responded(self, rfq_id: str, offer_id: str) -> CarrierRfqRecord:
        with self._database.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                update public.carrier_offers
                set carrier_rfq_id = %s
                where tenant_id = %s and id = %s
                """,
                (rfq_id, self._database.tenant_id, offer_id),
            )
            cursor.execute(
                """
                update public.carrier_rfqs
                set status = 'responded', responded_at = now()
                where tenant_id = %s and id = %s
                returning id, request_id, carrier_id, correlation_token, status, sent_at,
                  responded_at, expires_at
                """,
                (self._database.tenant_id, rfq_id),
            )
            row = cursor.fetchone()
        if row is None:
            raise LookupError(f"Carrier RFQ not found: {rfq_id}")
        return _carrier_rfq_from_postgres_row(row)

    async def list_open_batch(self, request_id: str) -> list[CarrierRfqRecord]:
        return await self._list_batch(request_id, status="sent")

    async def list_batch(self, request_id: str) -> list[CarrierRfqRecord]:
        return await self._list_batch(request_id, status=None)

    async def _list_batch(self, request_id: str, status: str | None) -> list[CarrierRfqRecord]:
        query = """
            select id, request_id, carrier_id, correlation_token, status, sent_at,
              responded_at, expires_at
            from public.carrier_rfqs
            where tenant_id = %s and request_id = %s
        """
        params: list[Any] = [self._database.tenant_id, request_id]
        if status is not None:
            query += " and status = %s"
            params.append(status)
        query += " order by sent_at"

        with self._database.connect() as connection, connection.cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()
        return [_carrier_rfq_from_postgres_row(row) for row in rows]

    async def expire_stale(self, cutoff: str) -> list[CarrierRfqRecord]:
        with self._database.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                update public.carrier_rfqs
                set status = 'expired'
                where tenant_id = %s and status = 'sent' and sent_at <= %s::timestamptz
                returning id, request_id, carrier_id, correlation_token, status, sent_at,
                  responded_at, expires_at
                """,
                (self._database.tenant_id, cutoff),
            )
            rows = cursor.fetchall()
        return [_carrier_rfq_from_postgres_row(row) for row in rows]

    async def mark_superseded(self, rfq_ids: tuple[str, ...]) -> None:
        if not rfq_ids:
            return
        with self._database.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                update public.carrier_rfqs
                set status = 'superseded'
                where tenant_id = %s and id = any(%s)
                """,
                (self._database.tenant_id, list(rfq_ids)),
            )

    async def find_winning(self, request_id: str) -> CarrierRfqRecord | None:
        with self._database.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                select id, request_id, carrier_id, correlation_token, status, sent_at,
                  responded_at, expires_at
                from public.carrier_rfqs
                where tenant_id = %s and request_id = %s and status = 'responded'
                order by responded_at
                limit 1
                """,
                (self._database.tenant_id, request_id),
            )
            row = cursor.fetchone()
        return _carrier_rfq_from_postgres_row(row) if row else None


class PostgresCarrierWriteRepository:
    def __init__(self, database: PostgresDatabase) -> None:
        self._database = database

    async def create_carrier(
        self,
        *,
        display_name: str,
        modes: tuple[str, ...],
        aliases: tuple[str, ...] = (),
        email: str | None = None,
        lane_score: float = 50.0,
        max_weight_kg: float | None = None,
        performance_score: float | None = None,
        preferred: bool = False,
    ) -> CarrierRecord:
        with self._database.connect() as connection, connection.cursor() as cursor:
            public_id = _next_public_id(cursor, "public.carriers", "CAR", self._database.tenant_id)
            cursor.execute(
                """
                insert into public.carriers
                  (tenant_id, public_id, name, aliases, modes, lane_score, max_weight_kg,
                   performance_score, is_preferred, sample_size, email)
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, 0, %s)
                returning id
                """,
                (
                    self._database.tenant_id,
                    public_id,
                    display_name,
                    list(aliases),
                    list(modes),
                    lane_score,
                    max_weight_kg,
                    performance_score,
                    preferred,
                    email,
                ),
            )
            carrier_id = str(cursor.fetchone()["id"])

        return CarrierRecord(
            id=carrier_id,
            display_name=display_name,
            aliases=aliases,
            modes=modes,
            lane_score=lane_score,
            max_weight_kg=max_weight_kg,
            performance_score=performance_score,
            preferred=preferred,
            sample_size=0,
            email=email,
        )


def _carrier_rfq_from_postgres_row(row: dict[str, Any]) -> CarrierRfqRecord:
    return CarrierRfqRecord(
        id=str(row["id"]),
        request_id=str(row["request_id"]),
        carrier_id=str(row["carrier_id"]),
        correlation_token=row["correlation_token"],
        status=row["status"],
        sent_at=row["sent_at"].isoformat(),
        responded_at=row["responded_at"].isoformat() if row["responded_at"] else None,
        expires_at=row["expires_at"].isoformat(),
    )


class PostgresCarrierRfqOutboundRepository:
    def __init__(self, database: PostgresDatabase) -> None:
        self._database = database

    async def enqueue(
        self,
        *,
        carrier_rfq_id: str,
        recipient: str,
        subject: str,
        body_text: str,
    ) -> CarrierRfqOutboundRecord:
        with self._database.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                insert into public.carrier_rfq_outbound
                  (tenant_id, carrier_rfq_id, recipient, subject, body_text, status)
                values (%s, %s, %s, %s, %s, %s)
                returning
                  id, carrier_rfq_id, recipient, subject, body_text, status,
                  created_at, sent_at, error_message
                """,
                (
                    self._database.tenant_id,
                    carrier_rfq_id,
                    recipient,
                    subject,
                    body_text,
                    "queued",
                ),
            )
            row = cursor.fetchone()
        return _carrier_rfq_outbound_from_postgres_row(row)

    async def next_queued(self, limit: int) -> list[CarrierRfqOutboundRecord]:
        with self._database.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                select
                  id, carrier_rfq_id, recipient, subject, body_text, status,
                  created_at, sent_at, error_message
                from public.carrier_rfq_outbound
                where tenant_id = %s and status = %s
                order by created_at
                limit %s
                """,
                (self._database.tenant_id, "queued", limit),
            )
            rows = cursor.fetchall()
        return [_carrier_rfq_outbound_from_postgres_row(row) for row in rows]

    async def mark_sent(self, item_id: str) -> CarrierRfqOutboundRecord:
        with self._database.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                update public.carrier_rfq_outbound
                set status = %s, sent_at = now(), error_message = null
                where tenant_id = %s and id = %s
                returning
                  id, carrier_rfq_id, recipient, subject, body_text, status,
                  created_at, sent_at, error_message
                """,
                ("sent", self._database.tenant_id, item_id),
            )
            row = cursor.fetchone()
        if row is None:
            raise LookupError(f"Carrier RFQ outbound item not found: {item_id}")
        return _carrier_rfq_outbound_from_postgres_row(row)

    async def mark_failed(self, item_id: str, error_message: str) -> CarrierRfqOutboundRecord:
        with self._database.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                update public.carrier_rfq_outbound
                set status = %s, error_message = %s
                where tenant_id = %s and id = %s
                returning
                  id, carrier_rfq_id, recipient, subject, body_text, status,
                  created_at, sent_at, error_message
                """,
                ("failed", error_message, self._database.tenant_id, item_id),
            )
            row = cursor.fetchone()
        if row is None:
            raise LookupError(f"Carrier RFQ outbound item not found: {item_id}")
        return _carrier_rfq_outbound_from_postgres_row(row)


def _carrier_rfq_outbound_from_postgres_row(row: dict[str, Any]) -> CarrierRfqOutboundRecord:
    return CarrierRfqOutboundRecord(
        id=str(row["id"]),
        carrier_rfq_id=str(row["carrier_rfq_id"]),
        recipient=row["recipient"],
        subject=row["subject"],
        body_text=row["body_text"],
        status=row["status"],
        created_at=row["created_at"].isoformat(),
        sent_at=row["sent_at"].isoformat() if row["sent_at"] else None,
        error_message=row["error_message"],
    )


class PostgresClarificationOutboundRepository:
    def __init__(self, database: PostgresDatabase) -> None:
        self._database = database

    async def enqueue(
        self,
        *,
        inbound_email_id: str,
        recipient: str,
        subject: str,
        body_text: str,
        in_reply_to_message_id: str | None = None,
    ) -> ClarificationOutboundRecord:
        with self._database.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                insert into public.clarification_outbound
                  (tenant_id, inbound_email_id, recipient, subject, body_text, status,
                   in_reply_to_message_id)
                values (%s, %s, %s, %s, %s, %s, %s)
                returning
                  id, inbound_email_id, recipient, subject, body_text, status,
                  created_at, sent_at, error_message, in_reply_to_message_id
                """,
                (
                    self._database.tenant_id,
                    inbound_email_id,
                    recipient,
                    subject,
                    body_text,
                    "queued",
                    in_reply_to_message_id,
                ),
            )
            row = cursor.fetchone()
        return _clarification_outbound_from_postgres_row(row)

    async def next_queued(self, limit: int) -> list[ClarificationOutboundRecord]:
        with self._database.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                select
                  id, inbound_email_id, recipient, subject, body_text, status,
                  created_at, sent_at, error_message, in_reply_to_message_id
                from public.clarification_outbound
                where tenant_id = %s and status = %s
                order by created_at
                limit %s
                """,
                (self._database.tenant_id, "queued", limit),
            )
            rows = cursor.fetchall()
        return [_clarification_outbound_from_postgres_row(row) for row in rows]

    async def mark_sent(self, item_id: str) -> ClarificationOutboundRecord:
        with self._database.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                update public.clarification_outbound
                set status = %s, sent_at = now(), error_message = null
                where tenant_id = %s and id = %s
                returning
                  id, inbound_email_id, recipient, subject, body_text, status,
                  created_at, sent_at, error_message, in_reply_to_message_id
                """,
                ("sent", self._database.tenant_id, item_id),
            )
            row = cursor.fetchone()
        if row is None:
            raise LookupError(f"Clarification outbound item not found: {item_id}")
        return _clarification_outbound_from_postgres_row(row)

    async def mark_failed(self, item_id: str, error_message: str) -> ClarificationOutboundRecord:
        with self._database.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                update public.clarification_outbound
                set status = %s, error_message = %s
                where tenant_id = %s and id = %s
                returning
                  id, inbound_email_id, recipient, subject, body_text, status,
                  created_at, sent_at, error_message, in_reply_to_message_id
                """,
                ("failed", error_message, self._database.tenant_id, item_id),
            )
            row = cursor.fetchone()
        if row is None:
            raise LookupError(f"Clarification outbound item not found: {item_id}")
        return _clarification_outbound_from_postgres_row(row)


def _clarification_outbound_from_postgres_row(row: dict[str, Any]) -> ClarificationOutboundRecord:
    return ClarificationOutboundRecord(
        id=str(row["id"]),
        inbound_email_id=str(row["inbound_email_id"]),
        recipient=row["recipient"],
        subject=row["subject"],
        body_text=row["body_text"],
        status=row["status"],
        created_at=row["created_at"].isoformat(),
        sent_at=row["sent_at"].isoformat() if row["sent_at"] else None,
        error_message=row["error_message"],
        in_reply_to_message_id=row.get("in_reply_to_message_id"),
    )


def _inbound_email_from_postgres_row(row: dict[str, Any]) -> InboundEmailRecord:
    return InboundEmailRecord(
        id=str(row["id"]),
        sender=row["sender"],
        recipient=row["recipient"] or "",
        subject=row["subject"],
        body_text=row["body_text"],
        classification=row["classification"],
        message_id=row["message_id"],
        in_reply_to=row["in_reply_to"],
        references_header=row["references_header"],
        request_id=str(row["request_id"]) if row["request_id"] else None,
        quote_id=str(row["quote_id"]) if row["quote_id"] else None,
        created_at=row["created_at"].isoformat(),
    )


def _rate_profile_from_postgres_row(row: dict[str, Any]) -> RateProfileRecord:
    return RateProfileRecord(
        id=str(row["id"]),
        mode=row["mode"],
        origin=row["origin"],
        destination=row["destination"],
        base_price=float(row["base_price"]),
        price_per_kg=float(row["price_per_kg"]),
        currency=row["currency"],
    )


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
        in_reply_to_message_id=row.get("in_reply_to_message_id"),
    )


def _agent_config_from_postgres_row(row: dict[str, Any]) -> AgentConfigRecord:
    config = row["config"] or {}
    return AgentConfigRecord(
        agent_key=row["agent_key"],
        agent_name=str(config.get("agent_name", row["agent_key"])),
        is_enabled=bool(row["is_enabled"]),
        auto_mode=str(config.get("auto_mode", "manual")),
        min_confidence=float(config.get("min_confidence", 0)),
        config=dict(config),
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
    return origin or destination or "Väntar på sträckbekräftelse"


def _split_lane(lane: str) -> tuple[str | None, str | None]:
    if " -> " not in lane:
        return lane, None
    origin, destination = lane.split(" -> ", maxsplit=1)
    return origin or None, destination or None
