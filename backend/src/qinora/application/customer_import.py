"""Manual customer (contact) creation - one at a time from the Kunder page
form, or in bulk from an uploaded CSV/Excel-export file.

A customer's `domain` is what application/contact_matching.py falls back to
when an inbound sender's exact address is unknown, so it is derived from the
e-mail address automatically - except for public webmail providers
(gmail.com, outlook.com, ...), where a domain match would wrongly attribute
every private sender on that provider to this one customer.
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date

from qinora.application.ports import ContactWriteRepository
from qinora.application.read_models import ContactRecord
from qinora.application.thread_matching import PUBLIC_WEBMAIL_DOMAINS

MAX_IMPORT_ROWS = 5000

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_DOMAIN_RE = re.compile(r"^[a-z0-9-]+(\.[a-z0-9-]+)+$")

# Header aliases (Swedish + English, case/space/underscore-insensitive) ->
# CustomerInput field. Lets a user upload a CRM/Excel export without having
# to rename columns first.
_HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "display_name": (
        "display_name", "name", "namn", "customer", "kund", "kundnamn", "company",
        "företag", "foretag", "företagsnamn", "bolag",
    ),
    "email": ("email", "e-mail", "e-post", "epost", "mail", "e-postadress", "mejl"),
    "domain": ("domain", "domän", "doman", "webbdomän"),
    "default_markup_percent": (
        "default_markup_percent", "markup", "markup_percent", "påslag", "paslag",
        "påslag_%", "påslag_procent", "marginal",
    ),
    "default_incoterms": ("default_incoterms", "incoterms", "incoterm", "leveransvillkor"),
    "payment_terms": ("payment_terms", "betalningsvillkor", "betalvillkor"),
    "segment": ("segment", "bransch", "industry"),
    "customer_since": ("customer_since", "kund_sedan", "kund_sen", "startdatum"),
    "sla_tolerance_hours": (
        "sla_tolerance_hours", "sla", "sla_timmar", "sla-tolerans", "sla_tolerans",
    ),
    "account_owner": ("account_owner", "ansvarig", "kundansvarig", "owner", "säljare"),
    "health_status": ("health_status", "hälsa", "halsa", "status"),
    "contract_note": ("contract_note", "avtal", "avtalsnotering", "anteckning", "notering"),
    "customs_contact_name": ("customs_contact_name", "tullkontakt", "tullkontakt_namn"),
    "customs_contact_email": (
        "customs_contact_email", "tullkontakt_email", "tullkontakt_e-post", "tull_e-post",
    ),
    "annual_volume_estimate": (
        "annual_volume_estimate", "årlig_volym", "arlig_volym", "volym", "annual_volume",
    ),
    "org_number": (
        "org_number", "orgnr", "org_nr", "org.nr", "org.nummer", "organisationsnummer",
        "organization_number", "vat", "vat_number", "momsnummer",
    ),
    "address": ("address", "adress", "postadress", "besöksadress", "besoksadress"),
    "contact_person": ("contact_person", "kontaktperson", "kontakt", "contact"),
    "contact_email": (
        "contact_email", "kontaktperson_e-post", "kontaktperson_email", "kontakt_e-post",
        "kontakt_email",
    ),
    "contact_phone": (
        "contact_phone", "telefon", "telefonnummer", "tel", "mobil", "kontaktperson_telefon",
        "kontakt_telefon", "phone",
    ),
}

_HEALTH_ALIASES = {
    "good": "good", "bra": "good", "god": "good", "ok": "good",
    "watch": "watch", "bevaka": "watch", "bevakas": "watch",
    "at_risk": "at_risk", "at risk": "at_risk", "risk": "at_risk", "i riskzon": "at_risk",
}


ExistingContactsLoader = Callable[[], Awaitable[list[ContactRecord]]]


class CustomerValidationError(ValueError):
    pass


class DuplicateCustomerError(CustomerValidationError):
    """A customer with the same e-mail address or name is already registered."""


@dataclass(frozen=True)
class CustomerInput:
    display_name: str
    email: str | None = None
    domain: str | None = None
    default_markup_percent: float = 0.0
    default_incoterms: str | None = None
    payment_terms: str | None = None
    segment: str | None = None
    customer_since: str | None = None
    sla_tolerance_hours: float | None = None
    account_owner: str | None = None
    health_status: str = "good"
    contract_note: str | None = None
    customs_contact_name: str | None = None
    customs_contact_email: str | None = None
    annual_volume_estimate: float | None = None
    org_number: str | None = None
    contact_person: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    address: str | None = None


@dataclass(frozen=True)
class ImportRowIssue:
    row: int
    display_name: str | None
    reason: str


@dataclass(frozen=True)
class CustomerImportResult:
    created: list[ContactRecord] = field(default_factory=list)
    skipped: list[ImportRowIssue] = field(default_factory=list)
    errors: list[ImportRowIssue] = field(default_factory=list)


def normalize_customer_input(raw: CustomerInput) -> CustomerInput:
    """Trims/validates one customer and derives `domain` from `email`.

    Raises CustomerValidationError with a Swedish, user-facing message.
    """
    display_name = raw.display_name.strip()
    if not display_name:
        raise CustomerValidationError("Kundnamn saknas")

    email = _clean(raw.email)
    if email is not None:
        email = email.lower()
        if not _EMAIL_RE.match(email):
            raise CustomerValidationError(f"Ogiltig e-postadress: {email}")

    domain = _clean(raw.domain)
    if domain is not None:
        domain = domain.lower().removeprefix("@")
        domain = re.sub(r"^https?://", "", domain).removeprefix("www.").rstrip("/")
        if not _DOMAIN_RE.match(domain):
            raise CustomerValidationError(f"Ogiltig domän: {domain}")
        if domain in PUBLIC_WEBMAIL_DOMAINS:
            raise CustomerValidationError(
                f"{domain} är en publik e-posttjänst och kan inte användas som kunddomän"
            )
    elif email is not None:
        email_domain = email.rsplit("@", 1)[1]
        if email_domain not in PUBLIC_WEBMAIL_DOMAINS:
            domain = email_domain

    customs_email = _clean(raw.customs_contact_email)
    if customs_email is not None:
        customs_email = customs_email.lower()
        if not _EMAIL_RE.match(customs_email):
            raise CustomerValidationError(f"Ogiltig e-post för tullkontakt: {customs_email}")

    contact_email = _clean(raw.contact_email)
    if contact_email is not None:
        contact_email = contact_email.lower()
        if not _EMAIL_RE.match(contact_email):
            raise CustomerValidationError(f"Ogiltig e-post för kontaktperson: {contact_email}")

    customer_since = _clean(raw.customer_since)
    if customer_since is not None:
        try:
            customer_since = date.fromisoformat(customer_since).isoformat()
        except ValueError as error:
            raise CustomerValidationError(
                f"Ogiltigt datum för 'kund sedan' (använd ÅÅÅÅ-MM-DD): {customer_since}"
            ) from error

    health_status = _HEALTH_ALIASES.get((raw.health_status or "good").strip().lower())
    if health_status is None:
        raise CustomerValidationError(
            f"Ogiltig hälsostatus: {raw.health_status} (tillåtna: good, watch, at_risk)"
        )

    if raw.default_markup_percent < 0 or raw.default_markup_percent > 1000:
        raise CustomerValidationError("Påslag måste vara mellan 0 och 1000 %")
    for label, value in (
        ("SLA-tolerans", raw.sla_tolerance_hours),
        ("Årlig volym", raw.annual_volume_estimate),
    ):
        if value is not None and value < 0:
            raise CustomerValidationError(f"{label} kan inte vara negativ")

    incoterms = _clean(raw.default_incoterms)
    return CustomerInput(
        display_name=display_name,
        email=email,
        domain=domain,
        default_markup_percent=raw.default_markup_percent,
        default_incoterms=incoterms.upper() if incoterms else None,
        payment_terms=_clean(raw.payment_terms),
        segment=_clean(raw.segment),
        customer_since=customer_since,
        sla_tolerance_hours=raw.sla_tolerance_hours,
        account_owner=_clean(raw.account_owner),
        health_status=health_status,
        contract_note=_clean(raw.contract_note),
        customs_contact_name=_clean(raw.customs_contact_name),
        customs_contact_email=customs_email,
        annual_volume_estimate=raw.annual_volume_estimate,
        org_number=normalize_org_number(raw.org_number),
        contact_person=_clean(raw.contact_person),
        contact_email=contact_email,
        contact_phone=_clean(raw.contact_phone),
        address=_clean(raw.address),
    )


def normalize_org_number(value: str | None) -> str | None:
    """Swedish organisation numbers are shown as NNNNNN-NNNN whether they
    arrive as 5566778899, 556677-8899 or 16556677-8899 (12-digit form);
    anything else (e.g. a foreign VAT number) is kept as typed, trimmed.
    """
    cleaned = _clean(value)
    if cleaned is None:
        return None
    digits = re.sub(r"[\s-]", "", cleaned)
    if digits.isdigit() and len(digits) == 12 and digits.startswith(("16", "19", "20")):
        digits = digits[2:]
    if digits.isdigit() and len(digits) == 10:
        return f"{digits[:6]}-{digits[6:]}"
    return cleaned


def parse_customer_csv(
    content: bytes,
) -> tuple[list[tuple[int, CustomerInput]], list[ImportRowIssue]]:
    """Parses a CSV (comma, semicolon or tab separated; UTF-8 or Windows-1252,
    as Excel exports it) into (row_number, CustomerInput) pairs.

    Row numbers are 1-based spreadsheet rows (header = row 1), so an error
    message points at the row the user sees in Excel. Rows that cannot be
    parsed are returned as issues rather than aborting the whole import.
    """
    text = _decode(content)
    if not text.strip():
        raise CustomerValidationError("Filen är tom")

    # Pick the delimiter from the header row alone - csv.Sniffer is easily
    # fooled by Swedish decimal commas ("12,5") in the data rows.
    header_line = text.lstrip("\ufeff").splitlines()[0]
    delimiter = max(";	,", key=header_line.count)
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)

    header = next(reader, None)
    if not header:
        raise CustomerValidationError("Filen saknar rubrikrad")
    columns = _map_header(header)
    if "display_name" not in columns.values():
        raise CustomerValidationError(
            "Hittar ingen kolumn för kundnamn - rubrikraden måste innehålla t.ex. "
            "'Namn', 'Kundnamn' eller 'display_name'"
        )

    rows: list[tuple[int, CustomerInput]] = []
    issues: list[ImportRowIssue] = []
    for row_number, cells in enumerate(reader, start=2):
        if not any(cell.strip() for cell in cells):
            continue
        if len(rows) + len(issues) >= MAX_IMPORT_ROWS:
            raise CustomerValidationError(f"Filen har fler än {MAX_IMPORT_ROWS} rader")
        values = {
            columns[index]: cell.strip()
            for index, cell in enumerate(cells)
            if index in columns and cell.strip()
        }
        try:
            rows.append((row_number, _customer_input_from_values(values)))
        except CustomerValidationError as error:
            issues.append(ImportRowIssue(row_number, values.get("display_name"), str(error)))
    return rows, issues


class CustomerImportService:
    def __init__(
        self,
        contacts: ContactWriteRepository,
        existing_contacts: ExistingContactsLoader,
    ) -> None:
        self._contacts = contacts
        self._existing_contacts = existing_contacts

    async def create(self, raw: CustomerInput) -> ContactRecord:
        customer = normalize_customer_input(raw)
        existing = await self._existing_contacts()
        duplicate = _duplicate_reason(customer, _DuplicateIndex.from_contacts(existing))
        if duplicate:
            raise DuplicateCustomerError(duplicate)
        return await self._contacts.create_contact(customer)

    async def import_rows(
        self,
        rows: list[tuple[int, CustomerInput]],
        parse_issues: list[ImportRowIssue] | None = None,
    ) -> CustomerImportResult:
        index = _DuplicateIndex.from_contacts(await self._existing_contacts())
        result = CustomerImportResult(errors=list(parse_issues or []))
        for row_number, raw in rows:
            try:
                customer = normalize_customer_input(raw)
            except CustomerValidationError as error:
                result.errors.append(
                    ImportRowIssue(row_number, raw.display_name or None, str(error))
                )
                continue
            duplicate = _duplicate_reason(customer, index)
            if duplicate:
                result.skipped.append(ImportRowIssue(row_number, customer.display_name, duplicate))
                continue
            result.created.append(await self._contacts.create_contact(customer))
            index.add(customer.display_name, customer.email)
        result.errors.sort(key=lambda issue: issue.row)
        return result


@dataclass
class _DuplicateIndex:
    names: set[str]
    emails: set[str]

    @classmethod
    def from_contacts(cls, contacts: list[ContactRecord]) -> _DuplicateIndex:
        index = cls(names=set(), emails=set())
        for contact in contacts:
            index.add(contact.display_name, contact.email)
        return index

    def add(self, name: str, email: str | None) -> None:
        self.names.add(name.casefold())
        if email:
            self.emails.add(email.lower())


def _duplicate_reason(customer: CustomerInput, index: _DuplicateIndex) -> str | None:
    if customer.email and customer.email in index.emails:
        return f"En kund med e-postadressen {customer.email} finns redan"
    if customer.display_name.casefold() in index.names:
        return f"En kund med namnet {customer.display_name} finns redan"
    return None


def _customer_input_from_values(values: dict[str, str]) -> CustomerInput:
    return CustomerInput(
        display_name=values.get("display_name", ""),
        email=values.get("email"),
        domain=values.get("domain"),
        default_markup_percent=_parse_number(values.get("default_markup_percent"), "Påslag") or 0.0,
        default_incoterms=values.get("default_incoterms"),
        payment_terms=values.get("payment_terms"),
        segment=values.get("segment"),
        customer_since=values.get("customer_since"),
        sla_tolerance_hours=_parse_number(values.get("sla_tolerance_hours"), "SLA-tolerans"),
        account_owner=values.get("account_owner"),
        health_status=values.get("health_status") or "good",
        contract_note=values.get("contract_note"),
        customs_contact_name=values.get("customs_contact_name"),
        customs_contact_email=values.get("customs_contact_email"),
        annual_volume_estimate=_parse_number(values.get("annual_volume_estimate"), "Årlig volym"),
        org_number=values.get("org_number"),
        contact_person=values.get("contact_person"),
        contact_email=values.get("contact_email"),
        contact_phone=values.get("contact_phone"),
        address=values.get("address"),
    )


def _parse_number(value: str | None, label: str) -> float | None:
    if value is None:
        return None
    # Swedish Excel: "1 250 000,50", "12,5 %", "48 h", "100 000 kr".
    cleaned = re.sub(r"[\s %]|kr|sek|h$", "", value.strip().lower())
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    else:
        cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned)
    except ValueError as error:
        raise CustomerValidationError(f"{label} är inte ett tal: {value}") from error


def _map_header(header: list[str]) -> dict[int, str]:
    lookup = {
        _normalize_header(alias): field_name
        for field_name, aliases in _HEADER_ALIASES.items()
        for alias in aliases
    }
    columns: dict[int, str] = {}
    for index, name in enumerate(header):
        field_name = lookup.get(_normalize_header(name))
        if field_name and field_name not in columns.values():
            columns[index] = field_name
    return columns


def _normalize_header(value: str) -> str:
    return re.sub(r"[\s_]+", "_", value.strip().lstrip("\ufeff").lower())


def _decode(content: bytes) -> str:
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return content.decode("cp1252", errors="replace")


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None
