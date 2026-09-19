"""DocumentTextExtractor implementation for knowledge-base uploads, plus the
revision fingerprint both knowledge repositories share.

Plain-text formats are decoded as UTF-8 (falling back to cp1252, which is
what Swedish Excel/Notepad exports commonly are); PDFs go through pypdf.
A scanned PDF with no text layer yields an empty string, which
KnowledgeBaseService turns into a clear "paste the text instead" error.
"""

import hashlib
import io
from collections.abc import Iterable
from pathlib import PurePath

from pypdf import PdfReader


class PlainTextAndPdfExtractor:
    def extract(self, *, filename: str, content: bytes) -> str:
        if PurePath(filename).suffix.lower() == ".pdf":
            return _pdf_text(content)
        return _decode(content)


def _decode(content: bytes) -> str:
    if content.startswith(b"\xef\xbb\xbf"):
        content = content[3:]
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return content.decode("cp1252", errors="replace")


def _pdf_text(content: bytes) -> str:
    reader = PdfReader(io.BytesIO(content))
    return "\n\n".join((page.extract_text() or "").strip() for page in reader.pages)


def knowledge_revision(document_ids: Iterable[str]) -> str:
    """Fingerprint of the exact set of knowledge documents, shared by both
    repository drivers. Any add or delete changes it, so AgentKnowledge's
    chunk cache can never serve a stale set (a count or max-id marker can
    come out identical after a delete followed by an add)."""
    digest = hashlib.sha1(usedforsecurity=False)
    for document_id in document_ids:
        digest.update(str(document_id).encode())
        digest.update(b",")
    return digest.hexdigest()
