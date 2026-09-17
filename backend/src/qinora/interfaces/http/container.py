from dataclasses import dataclass
from pathlib import Path
from typing import Any

from qinora.application import (
    AgentConfigService,
    AnalyzeRFQUseCase,
    BookingWorkflow,
    CarrierOfferParsingAgent,
    CarrierRfqCollector,
    CarrierRfqTargeting,
    CaseNotesService,
    ContactMatchingUseCase,
    CreateRequestUseCase,
    DemoFlowUseCase,
    DocumentIntakeService,
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
    UpdateRequestUseCase,
)
from qinora.application.email_intake_orchestrator import EmailIntakeOrchestrator
from qinora.application.llm_ports import GraphExecutor
from qinora.application.ports import (
    AgentDispatcher,
    CarrierOfferParsingLLM,
    CarrierOfferReportOutboundRepository,
    CarrierRfqOutboundRepository,
    CarrierRfqRepository,
    CarrierWriteRepository,
    CaseNoteRepository,
    ClarificationOutboundRepository,
    DocumentRepository,
    OutboundReplyRepository,
    QuoteReplyInterpretationLLM,
    RateProfileRepository,
    RequestParsingLLM,
    RequestWriteRepository,
    ShipmentWriteRepository,
    UserRepository,
)
from qinora.application.pricing_engine import PricingEngine
from qinora.application.thread_matching import ThreadMatchingUseCase
from qinora.infrastructure.email_dispatch import EmailIntakeDispatcher
from qinora.infrastructure.llm import (
    OpenAICarrierOfferParsingLLM,
    OpenAIGraphExecutor,
    OpenAIQuoteReplyInterpretationLLM,
    OpenAIRequestParsingLLM,
    StubCarrierOfferParsingLLM,
    StubGraphExecutor,
    StubQuoteReplyInterpretationLLM,
    StubRequestParsingLLM,
)
from qinora.infrastructure.migrations import iter_migration_files, run_migrations
from qinora.infrastructure.outbound_mailer import RecordingOutboundMailer
from qinora.infrastructure.postgres import (
    PostgresAgentConfigRepository,
    PostgresAgentLogWriteRepository,
    PostgresCarrierOfferReportOutboundRepository,
    PostgresCarrierOfferWriteRepository,
    PostgresCarrierRfqOutboundRepository,
    PostgresCarrierRfqRepository,
    PostgresCarrierWriteRepository,
    PostgresCaseNoteRepository,
    PostgresClarificationOutboundRepository,
    PostgresContactReadRepository,
    PostgresDatabase,
    PostgresDocumentRepository,
    PostgresEmailThreadRepository,
    PostgresInboundEmailRepository,
    PostgresInvoiceWriteRepository,
    PostgresOperationalReadRepository,
    PostgresOperationalTaskWriteRepository,
    PostgresOutboundReplyRepository,
    PostgresQuoteResponseEventRepository,
    PostgresQuoteWriteRepository,
    PostgresRateProfileRepository,
    PostgresRequestWriteRepository,
    PostgresShipmentEventRepository,
    PostgresShipmentWriteRepository,
    PostgresStaleRequestRepository,
    PostgresUserRepository,
    PostgresWebhookEventRepository,
)
from qinora.infrastructure.settings import LLMProvider, PersistenceDriver, Settings
from qinora.infrastructure.sqlite import (
    SQLiteAgentConfigRepository,
    SQLiteAgentLogWriteRepository,
    SQLiteCarrierOfferReportOutboundRepository,
    SQLiteCarrierOfferWriteRepository,
    SQLiteCarrierRfqOutboundRepository,
    SQLiteCarrierRfqRepository,
    SQLiteCarrierWriteRepository,
    SQLiteCaseNoteRepository,
    SQLiteClarificationOutboundRepository,
    SQLiteContactReadRepository,
    SQLiteDatabase,
    SQLiteDocumentRepository,
    SQLiteEmailThreadRepository,
    SQLiteInboundEmailRepository,
    SQLiteInvoiceWriteRepository,
    SQLiteOperationalReadRepository,
    SQLiteOperationalTaskWriteRepository,
    SQLiteOutboundReplyRepository,
    SQLiteQuoteResponseEventRepository,
    SQLiteQuoteWriteRepository,
    SQLiteRateProfileRepository,
    SQLiteRequestWriteRepository,
    SQLiteShipmentEventRepository,
    SQLiteShipmentWriteRepository,
    SQLiteStaleRequestRepository,
    SQLiteUserRepository,
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


def build_graph_executor(settings: Settings) -> GraphExecutor:
    if settings.llm_provider is LLMProvider.OPENAI:
        return OpenAIGraphExecutor(settings)
    return StubGraphExecutor()


@dataclass(frozen=True)
class AppContainer:
    settings: Settings
    database: Any
    dispatcher: AgentDispatcher
    outbound_mailer: RecordingOutboundMailer
    demo_flow: DemoFlowUseCase
    agent_config_service: AgentConfigService
    email_webhook: EmailWebhookUseCase
    operational_queries: OperationalQueries
    create_request: CreateRequestUseCase
    update_request: UpdateRequestUseCase
    quote_workflow: QuoteWorkflow
    quote_response_workflow: QuoteResponseWorkflow
    booking_workflow: BookingWorkflow
    shipment_workflow: ShipmentWorkflow
    invoice_audit: InvoiceAuditWorkflow
    process_outbound_queue: ProcessOutboundQueueUseCase
    outbound_reply_repository: OutboundReplyRepository
    stale_request_escalator: StaleRequestEscalator
    tracking_simulator: TrackingSimulator
    shipment_repository: ShipmentWriteRepository
    request_repository: RequestWriteRepository
    request_parsing_agent: RequestParsingAgent
    carrier_offer_agent: CarrierOfferParsingAgent
    rate_profile_repository: RateProfileRepository
    pricing_engine: PricingEngine
    carrier_rfq_targeting: CarrierRfqTargeting
    carrier_rfq_repository: CarrierRfqRepository
    carrier_rfq_outbound_repository: CarrierRfqOutboundRepository
    carrier_offer_report_outbound_repository: CarrierOfferReportOutboundRepository
    clarification_outbound_repository: ClarificationOutboundRepository
    carrier_write_repository: CarrierWriteRepository
    carrier_rfq_collector: CarrierRfqCollector
    email_intake_orchestrator: EmailIntakeOrchestrator
    graph_executor: GraphExecutor
    analyze_rfq_use_case: AnalyzeRFQUseCase
    document_repository: DocumentRepository
    document_intake_service: DocumentIntakeService
    case_note_repository: CaseNoteRepository
    case_notes_service: CaseNotesService
    user_repository: UserRepository


def build_container(settings: Settings | None = None) -> AppContainer:
    resolved_settings = settings or Settings.from_env()
    if resolved_settings.persistence_driver is PersistenceDriver.POSTGRES:
        return _build_postgres_container(resolved_settings)
    return _build_sqlite_container(resolved_settings)


def _build_sqlite_container(settings: Settings) -> AppContainer:
    database = SQLiteDatabase(settings.sqlite_path)
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
    contact_read_repository = SQLiteContactReadRepository(database)
    contact_matching = ContactMatchingUseCase(
        contact_read_repository,
        SQLiteAgentLogWriteRepository(database),
    )

    carrier_rfq_repository = SQLiteCarrierRfqRepository(database)
    carrier_write_repository = SQLiteCarrierWriteRepository(database)
    email_thread_repository = SQLiteEmailThreadRepository(database)

    booking_workflow = BookingWorkflow(
        quote_repository,
        shipment_repository,
        operational_queries,
        carrier_rfq_repository,
        outbound_repository,
        email_thread_repository,
        customer_mailbox=settings.customer_mailbox,
    )

    request_repository = SQLiteRequestWriteRepository(database)
    create_request = CreateRequestUseCase(request_repository, task_repository)
    update_request = UpdateRequestUseCase(request_repository, task_repository)
    quote_workflow = QuoteWorkflow(
        quote_repository,
        outbound_repository,
        operational_queries,
        email_thread_repository,
        customer_mailbox=settings.customer_mailbox,
    )
    process_outbound_queue = ProcessOutboundQueueUseCase(outbound_repository, outbound_mailer)
    agent_log_repository = SQLiteAgentLogWriteRepository(database)

    rate_profile_repository = SQLiteRateProfileRepository(database)
    carrier_offer_repository = SQLiteCarrierOfferWriteRepository(database)
    carrier_rfq_outbound_repository = SQLiteCarrierRfqOutboundRepository(database)
    carrier_offer_report_outbound_repository = SQLiteCarrierOfferReportOutboundRepository(
        database
    )
    clarification_outbound_repository = SQLiteClarificationOutboundRepository(database)
    carrier_rfq_targeting = CarrierRfqTargeting(operational_queries)
    pricing_engine = PricingEngine(
        rate_profile_repository,
        quote_workflow,
        task_repository,
        settings.default_markup_percent,
        carrier_rfq_targeting,
        carrier_rfq_repository,
        carrier_rfq_outbound_repository,
        request_repository,
        carrier_mailbox=settings.carrier_mailbox,
        clarification_outbound=clarification_outbound_repository,
        customer_mailbox=settings.customer_mailbox,
    )

    request_parsing_agent = RequestParsingAgent(
        build_request_parsing_llm(settings),
        create_request,
        agent_log_repository,
        agent_config_service,
        update_request=update_request,
        task_repository=task_repository,
        clarification_outbound=clarification_outbound_repository,
        customer_mailbox=settings.customer_mailbox,
    )
    carrier_offer_agent = CarrierOfferParsingAgent(
        build_carrier_offer_parsing_llm(settings),
        carrier_offer_repository,
        agent_log_repository,
        agent_config_service,
    )
    carrier_rfq_collector = CarrierRfqCollector(
        carrier_rfq_repository,
        carrier_offer_repository,
        email_thread_repository,
        contact_read_repository,
        quote_workflow,
        task_repository,
        request_repository,
        settings.default_markup_percent,
        carrier_offer_report_outbound=carrier_offer_report_outbound_repository,
        carrier_mailbox=settings.carrier_mailbox,
        customer_mailbox=settings.customer_mailbox,
    )

    email_intake_orchestrator = EmailIntakeOrchestrator(
        agent_config_service,
        contact_matching,
        ThreadMatchingUseCase(email_thread_repository),
        email_thread_repository,
        operational_queries,
        booking_workflow,
        task_repository,
        request_parsing_agent,
        pricing_engine,
        carrier_rfq_repository,
        carrier_offer_agent,
        carrier_rfq_collector,
        build_quote_reply_interpretation_llm(settings),
        carrier_mailbox=settings.carrier_mailbox,
        clarification_outbound=clarification_outbound_repository,
        customer_mailbox=settings.customer_mailbox,
    )
    dispatcher: AgentDispatcher = EmailIntakeDispatcher(email_intake_orchestrator)
    graph_executor = build_graph_executor(settings)
    analyze_rfq_use_case = AnalyzeRFQUseCase(graph_executor)

    document_repository = SQLiteDocumentRepository(database)
    document_intake_service = DocumentIntakeService(document_repository)
    case_note_repository = SQLiteCaseNoteRepository(database)
    case_notes_service = CaseNotesService(case_note_repository)

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
        ),
        operational_queries=operational_queries,
        create_request=create_request,
        update_request=update_request,
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
        outbound_reply_repository=outbound_repository,
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
        request_repository=request_repository,
        request_parsing_agent=request_parsing_agent,
        carrier_offer_agent=carrier_offer_agent,
        rate_profile_repository=rate_profile_repository,
        pricing_engine=pricing_engine,
        carrier_rfq_targeting=carrier_rfq_targeting,
        carrier_rfq_repository=carrier_rfq_repository,
        carrier_rfq_outbound_repository=carrier_rfq_outbound_repository,
        carrier_offer_report_outbound_repository=carrier_offer_report_outbound_repository,
        clarification_outbound_repository=clarification_outbound_repository,
        carrier_write_repository=carrier_write_repository,
        carrier_rfq_collector=carrier_rfq_collector,
        email_intake_orchestrator=email_intake_orchestrator,
        graph_executor=graph_executor,
        analyze_rfq_use_case=analyze_rfq_use_case,
        document_repository=document_repository,
        document_intake_service=document_intake_service,
        case_note_repository=case_note_repository,
        case_notes_service=case_notes_service,
        user_repository=SQLiteUserRepository(database),
    )


