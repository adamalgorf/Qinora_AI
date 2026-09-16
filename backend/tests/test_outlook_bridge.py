"""Unit tests for the Outlook/Graph intake bridge worker.

All HTTP is stubbed at the single `_request` seam, so these check the
Graph call shapes, the webhook payload mapping and the HMAC signing without
network - the signing is asserted against the backend's own
verify_hmac_signature so the two sides can't drift apart.
"""

from __future__ import annotations

import json

import pytest

from qinora.interfaces.http.security import verify_hmac_signature
from qinora.workers import outlook_bridge as ob


@pytest.fixture
def settings() -> ob.Settings:
    return ob.Settings(
        tenant_id="tenant",
        client_id="client",
        client_secret="secret",
        refresh_token=None,
        mailboxes=["test.spedition@sandahls.com", "qinora.ai@sandahls.com"],
        send_mailbox="test.spedition@sandahls.com",
        sender_display_name="Sandahls",
        api_base_url="https://api.example.test",
        webhook_secret="hook-secret",
    )


class FakeHttp:
    """Records every request and answers from a routing table."""

    def __init__(self):
        self.calls: list[dict] = []
        self.routes: list[tuple[str, str, int, object]] = []

    def route(self, method: str, url_fragment: str, status: int, body: object) -> None:
        self.routes.append((method, url_fragment, status, body))

    def __call__(
        self,
        method,
        url,
        *,
        headers=None,
        json_body=None,
        form_body=None,
        raw_body=None,
        timeout=30.0,
    ):
        self.calls.append(
            {
                "method": method,
                "url": url,
                "headers": headers or {},
                "json": json_body,
                "form": form_body,
                "raw": raw_body,
            }
        )
        for m, frag, status, body in self.routes:
            if m == method and frag in url:
                payload = body if isinstance(body, bytes) else json.dumps(body).encode()
                return status, payload
        raise AssertionError(f"unexpected request {method} {url}")


@pytest.fixture
def http(monkeypatch) -> FakeHttp:
    fake = FakeHttp()
    monkeypatch.setattr(ob, "_request", fake)
    fake.route("POST", "/oauth2/v2.0/token", 200, {"access_token": "tok", "expires_in": 3600})
    return fake


def test_webhook_payload_maps_graph_message_like_code_gs():
    message = {
        "id": "AAMk1",
        "internetMessageId": "<abc@mail.example>",
        "subject": "RFQ Stockholm -> Hamburg",
        "from": {"emailAddress": {"address": "kund@example.com", "name": "Anna Andersson"}},
        "toRecipients": [{"emailAddress": {"address": "test.spedition@sandahls.com"}}],
        "body": {"contentType": "text", "content": "Hej, 500 kg LTL"},
    }
    headers = {"in-reply-to": "<prev@mail.example>", "references": "<prev@mail.example>"}
    payload = ob.build_webhook_payload(message, headers, "test.spedition@sandahls.com")
    assert payload == {
        "sender": "kund@example.com",
        "sender_name": "Anna Andersson",
        "recipient": "test.spedition@sandahls.com",
        "subject": "RFQ Stockholm -> Hamburg",
        "body_text": "Hej, 500 kg LTL",
        "message_id": "<abc@mail.example>",
        "in_reply_to": "<prev@mail.example>",
        "references": "<prev@mail.example>",
    }


def test_forward_new_mail_posts_signed_payload_and_marks_read(settings, http):
    message = {
        "id": "AAMk1",
        "internetMessageId": "<abc@mail.example>",
        "subject": "Offert",
        "from": {"emailAddress": {"address": "kund@example.com", "name": "Anna"}},
        "toRecipients": [{"emailAddress": {"address": "test.spedition@sandahls.com"}}],
        "body": {"content": "Pris på 500 kg, tack. Hälsningar Åsa"},
    }
    http.route(
        "GET",
        "users/test.spedition%40sandahls.com/mailFolders/inbox/messages",
        200,
        {"value": [message]},
    )
    http.route(
        "GET", "users/qinora.ai%40sandahls.com/mailFolders/inbox/messages", 200, {"value": []}
    )
    http.route(
        "GET",
        "/messages/AAMk1?$select=internetMessageHeaders",
        200,
        {"internetMessageHeaders": [{"name": "In-Reply-To", "value": "<x@y>"}]},
    )
    http.route("POST", "/webhooks/email", 200, {"accepted": True, "duplicate": False})
    http.route("PATCH", "/messages/AAMk1", 200, {})

    stats = ob.RunStats()
    ob.forward_new_mail(ob.GraphClient(settings), ob.QinoraClient(settings), settings, stats)

    assert stats.forwarded == 1
    webhook = next(c for c in http.calls if "/webhooks/email" in c["url"])
    body = webhook["raw"]
    assert verify_hmac_signature("hook-secret", body, webhook["headers"]["x-qinora-signature"])
    assert webhook["headers"]["x-idempotency-key"] == "<abc@mail.example>"
    assert json.loads(body)["in_reply_to"] == "<x@y>"
    assert json.loads(body)["sender_name"] == "Anna"
    mark = next(c for c in http.calls if c["method"] == "PATCH")
    assert mark["json"] == {"isRead": True}
    # Plain-text body requested from Graph, like getPlainBody() in Code.gs.
    listing = next(c for c in http.calls if "mailFolders/inbox" in c["url"])
    assert 'outlook.body-content-type="text"' in listing["headers"]["Prefer"]


