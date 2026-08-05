from dataclasses import dataclass
from pathlib import Path
from typing import Any

from qinora.application import (
    AgentConfigService,
    BookingWorkflow,
    CarrierOfferParsingAgent,
    ContactMatchingUseCase,
    CreateRequestUseCase,
    DemoFlowUseCase,
    EmailWebhookUseCase,
    InvoiceAuditWorkflow,
    OperationalQueries,
    ProcessOutboundQueueUseCase,
    QuoteResponseWorkflow,
    QuoteWorkflow,
    RequestParsingAgent,
    ShipmentWorkflow,
    StaleRequestEscalator,
    TrackingSimulator,
)
from qinora.application.ports import (
    CarrierOfferParsingLLM,
    QuoteReplyInterpretationLLM,
    RequestParsingLLM,
    ShipmentWriteRepository,
)
from qinora.infrastructure.in_memory import RecordingAgentDispatcher
from qinora.infrastructure.llm import (
    OpenAICarrierOfferParsingLLM,
    OpenAIQuoteReplyInterpretationLLM,
    OpenAIRequestParsingLLM,
    StubCarrierOfferParsingLLM,
    StubQuoteReplyInterpretationLLM,
    StubRequestParsingLLM,
)
from qinora.infrastructure.migrations import iter_migration_files, run_migrations
from qinora.infrastructure.outbound_mailer import RecordingOutboundMailer
from qinora.infrastructure.postgres import (
    PostgresAgentConfigRepository,
    PostgresAgentLogWriteRepository,
    PostgresCarrierOfferWriteRepository,
    PostgresContactReadRepository,
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
    PostgresStaleRequestRepository,
    PostgresWebhookEventRepository,
)
from qinora.infrastructure.settings import LLMProvider, PersistenceDriver, Settings
from qinora.infrastructure.sqlite import (
    SQLiteAgentConfigRepository,
    SQLiteAgentLogWriteRepository,
    SQLiteCarrierOfferWriteRepository,
    SQLiteContactReadRepository,
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
    SQLiteStaleRequestRepository,
    SQLiteWebhookEventRepository,
)


def build_request_parsing_llm(settings: Settings) -> RequestParsingLLM:
    if settings.llm_provider is LLMProvider.OPENAI:
        return OpenAIRequestParsingLLM(settings)
    return StubRequestParsingLLM()


def build_carrier_offer_parsing_llm(settings: Settings) -> CarrierOfferParsingLLM:
    if settings.llm_provider is LLMProvider.OPENAI:
        return OpenAICarrierOfferParsingLLM(settings)
    return StubCarrierOfferParsingLLM()


def build_quote_reply_interpretation_llm(settings: Settings) -> QuoteReplyInterpretationLLM:
    if settings.llm_provider is LLMProvider.OPENAI:
        return OpenAIQuoteReplyInterpretationLLM(settings)
    return StubQuoteReplyInterpretationLLM()


@dataclass(frozen=True)
class AppContainer:
    settings: Settings
    database: Any
    dispatcher: RecordingAgentDispatcher
    outbound_mailer: RecordingOutboundMailer
    demo_flow: DemoFlowUseCase
    agent_config_service: AgentConfigService
    email_webhook: EmailWebhookUseCase
    operational_queries: OperationalQueries
    create_request: CreateRequestUseCase
    quote_workflow: QuoteWorkflow
    quote_response_workflow: QuoteResponseWorkflow
    booking_workflow: BookingWorkflow
    shipment_workflow: ShipmentWorkflow
    invoice_audit: InvoiceAuditWorkflow
    process_outbound_queue: ProcessOutboundQueueUseCase
    stale_request_escalator: StaleRequestEscalator
    tracking_simulator: TrackingSimulator
    shipment_repository: ShipmentWriteRepository
    request_parsing_agent: RequestParsingAgent
    carrier_offer_agent: CarrierOfferParsingAgent


def build_container(settings: Settings | None = None) -> AppContainer:
    resolved_settings = settings or Settings.from_env()
    if resolved_settings.persistence_driver is PersistenceDriver.POSTGRES:
        return _build_postgres_container(resolved_settings)
    return _build_sqlite_container(resolved_settings)


