from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import anyio

from qinora.application.read_models import InboundEmailRecord
from qinora.application.thread_matching import ThreadMatchingUseCase, normalize_subject


def _email(
    id: str,
    *,
    sender: str = "logistics@volvo.example",
    subject: str = "Quote request Hamburg",
    message_id: str | None = None,
    request_id: str | None = None,
    quote_id: str | None = None,
    created_at: str | None = None,
) -> InboundEmailRecord:
    return InboundEmailRecord(
        id=id,
        sender=sender,
        recipient="farah@qinora.org",
        subject=subject,
        body_text="body",
        classification="transport_request",
        message_id=message_id,
        in_reply_to=None,
        references_header=None,
        request_id=request_id,
        quote_id=quote_id,
        created_at=created_at or datetime.now(UTC).isoformat(),
    )


@dataclass
class FakeEmailThreadRepository:
    message_id_candidates: list[InboundEmailRecord] = field(default_factory=list)
    sender_candidates: list[InboundEmailRecord] = field(default_factory=list)
    domain_candidates: list[InboundEmailRecord] = field(default_factory=list)

    async def get(self, email_id: str) -> InboundEmailRecord | None:
        raise NotImplementedError

    async def find_candidates_by_message_ids(
        self, message_ids: tuple[str, ...]
    ) -> list[InboundEmailRecord]:
        return [row for row in self.message_id_candidates if row.message_id in message_ids]

    async def find_candidates_by_sender(
        self, sender: str, limit: int = 200
    ) -> list[InboundEmailRecord]:
        return [row for row in self.sender_candidates if row.sender.lower() == sender.lower()]

    async def find_candidates_by_domain(
        self, domain: str, limit: int = 200
    ) -> list[InboundEmailRecord]:
        return [
            row
            for row in self.domain_candidates
            if row.sender.lower().endswith(f"@{domain.lower()}")
        ]

    async def list_thread_history(self, *, request_id, quote_id):
        raise NotImplementedError

    async def link_thread(self, email_id, *, request_id, quote_id):
        raise NotImplementedError

    async def mark_classification(self, email_id, classification):
        raise NotImplementedError


def test_normalize_subject_strips_reply_and_forward_prefixes() -> None:
    assert normalize_subject("Re: Fwd: SV: Quote request") == "quote request"
    assert normalize_subject("  Quote request  ") == "quote request"


def test_tier_1_matches_on_in_reply_to_message_id() -> None:
    anchor = _email("mail-1", message_id="<abc@mail.example>", request_id="req-1")
    repository = FakeEmailThreadRepository(message_id_candidates=[anchor])
    matcher = ThreadMatchingUseCase(repository)

    result = anyio.run(
        lambda: matcher.match(
            sender="logistics@volvo.example",
            subject="Re: Quote request Hamburg",
            message_id="<xyz@mail.example>",
            in_reply_to="<abc@mail.example>",
            references=None,
        )
    )

    assert result is not None
    assert result.tier == 1
    assert result.request_id == "req-1"
    assert result.matched_email_id == "mail-1"


def test_tier_2_matches_normalized_subject_and_sender_within_30_days() -> None:
    recent = (datetime.now(UTC) - timedelta(days=5)).isoformat()
    anchor = _email(
        "mail-1",
        subject="Quote request Hamburg",
        request_id="req-2",
        created_at=recent,
    )
    # volvo.example is not a public webmail domain, so the matcher looks up
    # candidates by domain rather than exact sender address.
    repository = FakeEmailThreadRepository(domain_candidates=[anchor])
    matcher = ThreadMatchingUseCase(repository)

    result = anyio.run(
        lambda: matcher.match(
            sender="logistics@volvo.example",
            subject="Re: Quote request Hamburg",
            message_id=None,
            in_reply_to=None,
            references=None,
        )
    )

    assert result is not None
    assert result.tier == 2
    assert result.request_id == "req-2"


def test_tier_3_falls_back_beyond_30_day_window() -> None:
    old = (datetime.now(UTC) - timedelta(days=400)).isoformat()
    anchor = _email(
        "mail-1",
        subject="Quote request Hamburg",
        request_id="req-3",
        created_at=old,
    )
    repository = FakeEmailThreadRepository(domain_candidates=[anchor])
    matcher = ThreadMatchingUseCase(repository)

    result = anyio.run(
        lambda: matcher.match(
            sender="logistics@volvo.example",
            subject="Fwd: Quote request Hamburg",
            message_id=None,
            in_reply_to=None,
            references=None,
        )
    )

    assert result is not None
    assert result.tier == 3
    assert result.request_id == "req-3"


def test_public_webmail_domain_requires_exact_sender_match() -> None:
    # A different person at gmail.com must not match just because the
    # domain matches - only find_candidates_by_sender (exact address) is
    # consulted for public webmail domains, never find_candidates_by_domain.
    other_sender = _email(
        "mail-1",
        sender="someone-else@gmail.com",
        subject="Quote request Hamburg",
        request_id="req-4",
    )
    repository = FakeEmailThreadRepository(domain_candidates=[other_sender])
    matcher = ThreadMatchingUseCase(repository)

    result = anyio.run(
        lambda: matcher.match(
            sender="me@gmail.com",
            subject="Re: Quote request Hamburg",
            message_id=None,
            in_reply_to=None,
            references=None,
        )
    )

    assert result is None


def test_non_webmail_domain_matches_on_domain() -> None:
    colleague = _email(
        "mail-1",
        sender="colleague@volvo.example",
        subject="Quote request Hamburg",
        request_id="req-5",
    )
    repository = FakeEmailThreadRepository(domain_candidates=[colleague])
    matcher = ThreadMatchingUseCase(repository)

    result = anyio.run(
        lambda: matcher.match(
            sender="logistics@volvo.example",
            subject="Re: Quote request Hamburg",
            message_id=None,
            in_reply_to=None,
            references=None,
        )
    )

    assert result is not None
    assert result.request_id == "req-5"


def test_blank_subject_never_matches() -> None:
    anchor = _email("mail-1", subject="   ", request_id="req-6")
    repository = FakeEmailThreadRepository(sender_candidates=[anchor])
    matcher = ThreadMatchingUseCase(repository)

    result = anyio.run(
        lambda: matcher.match(
            sender="logistics@volvo.example",
            subject="   ",
            message_id=None,
            in_reply_to=None,
            references=None,
        )
    )

    assert result is None


def test_no_candidates_returns_none() -> None:
    repository = FakeEmailThreadRepository()
    matcher = ThreadMatchingUseCase(repository)

    result = anyio.run(
        lambda: matcher.match(
            sender="nobody@example.com",
            subject="Something new",
            message_id=None,
            in_reply_to=None,
            references=None,
        )
    )

    assert result is None
