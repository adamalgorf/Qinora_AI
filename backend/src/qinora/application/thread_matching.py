"""Resolves an inbound email to a prior request/quote thread using a
3-tier match, so a follow-up email can be recognised as "the same
conversation" rather than always starting a brand-new request.

Tiers, in order:
  1. In-Reply-To / References headers against a known email_inbound.message_id
     (our own prior inbound history).
  2. Same normalized subject (Re:/Fwd:/SV:/VB: prefixes stripped,
     case-insensitive) + same sender, within 30 days.
  3. Fallback: same normalized subject + same sender, most recent, no day
     cutoff.

Public webmail domains (gmail.com, outlook.com, ...) require an exact
sender-address match at tiers 2/3, since many different people can share
one company-looking subject line at those providers; other domains match
on domain alone. An empty/blank subject never matches at tiers 2/3.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from qinora.application.ports import EmailThreadRepository
from qinora.application.read_models import InboundEmailRecord

PUBLIC_WEBMAIL_DOMAINS = frozenset(
    {
        "gmail.com",
        "outlook.com",
        "hotmail.com",
        "live.com",
        "yahoo.com",
        "icloud.com",
        "protonmail.com",
    }
)

_SUBJECT_PREFIX_RE = re.compile(r"^(re|fwd|sv|vb)\s*:\s*", re.IGNORECASE)
_TIER_2_WINDOW = timedelta(days=30)


@dataclass(frozen=True)
class ThreadMatchResult:
    request_id: str | None
    quote_id: str | None
    matched_email_id: str
    tier: int


def normalize_subject(subject: str) -> str:
    normalized = subject.strip()
    while True:
        stripped = _SUBJECT_PREFIX_RE.sub("", normalized).strip()
        if stripped == normalized:
            break
        normalized = stripped
    return normalized.casefold()


def _domain_of(address: str) -> str:
    normalized = address.strip().lower()
    return normalized.rsplit("@", 1)[1] if "@" in normalized else normalized


def _extract_message_ids(in_reply_to: str | None, references: str | None) -> tuple[str, ...]:
    raw = " ".join(part for part in (in_reply_to, references) if part)
    return tuple({token.strip() for token in raw.split() if token.strip()})


def _parse_created_at(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace(" ", "T"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


class ThreadMatchingUseCase:
    def __init__(self, repository: EmailThreadRepository) -> None:
        self._repository = repository

    async def match(
        self,
        *,
        sender: str,
        subject: str,
        message_id: str | None,
        in_reply_to: str | None,
        references: str | None,
    ) -> ThreadMatchResult | None:
        candidate_ids = _extract_message_ids(in_reply_to, references)
        if candidate_ids:
            rows = await self._repository.find_candidates_by_message_ids(candidate_ids)
            row = _first_linked(rows) or (rows[0] if rows else None)
            if row is not None:
                return ThreadMatchResult(row.request_id, row.quote_id, row.id, 1)

        normalized_subject = normalize_subject(subject)
        if not normalized_subject:
            return None

        domain = _domain_of(sender)
        if domain in PUBLIC_WEBMAIL_DOMAINS:
            candidates = await self._repository.find_candidates_by_sender(sender)
        else:
            candidates = await self._repository.find_candidates_by_domain(domain)

        subject_matches = [
            row for row in candidates if normalize_subject(row.subject) == normalized_subject
        ]
        if not subject_matches:
            return None

        cutoff = datetime.now(UTC) - _TIER_2_WINDOW
        for row in subject_matches:
            created_at = _parse_created_at(row.created_at)
            if created_at is not None and created_at >= cutoff:
                return ThreadMatchResult(row.request_id, row.quote_id, row.id, 2)

        # Tier 3 fallback: most recent subject match regardless of age.
        # `candidates` is already ordered created_at desc by the repository,
        # so the first subject match here is the most recent one.
        row = subject_matches[0]
        return ThreadMatchResult(row.request_id, row.quote_id, row.id, 3)


def _first_linked(rows: list[InboundEmailRecord]) -> InboundEmailRecord | None:
    """Among rows matched by message-id, prefer one that already carries a
    request/quote link (the anchor message of a real thread) over a bare
    reply-to-a-reply that hasn't been linked yet.
    """
    for row in rows:
        if row.request_id or row.quote_id:
            return row
    return None
