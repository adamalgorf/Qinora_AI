from dataclasses import dataclass

from qinora.application import (
    BookingWorkflow,
    CreateRequestUseCase,
    EmailWebhookUseCase,
    InvoiceAuditWorkflow,
    OperationalQueries,
    QuoteWorkflow,
)
from qinora.infrastructure.in_memory import RecordingAgentDispatcher
from qinora.infrastructure.settings import Settings
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
    database: SQLiteDatabase
    dispatcher: RecordingAgentDispatcher
    email_webhook: EmailWebhookUseCase
    operational_queries: OperationalQueries
    create_request: CreateRequestUseCase
    quote_workflow: QuoteWorkflow
    booking_workflow: BookingWorkflow
    invoice_audit: InvoiceAuditWorkflow
    shipment_repository: SQLiteShipmentWriteRepository


def build_container(settings: Settings | None = None) -> AppContainer:
    resolved_settings = settings or Settings.from_env()
    database = SQLiteDatabase(resolved_settings.sqlite_path)
    dispatcher = RecordingAgentDispatcher()
    operational_queries = OperationalQueries(SQLiteOperationalReadRepository(database))
    shipment_repository = SQLiteShipmentWriteRepository(database)

    return AppContainer(
        settings=resolved_settings,
        database=database,
        dispatcher=dispatcher,
        email_webhook=EmailWebhookUseCase(
            SQLiteWebhookEventRepository(database),
            SQLiteInboundEmailRepository(database),
            dispatcher,
        ),
        operational_queries=operational_queries,
        create_request=CreateRequestUseCase(SQLiteRequestWriteRepository(database)),
        quote_workflow=QuoteWorkflow(SQLiteQuoteWriteRepository(database)),
        booking_workflow=BookingWorkflow(
            SQLiteQuoteWriteRepository(database),
            shipment_repository,
            operational_queries,
        ),
        invoice_audit=InvoiceAuditWorkflow(
            SQLiteInvoiceWriteRepository(database),
            shipment_repository,
        ),
        shipment_repository=shipment_repository,
    )
