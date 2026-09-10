from dataclasses import dataclass

from qinora.application.ports import DocumentRepository
from qinora.application.read_models import DocumentRecord

MAX_DOCUMENT_SIZE_BYTES = 8 * 1024 * 1024

ALLOWED_CONTENT_TYPES = frozenset(
    {
        "application/pdf",
        "image/png",
        "image/jpeg",
    }
)

# Placeholder heuristic only - not real OCR/LLM extraction. Maps a declared
# document_type to filename keywords a human would expect to see; used only
# to dock confidence when they don't match.
_DOCUMENT_TYPE_FILENAME_HINTS: dict[str, tuple[str, ...]] = {
    "faktura": ("faktura", "invoice"),
    "cmr": ("cmr",),
    "pod": ("pod",),
    "tullfaktura": ("tull",),
}

_BASE_CONFIDENCE = 0.99
_MISMATCH_PENALTY = 0.15
_MIN_CONFIDENCE = 0.60
_MAX_CONFIDENCE = 0.99


class UnsupportedDocumentError(ValueError):
    """Raised when an upload fails the size or content-type allowlist."""


@dataclass(frozen=True)
class UploadDocumentCommand:
    filename: str
    content_type: str
    content: bytes
    document_type: str | None
    request_id: str | None = None
    shipment_id: str | None = None
    contact_id: str | None = None
    uploaded_by: str | None = None


class DocumentIntakeService:
    def __init__(self, repository: DocumentRepository) -> None:
        self._repository = repository

    async def upload(self, command: UploadDocumentCommand) -> DocumentRecord:
        if len(command.content) > MAX_DOCUMENT_SIZE_BYTES:
            raise UnsupportedDocumentError(
                f"Document exceeds the {MAX_DOCUMENT_SIZE_BYTES // (1024 * 1024)}MB size limit"
            )
        if command.content_type not in ALLOWED_CONTENT_TYPES:
            raise UnsupportedDocumentError(
                f"Unsupported content type: {command.content_type}"
            )

        confidence = _estimate_confidence(command.filename, command.document_type)
        status = _status_from_confidence(confidence)

        return await self._repository.create_document(
            filename=command.filename,
            content_type=command.content_type,
            size_bytes=len(command.content),
            content=command.content,
            document_type=command.document_type,
            status=status,
            ai_confidence=confidence,
            extracted_fields={},
            request_id=command.request_id,
            shipment_id=command.shipment_id,
            contact_id=command.contact_id,
            uploaded_by=command.uploaded_by,
        )


def _estimate_confidence(filename: str, document_type: str | None) -> float:
    """Stub confidence score - not real OCR/LLM extraction, just a
    placeholder heuristic until an actual document-understanding pass
    replaces it: start high, dock confidence if the declared document_type
    doesn't show up as a keyword in the filename, clamp to a plausible
    review range.
    """
    confidence = _BASE_CONFIDENCE
    if document_type:
        hints = _DOCUMENT_TYPE_FILENAME_HINTS.get(document_type.strip().lower(), ())
        name = filename.lower()
        if hints and not any(hint in name for hint in hints):
            confidence -= _MISMATCH_PENALTY
    return max(_MIN_CONFIDENCE, min(_MAX_CONFIDENCE, confidence))


def _status_from_confidence(confidence: float) -> str:
    if confidence >= 0.95:
        return "validated"
    if confidence >= 0.80:
        return "pending_review"
    return "manual_review"