def _build_sqlite_container(settings: Settings) -> AppContainer:
    database = SQLiteDatabase(settings.sqlite_path)
    dispatcher = RecordingAgentDispatcher()
    outbound_mailer = RecordingOutboundMailer()
    agent_config_service = AgentConfigService(SQLiteAgentConfigRepository(database))
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
    contact_matching = ContactMatchingUseCase(
        SQLiteContactReadRepository(database),
        SQLiteAgentLogWriteRepository(database),
    )

    booking_workflow = BookingWorkflow(
        quote_repository,
        shipment_repository,
        operational_queries,
    )

    create_request = CreateRequestUseCase(
        SQLiteRequestWriteRepository(database),
        task_repository,
    )
    quote_workflow = QuoteWorkflow(quote_repository, outbound_repository, operational_queries)
    process_outbound_queue = ProcessOutboundQueueUseCase(outbound_repository, outbound_mailer)
    agent_log_repository = SQLiteAgentLogWriteRepository(database)

    return AppContainer(
        settings=settings,
        database=database,
        dispatcher=dispatcher,
        outbound_mailer=outbound_mailer,
        demo_flow=DemoFlowUseCase(
            create_request,
            quote_workflow,
            process_outbound_queue,
            booking_workflow,
            shipment_workflow,
            invoice_audit,
        ),
        agent_config_service=agent_config_service,
        email_webhook=EmailWebhookUseCase(
            SQLiteWebhookEventRepository(database),
            SQLiteInboundEmailRepository(database),
            dispatcher,
            contact_matching,
        ),
        operational_queries=operational_queries,
        create_request=create_request,
        quote_workflow=quote_workflow,
        quote_response_workflow=QuoteResponseWorkflow(
            quote_repository,
            quote_response_repository,
            booking_workflow,
            build_quote_reply_interpretation_llm(settings),
            agent_log_repository,
            agent_config_service,
        ),
        booking_workflow=booking_workflow,
        shipment_workflow=shipment_workflow,
        invoice_audit=invoice_audit,
        process_outbound_queue=process_outbound_queue,
        stale_request_escalator=StaleRequestEscalator(
            SQLiteStaleRequestRepository(database),
            task_repository,
        ),
        tracking_simulator=TrackingSimulator(
            operational_queries,
            shipment_workflow,
            invoice_repository,
            invoice_audit,
        ),
        shipment_repository=shipment_repository,
        request_parsing_agent=RequestParsingAgent(
            build_request_parsing_llm(settings),
            create_request,
            agent_log_repository,
            agent_config_service,
        ),
        carrier_offer_agent=CarrierOfferParsingAgent(
            build_carrier_offer_parsing_llm(settings),
            SQLiteCarrierOfferWriteRepository(database),
            agent_log_repository,
            agent_config_service,
        ),
    )


def _build_postgres_container(settings: Settings) -> AppContainer:
    if settings.database_url is None:
        raise RuntimeError("DATABASE_URL is required when QINORA_PERSISTENCE=postgres")

    run_migrations(settings.database_url, iter_migration_files(Path("migrations")))

    database = PostgresDatabase(settings.database_url, settings.postgres_tenant_id)
    dispatcher = RecordingAgentDispatcher()
    outbound_mailer = RecordingOutboundMailer()
    agent_config_service = AgentConfigService(PostgresAgentConfigRepository(database))
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
    contact_matching = ContactMatchingUseCase(
        PostgresContactReadRepository(database),
        PostgresAgentLogWriteRepository(database),
    )

    booking_workflow = BookingWorkflow(
        quote_repository,
        shipment_repository,
        operational_queries,
    )

    create_request = CreateRequestUseCase(
        PostgresRequestWriteRepository(database),
        task_repository,
    )
    quote_workflow = QuoteWorkflow(quote_repository, outbound_repository, operational_queries)
    process_outbound_queue = ProcessOutboundQueueUseCase(outbound_repository, outbound_mailer)
    agent_log_repository = PostgresAgentLogWriteRepository(database)

    return AppContainer(
        settings=settings,
        database=database,
        dispatcher=dispatcher,
        outbound_mailer=outbound_mailer,
        demo_flow=DemoFlowUseCase(
            create_request,
            quote_workflow,
            process_outbound_queue,
            booking_workflow,
            shipment_workflow,
            invoice_audit,
        ),
        agent_config_service=agent_config_service,
        email_webhook=EmailWebhookUseCase(
            PostgresWebhookEventRepository(database),
            PostgresInboundEmailRepository(database),
            dispatcher,
            contact_matching,
        ),
        operational_queries=operational_queries,
        create_request=create_request,
        quote_workflow=quote_workflow,
        quote_response_workflow=QuoteResponseWorkflow(
            quote_repository,
            quote_response_repository,
            booking_workflow,
            build_quote_reply_interpretation_llm(settings),
            agent_log_repository,
            agent_config_service,
        ),
        booking_workflow=booking_workflow,
        shipment_workflow=shipment_workflow,
        invoice_audit=invoice_audit,
        process_outbound_queue=process_outbound_queue,
        stale_request_escalator=StaleRequestEscalator(
            PostgresStaleRequestRepository(database),
            task_repository,
        ),
        tracking_simulator=TrackingSimulator(
            operational_queries,
            shipment_workflow,
            invoice_repository,
            invoice_audit,
        ),
        shipment_repository=shipment_repository,
        request_parsing_agent=RequestParsingAgent(
            build_request_parsing_llm(settings),
            create_request,
            agent_log_repository,
            agent_config_service,
        ),
        carrier_offer_agent=CarrierOfferParsingAgent(
            build_carrier_offer_parsing_llm(settings),
            PostgresCarrierOfferWriteRepository(database),
            agent_log_repository,
            agent_config_service,
        ),
    )
