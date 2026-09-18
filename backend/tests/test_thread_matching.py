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

    async def link_quote_to_request(self, request_id, quote_id):
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
            email_id="mail-new",
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
            email_id="mail-new",
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
            email_id="mail-new",
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
            email_id="mail-new",
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
            email_id="mail-new",
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
            email_id="mail-new",
            sender="logistics@volvo.example",
            subject="   ",
            message_id=None,
            in_reply_to=None,
            references=None,
        )
    )

    assert result is None


def test_excludes_the_email_being_processed_from_its_own_candidate_pool() -> None:
    # EmailWebhookUseCase.save() already wrote this exact email to
    # email_inbound before thread_matching ever runs, so it's in its own
    # candidate pool - a "Re: <original subject>" reply normalizes to the
    # same subject as the thread it's replying to, and since candidates are
    # ordered created_at desc, the email would "match itself" first (with
    # empty request_id/quote_id) and mask the real anchor underneath it.
    # Reproduced live 2026-09-16.
    real_anchor = _email(
        "mail-1",
        subject="Quote request Hamburg",
        request_id="req-7",
        created_at=(datetime.now(UTC) - timedelta(minutes=10)).isoformat(),
    )
    self_row = _email(
        "mail-new",
        subject="Re: Quote request Hamburg",
        request_id=None,
        created_at=datetime.now(UTC).isoformat(),
    )
    repository = FakeEmailThreadRepository(domain_candidates=[self_row, real_anchor])
    matcher = ThreadMatchingUseCase(repository)

    result = anyio.run(
        lambda: matcher.match(
            email_id="mail-new",
            sender="logistics@volvo.example",
            subject="Re: Quote request Hamburg",
            message_id=None,
            in_reply_to=None,
            references=None,
        )
    )

    assert result is not None
    assert result.request_id == "req-7"
    assert result.matched_email_id == "mail-1"


def test_excludes_the_email_being_processed_from_tier_1_message_id_candidates() -> None:
    # Same self-matching risk as the subject-based tiers above, but for the
    # In-Reply-To/References message-id lookup - a message can't legitimately
    # be a reply to itself.
    real_anchor = _email("mail-1", message_id="<abc@mail.example>", request_id="req-8")
    self_row = _email("mail-new", message_id="<xyz@mail.example>", request_id=None)
    repository = FakeEmailThreadRepository(message_id_candidates=[self_row, real_anchor])
    matcher = ThreadMatchingUseCase(repository)

    result = anyio.run(
        lambda: matcher.match(
            email_id="mail-new",
            sender="logistics@volvo.example",
            subject="Re: Quote request Hamburg",
            message_id="<xyz@mail.example>",
            in_reply_to="<abc@mail.example> <xyz@mail.example>",
            references=None,
        )
    )

    assert result is not None
    assert result.request_id == "req-8"
    assert result.matched_email_id == "mail-1"


def test_tier_2_ignores_an_unlinked_same_subject_candidate() -> None:
    # A generic one-word subject (here, the Swedish word for "inquiry")
    # from the same sender can trivially coincide across two completely
    # unrelated requests. If the only same-subject candidate never became
    # a real request (request_id/quote_id both None - itself just another
    # unprocessed inquiry, not a tracked conversation), tier 2 must not
    # match to it - doing so previously merged two unrelated shipments'
    # text into one Nora call. Reproduced live 2026-09-17.
    unlinked_unrelated = _email(
        "mail-1",
        subject="Förfråga",
        request_id=None,
        quote_id=None,
        created_at=(datetime.now(UTC) - timedelta(minutes=10)).isoformat(),
    )
    repository = FakeEmailThreadRepository(domain_candidates=[unlinked_unrelated])
    matcher = ThreadMatchingUseCase(repository)

    result = anyio.run(
        lambda: matcher.match(
            email_id="mail-new",
            sender="logistics@volvo.example",
            subject="Förfråga",
            message_id=None,
            in_reply_to=None,
            references=None,
        )
    )

    assert result is None


def test_tier_2_prefers_a_linked_candidate_over_an_unlinked_same_subject_one() -> None:
    unlinked_unrelated = _email(
        "mail-unlinked",
        subject="Förfråga",
        request_id=None,
        quote_id=None,
        created_at=(datetime.now(UTC) - timedelta(minutes=5)).isoformat(),
    )
    linked_real_thread = _email(
        "mail-linked",
        subject="Förfråga",
        request_id="req-9",
        created_at=(datetime.now(UTC) - timedelta(minutes=10)).isoformat(),
    )
    repository = FakeEmailThreadRepository(
        domain_candidates=[unlinked_unrelated, linked_real_thread]
    )
    matcher = ThreadMatchingUseCase(repository)

    result = anyio.run(
        lambda: matcher.match(
            email_id="mail-new",
            sender="logistics@volvo.example",
            subject="Förfråga",
            message_id=None,
            in_reply_to=None,
            references=None,
        )
    )

    assert result is not None
    assert result.request_id == "req-9"
    assert result.matched_email_id == "mail-linked"


def test_tier_3_ignores_an_unlinked_same_subject_candidate() -> None:
    old_unlinked = _email(
        "mail-1",
        subject="Förfråga",
        request_id=None,
        quote_id=None,
        created_at=(datetime.now(UTC) - timedelta(days=400)).isoformat(),
    )
    repository = FakeEmailThreadRepository(domain_candidates=[old_unlinked])
    matcher = ThreadMatchingUseCase(repository)

    result = anyio.run(
        lambda: matcher.match(
            email_id="mail-new",
            sender="logistics@volvo.example",
            subject="Förfråga",
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
            email_id="mail-new",
            sender="nobody@example.com",
            subject="Something new",
            message_id=None,
            in_reply_to=None,
            references=None,
        )
    )

    assert result is None
