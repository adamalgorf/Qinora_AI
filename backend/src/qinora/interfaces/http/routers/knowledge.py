from contextlib import suppress

from fastapi import APIRouter, Form, HTTPException, Response, UploadFile, status

from qinora.application import AuthContext, Role
from qinora.application.agent_registry import (
    AGENTS,
    KNOWLEDGE_DOMAINS,
    AgentDefinition,
    KnowledgeDomain,
    agents_reading,
    domain_info,
    get_agent,
)
from qinora.application.knowledge import AddKnowledgeDocumentCommand, KnowledgeValidationError
from qinora.application.read_models import KnowledgeDocumentRecord
from qinora.interfaces.http.auth import require_roles
from qinora.interfaces.http.container import AppContainer
from qinora.interfaces.http.dependencies import AUTH_CONTEXT, CONTAINER
from qinora.interfaces.http.schemas import (
    KnowledgeAgentItem,
    KnowledgeDocumentDetailResponse,
    KnowledgeDocumentItem,
    KnowledgeDomainItem,
    KnowledgeOverviewResponse,
    KnowledgePreviewRequest,
    KnowledgePreviewResponse,
    KnowledgeSnippetItem,
)

router = APIRouter()

_WRITE_ROLES = (Role.TOWER, Role.ADMIN, Role.SUPERADMIN)


@router.get("/knowledge/overview", response_model=KnowledgeOverviewResponse)
async def knowledge_overview(
    container: AppContainer = CONTAINER,
    context: AuthContext = AUTH_CONTEXT,
) -> KnowledgeOverviewResponse:
    _ = context
    documents = await container.knowledge_base_service.list_documents()
    return KnowledgeOverviewResponse(
        domains=[
            KnowledgeDomainItem(
                key=info.domain.value,
                label=info.label,
                description=info.description,
                agents=[agent.name for agent in agents_reading(info.domain)],
                document_count=sum(1 for doc in documents if doc.domain == info.domain.value),
            )
            for info in KNOWLEDGE_DOMAINS
        ],
        agents=[_agent_item(agent) for agent in AGENTS],
    )


@router.get("/knowledge", response_model=list[KnowledgeDocumentItem])
async def list_knowledge_documents(
    container: AppContainer = CONTAINER,
    context: AuthContext = AUTH_CONTEXT,
) -> list[KnowledgeDocumentItem]:
    _ = context
    return [
        _document_item(document)
        for document in await container.knowledge_base_service.list_documents()
    ]


@router.get("/knowledge/{document_id}", response_model=KnowledgeDocumentDetailResponse)
async def knowledge_document_detail(
    document_id: str,
    container: AppContainer = CONTAINER,
    context: AuthContext = AUTH_CONTEXT,
) -> KnowledgeDocumentDetailResponse:
    _ = context
    detail = await container.knowledge_base_service.get_document(document_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dokumentet finns inte")
    return KnowledgeDocumentDetailResponse(
        document=_document_item(detail.document), text=detail.text
    )


@router.post(
    "/knowledge",
    response_model=KnowledgeDocumentItem,
    status_code=status.HTTP_201_CREATED,
)
async def add_knowledge_document(
    domain: str = Form(),
    title: str | None = Form(default=None),
    text: str | None = Form(default=None),
    file: UploadFile | None = None,
    container: AppContainer = CONTAINER,
    context: AuthContext = AUTH_CONTEXT,
) -> KnowledgeDocumentItem:
    require_roles(context, *_WRITE_ROLES)
    try:
        record = await container.knowledge_base_service.add_document(
            AddKnowledgeDocumentCommand(
                domain=domain,
                title=title,
                text=text,
                filename=file.filename if file else None,
                content=await file.read() if file else None,
                uploaded_by=context.user_id,
            )
        )
    except KnowledgeValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error
    return _document_item(record)


@router.delete("/knowledge/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_knowledge_document(
    document_id: str,
    container: AppContainer = CONTAINER,
    context: AuthContext = AUTH_CONTEXT,
) -> Response:
    require_roles(context, *_WRITE_ROLES)
    if not await container.knowledge_base_service.delete_document(document_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dokumentet finns inte")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/knowledge/preview", response_model=KnowledgePreviewResponse)
async def preview_agent_knowledge(
    payload: KnowledgePreviewRequest,
    container: AppContainer = CONTAINER,
    context: AuthContext = AUTH_CONTEXT,
) -> KnowledgePreviewResponse:
    """Shows exactly which excerpts an agent would read for a given email -
    the same retrieval the agent runs before acting, so staff can check the
    knowledge base answers the questions they expect it to."""
    _ = context
    agent = get_agent(payload.agent_key)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Okänd agent")
    brief = await container.agent_knowledge.brief_for(agent.key, payload.text)
    return KnowledgePreviewResponse(
        agent=_agent_item(agent),
        snippets=[
            KnowledgeSnippetItem(
                document_id=snippet.document_id,
                title=snippet.title,
                domain=snippet.domain,
                domain_label=_label(snippet.domain),
                text=snippet.text,
                score=snippet.score,
            )
            for snippet in brief.snippets
        ],
    )


def _agent_item(agent: AgentDefinition) -> KnowledgeAgentItem:
    return KnowledgeAgentItem(
        key=agent.key,
        name=agent.name,
        role=agent.role,
        domains=[
            info.domain.value for info in KNOWLEDGE_DOMAINS if info.domain in agent.readable_domains
        ],
    )


def _document_item(document: KnowledgeDocumentRecord) -> KnowledgeDocumentItem:
    readers: list[str] = []
    with suppress(ValueError):
        readers = [agent.name for agent in agents_reading(KnowledgeDomain(document.domain))]
    return KnowledgeDocumentItem(
        **document.__dict__,
        domain_label=_label(document.domain),
        read_by=readers,
    )


def _label(domain: str) -> str:
    try:
        return domain_info(KnowledgeDomain(domain)).label
    except ValueError:
        return domain
