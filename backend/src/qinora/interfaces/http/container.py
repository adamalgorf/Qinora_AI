from dataclasses import dataclass
from typing import Any

from qinora.application import (
    BookingWorkflow,
    CreateRequestUseCase,
    EmailWebhookUseCase,
    InvoiceAuditWorkflow,
    OperationalQueries,
    ProcessOutboundQueueUseCase,
    QuoteResponseWorkflow,
    QuoteWorkflow,
    ShipmentWorkflow,
    TrackingSimulator,
)
from qinora.application.ports import ShipmentWriteRepository
from qinora.infrastructure.in_memory import RecordingAgentDispatcher
from qinora.infrastructure.outbound_mailer import RecordingOutboundMailer
from qinora.infrastructure.postgres import (
    PostgresDatabase,
    PostgresInboundEmailRepository,
    PostgresInvoiceWriteRepository,
    PostgresOperationalReadRepository,
    PostgresOperationalTaskWriteRepository,
    PostgresOutboundReplyRepository,
    PostgresQuoteResponseEventRepository,
    PostgresQuoteWriteRepository,
    PostgresRequestWriteRepository,
    PostgresShipmentEventRepository,
    PostgresShipmentWriteRepository,
    PostgresWebhookEventRepository,
)
from qinora.infrastructure.settings import PersistenceDriver, Settings
from qinora.infrastructure.sqlite import (
    SQLiteDatabase,
    SQLiteInboundEmailRepository,
    SQLiteInvoiceWriteRepository,
    SQLiteOperationalReadRepository,
    SQLiteOperationalTaskWriteRepository,
    SQLiteOutboundReplyRepository,
    SQLiteQuoteResponseEventRepository,
    SQLiteQuoteWriteRepository,
    SQLiteRequestWriteRepository,
    SQLiteShipmentEventRepository,
    SQLiteShipmentWriteRepository,
    SQLiteWebhookEventRepository,
)


@dataclass(frozen=True)
class AppContainer:
    settings: Settings
    database: Any
    dispatcher: RecordingAgentDispatcher
    outbound_mailer: RecordingOutboundMailer
    email_webhook: EmailWebhookUseCase
    operational_queries: OperationalQueries
    create_request: CreateRequestUseCase
    quote_workflow: QuoteWorkflow
    quote_response_workflow: QuoteResponseWorkflow
    booking_workflow: BookingWorkflow
    shipment_workflow: ShipmentWorkflow
    invoice_audit: InvoiceAuditWorkflow
    process_outbound_queue: ProcessOutboundQueueUseCase
    tracking_simulator: TrackingSimulator
    shipment_repository: ShipmentWriteRepository


def build_container(settings: Settings | None = None) -> AppContainer:
    resolved_settings = settings or Settings.from_env()
    if resolved_settings.persistence_driver is PersistenceDriver.POSTGRES:
        return _build_postgres_container(resolved_settings)
    return _build_sqlite_container(resolved_settings)


def _build_sqlite_container(settings: Settings) -> AppContainer:
    database = SQLiteDatabase(settings.sqlite_path)
    dispatcher = RecordingAgentDispatcher()
    outbound_mailer = RecordingOutboundMailer()
    operational_queries = OperationalQueries(SQLiteOperationalReadRepository(database))
    quote_repository = SQLiteQuoteWriteRepository(database)
    quote_response_repository = SQLiteQuoteResponseEventRepository(database)
    outbound_repository = SQLiteOutboundReplyRepository(database)
    shipment_repository = SQLiteShipmentWriteRepository(database)
    shipment_event_repository = SQLiteShipmentEventRepository(database)
    shipment_workflow = ShipmentWorkflow(shipment_repository, shipment_event_repository)
    invoice_repository = SQLiteInvoiceWriteRepository(database)
    invoice_audit = InvoiceAuditWorkflow(invoice_repository, shipment_workflow)
    task_repository = SQLiteOperationalTaskWriteRepository(database)

    booking_workflow = BookingWorkflow(
        quote_repository,
        shipment_repository,
        operational_queries,
    )

    return AppContainer(
        settings=settings,
        database=database,
        dispatcher=dispatcher,
        outbound_mailer=outbound_mailer,
        email_webhook=EmailWebhookUseCase(
            SQLiteWebhookEventRepository(database),
            SQLiteInboundEmailRepository(database),
            dispatcher,
        ),
        operational_queries=operational_queries,
        create_request=CreateRequestUseCase(
            SQLiteRequestWriteRepository(database),
            task_repository,
        ),
        quote_workflow=QuoteWorkflow(quote_repository, outbound_repository),
        quote_response_workflow=QuoteResponseWorkflow(
            quote_repository,
            quote_response_repository,
            booking_workflow,
        ),
        booking_workflow=booking_workflow,
        shipment_workflow=shipment_workflow,
        invoice_audit=invoice_audit,
        process_outbound_queue=ProcessOutboundQueueUseCase(outbound_repository, outbound_mailer),
        tracking_simulator=TrackingSimulator(
            operational_queries,
            shipment_workflow,
            invoice_repository,
            invoice_audit,
        ),
        shipment_repository=shipment_repository,
    )


def _build_postgres_container(settings: Settings) -> AppContainer:
    if settings.database_url is None:
        raise RuntimeError("DATABASE_URL is required when QINORA_PERSISTENCE=postgres")

    database = PostgresDatabase(settings.database_url, settings.postgres_tenant_id)
    dispatcher = RecordingAgentDispatcher()
    outbound_mailer = RecordingOutboundMailer()
    operational_queries = OperationalQueries(PostgresOperationalReadRepository(database))
    quote_repository = PostgresQuoteWriteRepository(database)
    quote_response_repository = PostgresQuoteResponseEventRepository(database)
    outbound_repository = PostgresOutboundReplyRepository(database)
    shipment_repository = PostgresShipmentWriteRepository(database)
    shipment_event_repository = PostgresShipmentEventRepository(database)
    shipment_workflow = ShipmentWorkflow(shipment_repository, shipment_event_repository)
    invoice_repository = PostgresInvoiceWriteRepository(database)
    invoice_audit = InvoiceAuditWorkflow(invoice_repository, shipment_workflow)
    task_repository = PostgresOperationalTaskWriteRepository(database)

    booking_workflow = BookingWorkflow(
        quote_repository,
        shipment_repository,
        operational_queries,
    )

    return AppContainer(
        settings=settings,
        database=database,
        dispatcher=dispatcher,
        outbound_mailer=outbound_mailer,
        email_webhook=EmailWebhookUseCase(
            PostgresWebhookEventRepository(database),
            PostgresInboundEmailRepository(database),
            dispatcher,
        ),
        operational_queries=operational_queries,
        create_request=CreateRequestUseCase(
            PostgresRequestWriteRepository(database),
            task_repository,
        ),
        quote_workflow=QuoteWorkflow(quote_repository, outbound_repository),
        quote_response_workflow=QuoteResponseWorkflow(
            quote_repository,
            quote_response_repository,
            booking_workflow,
        ),
        booking_workflow=booking_workflow,
        shipment_workflow=shipment_workflow,
        invoice_audit=invoice_audit,
        process_outbound_queue=ProcessOutboundQueueUseCase(outbound_repository, outbound_mailer),
        tracking_simulator=TrackingSimulator(
            operational_queries,
            shipment_workflow,
            invoice_repository,
            invoice_audit,
        ),
        shipment_repository=shipment_repository,
    )
