"""Implementations of the CustomerDetailsParsingLLM port ("Nora").

Used by application/customer_onboarding.py after a not-yet-known sender
confirms an order and we ask them for their company details. Reads the
email(s) they sent back and extracts name, org number, address and contact
person. StubCustomerDetailsParsingLLM is the no-credentials fallback: it
never claims a thread contains details, so replies keep their existing
handling instead of being half-parsed by guesswork.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from qinora.application.agent_registry import NORA
from qinora.application.read_models import ParsedCustomerDetails
from qinora.infrastructure.llm.openai_client import KnowledgeGroundedLLM

SYSTEM_PROMPT = """You are Nora, an assistant for the Qinora logistics platform. A new \
customer has just confirmed a transport order by email, and we asked them to send \
their company details so we can register them as a customer and invoice them. \
You read the email thread that followed (oldest message first - the LAST message is \
the newest) and extract those company details.

Fields:
- company_name: the customer's company / organisation name.
- org_number: the organisation number (Swedish: NNNNNN-NNNN) or, for a foreign \
company, its VAT / registration number - exactly as written.
- address: the company's own postal address (street, postal code, city; country if \
given). This is the company's office / invoice address - NEVER a shipment's pickup, \
delivery or loading address.
- contact_person: the full name of the person we should contact about the account.
- contact_email: that person's e-mail address.
- contact_phone: that person's phone number, as written.

Rules:
- provides_details must be true only if the NEWEST message supplies at least one of \
these details (a signature block with company name, phone and address counts). It \
must be false for a bare thanks, a question, a greeting, or a new transport request \
that contains none of them.
- Only extract facts explicitly present in the thread. Never invent or guess a value, \
and use null for anything not stated. Details from earlier messages in the thread \
still count, so combine them with what the newest message adds.
- If the writer clearly is the contact person (they sign the message with their name, \
or say "contact me"), use their name and, for contact_email, the address shown in the \
"Message from" header of their message; take a phone number only if it is written in \
the text.
- confidence must reflect how explicit and unambiguous the extraction is: 1.0 when \
every extracted value is stated plainly, lower if you had to infer, and low (<0.5) \
if the text is too vague to rely on.
"""


class _CustomerDetailsSchema(BaseModel):
    provides_details: bool = Field(
        description="True only if the newest message supplies at least one company detail"
    )
    company_name: str | None = None
    org_number: str | None = None
    address: str | None = None
    contact_person: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)


class StubCustomerDetailsParsingLLM:
    async def parse(self, *, raw_text: str) -> ParsedCustomerDetails:
        _ = raw_text
        return ParsedCustomerDetails(
            provides_details=False,
            company_name=None,
            org_number=None,
            address=None,
            contact_person=None,
            contact_email=None,
            contact_phone=None,
            confidence=0.0,
        )


class OpenAICustomerDetailsParsingLLM(KnowledgeGroundedLLM):
    agent_key = NORA.key

    async def parse(self, *, raw_text: str) -> ParsedCustomerDetails:
        result, brief = await self._complete(
            system_prompt=SYSTEM_PROMPT,
            user_text=raw_text,
            schema=_CustomerDetailsSchema,
        )
        return ParsedCustomerDetails(
            provides_details=result.provides_details,
            company_name=_blank_to_none(result.company_name),
            org_number=_blank_to_none(result.org_number),
            address=_blank_to_none(result.address),
            contact_person=_blank_to_none(result.contact_person),
            contact_email=_blank_to_none(result.contact_email),
            contact_phone=_blank_to_none(result.contact_phone),
            confidence=result.confidence,
            consulted_documents=brief.document_titles,
        )


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None