def _build_postgres_container(settings: Settings) -> AppContainer:
    if settings.database_url is None:
        raise RuntimeError("DATABASE_URL is required when QINORA_PERSISTENCE=postgres")

    run_migrations(settings.database_url, iter_migration_files(Path("migrations")))

    database = PostgresDatabase(settings.database_url, settings.postgres_tenant_id)
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
    contact_read_repository = PostgresContactReadRepository(database)
    contact_matching = ContactMatchingUseCase(
        contact_read_repository,
        PostgresAgentLogWriteRepository(database),
    )

    carrier_rfq_repository = PostgresCarrierRfqRepository(database)
    carrier_write_repository = PostgresCarrierWriteRepository(database)
    email_thread_repository = PostgresEmailThreadRepository(database)

    booking_workflow = BookingWorkflow(
        quote_repository,
        shipment_repository,
        operational_queries,
        carrier_rfq_repository,
        outbound_repository,
        email_thread_repository,
        customer_mailbox=settings.customer_mailbox,
    )

    request_repository = PostgresRequestWriteRepository(database)
    create_request = CreateRequestUseCase(request_repository, task_repository)
    update_request = UpdateRequestUseCase(request_repository, task_repository)
    quote_workflow = QuoteWorkflow(
        quote_repository,
        outbound_repository,
        operational_queries,
        email_thread_repository,
        customer_mailbox=settings.customer_mailbox,
    )
    process_outbound_queue = ProcessOutboundQueueUseCase(outbound_repository, outbound_mailer)
    agent_log_repository = PostgresAgentLogWriteRepository(database)

    rate_profile_repository = PostgresRateProfileRepository(database)
    carrier_offer_repository = PostgresCarrierOfferWriteRepository(database)
    carrier_rfq_outbound_repository = PostgresCarrierRfqOutboundRepository(database)
    carrier_offer_report_outbound_repository = PostgresCarrierOfferReportOutboundRepository(
        database
    )
    clarification_outbound_repository = PostgresClarificationOutboundRepository(database)
    carrier_rfq_targeting = CarrierRfqTargeting(operational_queries)
    pricing_engine = PricingEngine(
        rate_profile_repository,
        quote_workflow,
        task_repository,
        settings.default_markup_percent,
        carrier_rfq_targeting,
        carrier_rfq_repository,
        carrier_rfq_outbound_repository,
        request_repository,
        carrier_mailbox=settings.carrier_mailbox,
        clarification_outbound=clarification_outbound_repository,
        customer_mailbox=settings.customer_mailbox,
    )

    request_parsing_agent = RequestParsingAgent(
        build_request_parsing_llm(settings),
        create_request,
        agent_log_repository,
        agent_config_service,
        update_request=update_request,
        task_repository=task_repository,
        clarification_outbound=clarification_outbound_repository,
        customer_mailbox=settings.customer_mailbox,
    )
    carrier_offer_agent = CarrierOfferParsingAgent(
        build_carrier_offer_parsing_llm(settings),
        carrier_offer_repository,
        agent_log_repository,
        agent_config_service,
    )
    carrier_rfq_collector = CarrierRfqCollector(
        carrier_rfq_repository,
        carrier_offer_repository,
        email_thread_repository,
        contact_read_repository,
        quote_workflow,
        task_repository,
        request_repository,
        settings.default_markup_percent,
        carrier_offer_report_outbound=carrier_offer_report_outbound_repository,
        carrier_mailbox=settings.carrier_mailbox,
        customer_mailbox=settings.customer_mailbox,
    )

    email_intake_orchestrator = EmailIntakeOrchestrator(
        agent_config_service,
        contact_matching,
        ThreadMatchingUseCase(email_thread_repository),
        email_thread_repository,
        operational_queries,
        booking_workflow,
        task_repository,
        request_parsing_agent,
        pricing_engine,
        carrier_rfq_repository,
        carrier_offer_agent,
        carrier_rfq_collector,
        build_quote_reply_interpretation_llm(settings),
        carrier_mailbox=settings.carrier_mailbox,
        clarification_outbound=clarification_outbound_repository,
        customer_mailbox=settings.customer_mailbox,
    )
    dispatcher: AgentDispatcher = EmailIntakeDispatcher(email_intake_orchestrator)
    graph_executor = build_graph_executor(settings)
    analyze_rfq_use_case = AnalyzeRFQUseCase(graph_executor)

    document_repository = PostgresDocumentRepository(database)
    document_intake_service = DocumentIntakeService(document_repository)
    case_note_repository = PostgresCaseNoteRepository(database)
    case_notes_service = CaseNotesService(case_note_repository)

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
        ),
        operational_queries=operational_queries,
        create_request=create_request,
        update_request=update_request,
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
        outbound_reply_repository=outbound_repository,
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
        request_repository=request_repository,
        request_parsing_agent=request_parsing_agent,
        carrier_offer_agent=carrier_offer_agent,
        rate_profile_repository=rate_profile_repository,
        pricing_engine=pricing_engine,
        carrier_rfq_targeting=carrier_rfq_targeting,
        carrier_rfq_repository=carrier_rfq_repository,
        carrier_rfq_outbound_repository=carrier_rfq_outbound_repository,
        carrier_offer_report_outbound_repository=carrier_offer_report_outbound_repository,
        clarification_outbound_repository=clarification_outbound_repository,
        carrier_write_repository=carrier_write_repository,
        carrier_rfq_collector=carrier_rfq_collector,
        email_intake_orchestrator=email_intake_orchestrator,
        graph_executor=graph_executor,
        analyze_rfq_use_case=analyze_rfq_use_case,
        document_repository=document_repository,
        document_intake_service=document_intake_service,
        case_note_repository=case_note_repository,
        case_notes_service=case_notes_service,
        user_repository=PostgresUserRepository(database),
    )
