from dataclasses import dataclass
from typing import Any

from qinora.application import (
    BookingWorkflow,
    CreateRequestUseCase,
    EmailWebhookUseCase,
    InvoiceAuditWorkflow,
    OperationalQueries,
    QuoteWorkflow,
)
from qinora.application.ports import ShipmentWriteRepository
from qinora.infrastructure.in_memory import RecordingAgentDispatcher
from qinora.infrastructure.postgres import (
    PostgresDatabase,
    PostgresInboundEmailRepository,
    PostgresInvoiceWriteRepository,
    PostgresOperationalReadRepository,
    PostgresQuoteWriteRepository,
    PostgresRequestWriteRepository,
    PostgresShipmentWriteRepository,
    PostgresWebhookEventRepository,
)
from qinora.infrastructure.settings import PersistenceDriver, Settings
from qinora.infrastructure.sqlite import (
    SQLiteDatabase,
    SQLiteInboundEmailRepository,
    SQLiteInvoiceWriteRepository,
    SQLiteOperationalReadRepository,
    SQLiteQuoteWriteRepository,
    SQLiteRequestWriteRepository,
    SQLiteShipmentWriteRepository,
    SQLiteWebhookEventRepository,
)


@dataclass(frozen=True)
class AppContainer:
    settings: Settings
    database: Any
    dispatcher: RecordingAgentDispatcher
    email_webhook: EmailWebhookUseCase
    operational_queries: OperationalQueries
    create_request: CreateRequestUseCase
    quote_workflow: QuoteWorkflow
    booking_workflow: BookingWorkflow
    invoice_audit: InvoiceAuditWorkflow
    shipment_repository: ShipmentWriteRepository


def build_container(settings: Settings | None = None) -> AppContainer:
    resolved_settings = settings or Settings.from_env()
    if resolved_settings.persistence_driver is PersistenceDriver.POSTGRES:
        return _build_postgres_container(resolved_settings)
    return _build_sqlite_container(resolved_settings)


def _build_sqlite_container(settings: Settings) -> AppContainer:
    database = SQLiteDatabase(settings.sqlite_path)
    dispatcher = RecordingAgentDispatcher()
    operational_queries = OperationalQueries(SQLiteOperationalReadRepository(database))
    quote_repository = SQLiteQuoteWriteRepository(database)
    shipment_repository = SQLiteShipmentWriteRepository(database)

    return AppContainer(
        settings=settings,
        database=database,
        dispatcher=dispatcher,
        email_webhook=EmailWebhookUseCase(
            SQLiteWebhookEventRepository(database),
            SQLiteInboundEmailRepository(database),
            dispatcher,
        ),
        operational_queries=operational_queries,
        create_request=CreateRequestUseCase(SQLiteRequestWriteRepository(database)),
        quote_workflow=QuoteWorkflow(quote_repository),
        booking_workflow=BookingWorkflow(
            quote_repository,
            shipment_repository,
            operational_queries,
        ),
        invoice_audit=InvoiceAuditWorkflow(
            SQLiteInvoiceWriteRepository(database),
            shipment_repository,
        ),
        shipment_repository=shipment_repository,
    )


def _build_postgres_container(settings: Settings) -> AppContainer:
    if settings.database_url is None:
        raise RuntimeError("DATABASE_URL is required when QINORA_PERSISTENCE=postgres")

    database = PostgresDatabase(settings.database_url, settings.postgres_tenant_id)
    dispatcher = RecordingAgentDispatcher()
    operational_queries = OperationalQueries(PostgresOperationalReadRepository(database))
    quote_repository = PostgresQuoteWriteRepository(database)
    shipment_repository = PostgresShipmentWriteRepository(database)

    return AppContainer(
        settings=settings,
        database=database,
        dispatcher=dispatcher,
        email_webhook=EmailWebhookUseCase(
            PostgresWebhookEventRepository(database),
            PostgresInboundEmailRepository(database),
            dispatcher,
        ),
        operational_queries=operational_queries,
        create_request=CreateRequestUseCase(PostgresRequestWriteRepository(database)),
        quote_workflow=QuoteWorkflow(quote_repository),
        booking_workflow=BookingWorkflow(
            quote_repository,
            shipment_repository,
            operational_queries,
        ),
        invoice_audit=InvoiceAuditWorkflow(
            PostgresInvoiceWriteRepository(database),
            shipment_repository,
        ),
        shipment_repository=shipment_repository,
    )