def test_rejected_webhook_leaves_message_unread(settings, http):
    message = {
        "id": "AAMk2",
        "internetMessageId": "<m2@x>",
        "subject": "s",
        "from": {"emailAddress": {"address": "a@b.c"}},
        "toRecipients": [{"emailAddress": {"address": "test.spedition@sandahls.com"}}],
        "body": {"content": "x"},
    }
    http.route("GET", "mailFolders/inbox/messages", 200, {"value": [message]})
    http.route("GET", "$select=internetMessageHeaders", 200, {})
    http.route("POST", "/webhooks/email", 401, {"detail": "Invalid signature"})
    stats = ob.RunStats()
    ob.forward_new_mail(ob.GraphClient(settings), ob.QinoraClient(settings), settings, stats)
    assert stats.forwarded == 0
    assert not any(c["method"] == "PATCH" for c in http.calls)


def test_send_queued_replies_threads_when_original_found(settings, http):
    items = [
        {
            "queue": "quote",
            "id": "q1",
            "recipient": "kund@example.com",
            "subject": "Re: Offert",
            "body_text": "Pris: 1100 SEK\nGäller 7 dagar.",
            "in_reply_to_message_id": "<abc@mail.example>",
        },
        {
            "queue": "carrier_rfq",
            "id": "c1",
            "recipient": "akeri@example.com",
            "subject": "QiNora RFQ",
            "body_text": "Hej",
            "in_reply_to_message_id": None,
        },
    ]
    http.route("GET", "/outbound/next-queued", 200, items)
    http.route(
        "GET", "users/test.spedition%40sandahls.com/messages?", 200, {"value": [{"id": "ORIG"}]}
    )
    http.route("POST", "/messages/ORIG/createReply", 201, {"id": "DRAFT"})
    http.route("PATCH", "/messages/DRAFT", 200, {})
    http.route("POST", "/messages/DRAFT/send", 202, b"")
    http.route("POST", "/sendMail", 202, b"")
    http.route("POST", "/outbound/quote/q1/ack", 200, {})
    http.route("POST", "/outbound/carrier_rfq/c1/ack", 200, {})
    http.route("POST", "/outbound/collect-carrier-rfqs", 200, {})

    stats = ob.RunStats()
    ob.send_queued_replies(ob.GraphClient(settings), ob.QinoraClient(settings), settings, stats)

    assert (stats.sent, stats.failed) == (2, 0)
    patch = next(c for c in http.calls if c["method"] == "PATCH")
    assert patch["json"]["body"] == {
        "contentType": "Text",
        "content": "Pris: 1100 SEK\nGäller 7 dagar.",
    }
    send = next(c for c in http.calls if "/sendMail" in c["url"])
    assert send["url"].startswith(
        "https://graph.microsoft.com/v1.0/users/test.spedition%40sandahls.com/"
    )
    assert (
        send["json"]["message"]["toRecipients"][0]["emailAddress"]["address"] == "akeri@example.com"
    )
    next_queued = next(c for c in http.calls if "/next-queued" in c["url"])
    assert verify_hmac_signature("hook-secret", b"", next_queued["headers"]["x-qinora-signature"])
    assert any("/collect-carrier-rfqs" in c["url"] for c in http.calls)


def test_send_failure_is_reported_back(settings, http):
    http.route(
        "GET",
        "/outbound/next-queued",
        200,
        [
            {
                "queue": "quote",
                "id": "q9",
                "recipient": "k@x.y",
                "subject": "s",
                "body_text": "b",
                "in_reply_to_message_id": None,
            }
        ],
    )
    http.route("POST", "/sendMail", 403, {"error": {"message": "ErrorAccessDenied"}})
    http.route("POST", "/outbound/quote/q9/fail", 200, {})
    http.route("POST", "/outbound/collect-carrier-rfqs", 200, {})
    stats = ob.RunStats()
    ob.send_queued_replies(ob.GraphClient(settings), ob.QinoraClient(settings), settings, stats)
    assert (stats.sent, stats.failed) == (0, 1)
    fail = next(c for c in http.calls if c["url"].endswith("/fail"))
    assert "ErrorAccessDenied" in json.loads(fail["raw"])["error_message"]


def test_mailbox_matches_true_when_sender_mailbox_unset(settings):
    # Legacy rows and single-mailbox deployments have no sender_mailbox at
    # all - fair game for any bridge instance to pick up.
    assert ob._mailbox_matches({"sender_mailbox": None}, settings) is True
    assert ob._mailbox_matches({}, settings) is True


def test_mailbox_matches_is_case_and_whitespace_insensitive(settings):
    assert ob._mailbox_matches({"sender_mailbox": " Test.Spedition@Sandahls.com "}, settings)


def test_mailbox_matches_false_for_a_different_bridge_instances_mail(settings):
    # settings.send_mailbox is test.spedition@sandahls.com - an item routed
    # to qinora.ai@sandahls.com belongs to the OTHER bridge instance and
    # must be left alone, not raced for / double-sent.
    assert not ob._mailbox_matches({"sender_mailbox": "qinora.ai@sandahls.com"}, settings)


def test_send_queued_replies_skips_items_for_another_mailbox(settings, http):
    # Reproduced live 2026-09-16: two bridge instances (one per mailbox)
    # both polling the same /outbound/next-queued raced each other and
    # marked the other instance's item "sent" without actually delivering
    # it. This locks in that a mismatched item is skipped entirely - never
    # sent and never ack'd - so the owning instance still gets to send it.
    items = [
        {
            "queue": "carrier_offer_report",
            "id": "r1",
            "recipient": "test.spedition@sandahls.com",
            "subject": "QiNora Offert",
            "body_text": "Billigaste svaret ...",
            "in_reply_to_message_id": None,
            "sender_mailbox": "qinora.ai@sandahls.com",
        },
        {
            "queue": "quote",
            "id": "q1",
            "recipient": "kund@example.com",
            "subject": "Din offert",
            "body_text": "Pris: 1100 SEK",
            "in_reply_to_message_id": None,
            "sender_mailbox": "test.spedition@sandahls.com",
        },
    ]
    http.route("GET", "/outbound/next-queued", 200, items)
    http.route("POST", "/sendMail", 202, b"")
    http.route("POST", "/outbound/quote/q1/ack", 200, {})
    http.route("POST", "/outbound/collect-carrier-rfqs", 200, {})

    stats = ob.RunStats()
    ob.send_queued_replies(ob.GraphClient(settings), ob.QinoraClient(settings), settings, stats)

    assert (stats.sent, stats.failed) == (1, 0)
    send_calls = [c for c in http.calls if "/sendMail" in c["url"]]
    assert len(send_calls) == 1
    assert send_calls[0]["json"]["message"]["toRecipients"][0]["emailAddress"]["address"] == (
        "kund@example.com"
    )
    assert not any(c["url"].endswith("/r1/ack") for c in http.calls)
    assert not any(c["url"].endswith("/r1/fail") for c in http.calls)


def test_repair_mojibake_reverses_latin1_as_utf8_misdecoding():
    original = "Förfrågan från Åsa"
    # Build the exact mangling Graph produces: the original UTF-8 bytes
    # mis-decoded as Latin-1 (see _repair_mojibake's docstring) - spelled
    # out programmatically rather than as a literal, since the mangled form
    # is itself fragile to how this file/editor round-trips non-ASCII text.
    mangled = original.encode("utf-8").decode("latin1")
    assert ob._repair_mojibake(mangled) == original


def test_repair_mojibake_is_a_safe_no_op_on_already_correct_text():
    # "ö" (U+00F6) encodes to a single Latin-1 byte (0xF6), which is not
    # valid UTF-8 on its own - the round trip must raise internally and
    # return the original text unchanged rather than corrupting it further.
    correct = "Förfrågan från Åsa"
    assert ob._repair_mojibake(correct) == correct


def test_repair_mojibake_handles_empty_string():
    assert ob._repair_mojibake("") == ""


def test_delegated_mode_uses_me_and_refresh_grant(monkeypatch, http):
    monkeypatch.setenv("OUTLOOK_TENANT_ID", "t")
    monkeypatch.setenv("OUTLOOK_CLIENT_ID", "c")
    monkeypatch.setenv("OUTLOOK_REFRESH_TOKEN", "rt")
    monkeypatch.delenv("OUTLOOK_CLIENT_SECRET", raising=False)
    monkeypatch.setenv("QINORA_API_BASE_URL", "https://api.example.test/")
    monkeypatch.setenv("EMAIL_WEBHOOK_SECRET", "s")
    s = ob.Settings.from_env()
    assert s.delegated and s.mailboxes == ["me"] and s.send_mailbox == "me"
    assert s.api_base_url == "https://api.example.test"
    http.route("GET", "/me/mailFolders/inbox/messages", 200, {"value": []})
    ob.GraphClient(s).list_unread("me", 5)
    token_call = next(c for c in http.calls if "/oauth2/v2.0/token" in c["url"])
    assert token_call["form"]["grant_type"] == "refresh_token"
