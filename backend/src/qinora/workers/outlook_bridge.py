"""QiNora Outlook / Microsoft 365 intake bridge.

The Microsoft Graph counterpart of integrations/gmail-intake-bridge/Code.gs.
Where Code.gs runs *inside* a Google mailbox as an Apps Script, this runs as
a normal QiNora worker (ECS scheduled task in AWS - infra/aws/ecs_workers.tf -
or a looping docker-compose service locally) and talks to the Sandahls
Outlook mailboxes through Microsoft Graph instead.

One pass (``python -m qinora.workers.outlook_bridge``) does exactly what one
Code.gs heartbeat does, against every mailbox listed in OUTLOOK_MAILBOXES:

1. forward_new_mail  - every unread message in the mailbox's Inbox is POSTed
   to QiNora's ``/webhooks/email`` with the HMAC-SHA256 signature the backend
   expects (interfaces/http/security.py), then marked read so it is never
   forwarded twice. The backend's own idempotency-key check
   (``x-idempotency-key`` = the RFC 822 Message-ID) is the real safety net.
2. send_queued_replies - polls ``/outbound/next-queued`` for customer quote
   replies, clarification requests and automatic carrier RFQs, sends each one
   through Graph (as a reply in the original Outlook conversation when the
   item names the inbound Message-ID it answers, otherwise as a new mail),
   and acks/fails each item back so QiNora's queues stay in sync.
3. pings ``/outbound/collect-carrier-rfqs`` so the carrier-RFQ sourcing
   sweep keeps running on the same cadence, exactly like Code.gs did.

Authentication - two supported modes, picked by which env vars are set:

* Application (recommended for production): an Entra ID app registration in
  the Sandahls tenant with *application* permissions Mail.ReadWrite +
  Mail.Send (admin consent), ideally scoped to just these mailboxes with an
  Exchange ApplicationAccessPolicy. Set OUTLOOK_TENANT_ID, OUTLOOK_CLIENT_ID,
  OUTLOOK_CLIENT_SECRET.
* Delegated (no admin needed beyond allowing the app): sign in once as the
  mailbox itself with ``python -m qinora.workers.outlook_bridge login`` (device
  code flow - you type the code into a browser, this process never sees the
  password) and store the printed refresh token as OUTLOOK_REFRESH_TOKEN. In
  this mode the worker only reaches that one mailbox (Graph ``/me``).

Mailbox passwords are never used anywhere here - Exchange Online has had
basic auth (IMAP/SMTP password login) disabled since 2022, so an OAuth app
registration is the only way in regardless. See
integrations/outlook-intake-bridge/README.md for the setup walkthrough.

Only the standard library is used on purpose: the worker image is the
backend image and this must not drag extra dependencies into it.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from email.utils import parseaddr

log = logging.getLogger("qinora.outlook_bridge")

GRAPH = "https://graph.microsoft.com/v1.0"
LOGIN = "https://login.microsoftonline.com"
DELEGATED_SCOPES = (
    "https://graph.microsoft.com/Mail.ReadWrite "
    "https://graph.microsoft.com/Mail.Send offline_access"
)
APP_SCOPE = "https://graph.microsoft.com/.default"
BODY_LIMIT = 20000  # matches Code.gs's getPlainBody().slice(0, 20000)


# --------------------------------------------------------------------------- config


@dataclass
class Settings:
    tenant_id: str
    client_id: str
    client_secret: str | None
    refresh_token: str | None
    mailboxes: list[str]
    send_mailbox: str
    sender_display_name: str
    api_base_url: str
    webhook_secret: str
    max_messages_per_run: int = 20
    timeout: float = 30.0

    @property
    def delegated(self) -> bool:
        return bool(self.refresh_token)

    @classmethod
    def from_env(cls) -> Settings:
        env = os.environ
        mailboxes = [m.strip() for m in env.get("OUTLOOK_MAILBOXES", "").split(",") if m.strip()]
        refresh_token = env.get("OUTLOOK_REFRESH_TOKEN") or None
        client_secret = env.get("OUTLOOK_CLIENT_SECRET") or None
        if not refresh_token and not client_secret:
            raise SystemExit(
                "Set OUTLOOK_CLIENT_SECRET (application auth) or OUTLOOK_REFRESH_TOKEN "
                "(delegated auth, from `python -m qinora.workers.outlook_bridge login`)."
            )
        if not refresh_token and not mailboxes:
            raise SystemExit("OUTLOOK_MAILBOXES is required with application auth.")
        # Delegated tokens can only ever reach the signed-in user's mailbox.
        effective_mailboxes = ["me"] if refresh_token else mailboxes
        return cls(
            tenant_id=_required(env, "OUTLOOK_TENANT_ID"),
            client_id=_required(env, "OUTLOOK_CLIENT_ID"),
            client_secret=client_secret,
            refresh_token=refresh_token,
            mailboxes=effective_mailboxes,
            send_mailbox=env.get("OUTLOOK_SEND_MAILBOX") or effective_mailboxes[0],
            sender_display_name=env.get("OUTLOOK_SENDER_NAME", "Sandahls"),
            api_base_url=_required(env, "QINORA_API_BASE_URL").rstrip("/"),
            webhook_secret=_required(env, "EMAIL_WEBHOOK_SECRET"),
            max_messages_per_run=int(env.get("OUTLOOK_MAX_MESSAGES_PER_RUN", "20")),
        )


def _required(env: os._Environ[str], key: str) -> str:
    value = env.get(key)
    if not value:
        raise SystemExit(f"Missing required environment variable {key}")
    return value


# --------------------------------------------------------------------------- http


class HttpError(RuntimeError):
    def __init__(self, status: int, body: str):
        super().__init__(f"HTTP {status}: {body[:500]}")
        self.status = status
        self.body = body


def _request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    json_body: object | None = None,
    form_body: dict[str, str] | None = None,
    raw_body: bytes | None = None,
    timeout: float = 30.0,
) -> tuple[int, bytes]:
    data: bytes | None = None
    hdrs = dict(headers or {})
    if json_body is not None:
        data = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
        hdrs.setdefault("Content-Type", "application/json")
    elif form_body is not None:
        data = urllib.parse.urlencode(form_body).encode("utf-8")
        hdrs.setdefault("Content-Type", "application/x-www-form-urlencoded")
    elif raw_body is not None:
        data = raw_body
    req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


# --------------------------------------------------------------------------- graph


class GraphClient:
    def __init__(self, settings: Settings):
        self.s = settings
        self._token: str | None = None
        self._token_expires_at = 0.0

    # -- auth

    def token(self) -> str:
        if self._token and time.time() < self._token_expires_at - 60:
            return self._token
        url = f"{LOGIN}/{self.s.tenant_id}/oauth2/v2.0/token"
        if self.s.delegated:
            form = {
                "client_id": self.s.client_id,
                "grant_type": "refresh_token",
                "refresh_token": self.s.refresh_token or "",
                "scope": DELEGATED_SCOPES,
            }
            if self.s.client_secret:
                form["client_secret"] = self.s.client_secret
        else:
            form = {
                "client_id": self.s.client_id,
                "client_secret": self.s.client_secret or "",
                "grant_type": "client_credentials",
                "scope": APP_SCOPE,
            }
        status, body = _request("POST", url, form_body=form, timeout=self.s.timeout)
        if status != 200:
            raise HttpError(status, body.decode("utf-8", "replace"))
        payload = json.loads(body)
        self._token = payload["access_token"]
        self._token_expires_at = time.time() + float(payload.get("expires_in", 3600))
        if payload.get("refresh_token") and payload["refresh_token"] != self.s.refresh_token:
            # Entra rotates refresh tokens; the old one keeps working until it
            # ages out, but log so the stored one can be refreshed occasionally.
            log.info("Graph issued a rotated refresh token (stored one still valid for now).")
        return self._token

    def call(
        self,
        method: str,
        path: str,
        *,
        json_body: object | None = None,
        prefer: str | None = None,
    ) -> dict:
        headers = {"Authorization": f"Bearer {self.token()}", "Accept": "application/json"}
        if prefer:
            headers["Prefer"] = prefer
        url = path if path.startswith("http") else f"{GRAPH}{path}"
        for attempt in range(3):
            status, body = _request(
                method, url, headers=headers, json_body=json_body, timeout=self.s.timeout
            )
            if status == 429 or status >= 500:
                time.sleep(2 * (attempt + 1))
                continue
            if status >= 300:
                raise HttpError(status, body.decode("utf-8", "replace"))
            return json.loads(body) if body.strip() else {}
        raise HttpError(status, body.decode("utf-8", "replace"))

    # -- helpers

    def _mb(self, mailbox: str) -> str:
        return "/me" if mailbox == "me" else f"/users/{urllib.parse.quote(mailbox)}"

    def list_unread(self, mailbox: str, top: int) -> list[dict]:
        query = urllib.parse.urlencode(
            {
                "$filter": "isRead eq false",
                "$orderby": "receivedDateTime asc",
                "$top": str(top),
                "$select": "id,internetMessageId,subject,from,toRecipients,body,receivedDateTime",
            }
        )
        data = self.call(
            "GET",
            f"{self._mb(mailbox)}/mailFolders/inbox/messages?{query}",
            prefer='outlook.body-content-type="text"',
        )
        return data.get("value", [])

    def headers(self, mailbox: str, message_id: str) -> dict[str, str]:
        data = self.call(
            "GET",
            f"{self._mb(mailbox)}/messages/{message_id}?$select=internetMessageHeaders",
        )
        return {h["name"].lower(): h["value"] for h in data.get("internetMessageHeaders", []) or []}

    def mark_read(self, mailbox: str, message_id: str) -> None:
        self.call("PATCH", f"{self._mb(mailbox)}/messages/{message_id}", json_body={"isRead": True})

    def find_by_internet_message_id(self, mailbox: str, internet_message_id: str) -> str | None:
        cleaned = internet_message_id.strip()
        if not cleaned.startswith("<"):
            cleaned = f"<{cleaned}>"
        filt = "internetMessageId eq '" + cleaned.replace("'", "''") + "'"
        query = urllib.parse.urlencode({"$filter": filt, "$select": "id", "$top": "1"})
        data = self.call("GET", f"{self._mb(mailbox)}/messages?{query}")
        hits = data.get("value", [])
        return hits[0]["id"] if hits else None

    def reply(self, mailbox: str, message_id: str, body_text: str) -> None:
        # createReply -> patch the draft to a plain-text body -> send. Using
        # POST /reply with a `comment` would flatten the newlines in the
        # quote/clarification text into one HTML paragraph.
        draft = self.call("POST", f"{self._mb(mailbox)}/messages/{message_id}/createReply")
        draft_id = draft["id"]
        self.call(
            "PATCH",
            f"{self._mb(mailbox)}/messages/{draft_id}",
            json_body={"body": {"contentType": "Text", "content": body_text}},
        )
        self.call("POST", f"{self._mb(mailbox)}/messages/{draft_id}/send")

    def send(self, mailbox: str, recipient: str, subject: str, body_text: str) -> None:
        self.call(
            "POST",
            f"{self._mb(mailbox)}/sendMail",
            json_body={
                "message": {
                    "subject": subject,
                    "body": {"contentType": "Text", "content": body_text},
                    "toRecipients": [{"emailAddress": {"address": recipient}}],
                },
                "saveToSentItems": True,
            },
        )


# --------------------------------------------------------------------------- qinora api


class QinoraClient:
    def __init__(self, settings: Settings):
        self.s = settings

    def _sign(self, body: bytes) -> str:
        digest = hmac.new(self.s.webhook_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        return f"sha256={digest}"

    def _post(self, path: str, body: bytes, extra: dict[str, str] | None = None) -> tuple[int, str]:
        headers = {"Content-Type": "application/json", "x-qinora-signature": self._sign(body)}
        headers.update(extra or {})
        status, resp = _request(
            "POST",
            f"{self.s.api_base_url}{path}",
            headers=headers,
            raw_body=body,
            timeout=self.s.timeout,
        )
        return status, resp.decode("utf-8", "replace")

    def forward_email(self, payload: dict, idempotency_key: str) -> bool:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        status, text = self._post("/webhooks/email", body, {"x-idempotency-key": idempotency_key})
        if 200 <= status < 300:
            return True
        log.warning("QiNora webhook rejected %s: %s %s", idempotency_key, status, text)
        return False

    def next_queued(self) -> list[dict]:
        headers = {"x-qinora-signature": self._sign(b"")}
        status, resp = _request(
            "GET",
            f"{self.s.api_base_url}/outbound/next-queued",
            headers=headers,
            timeout=self.s.timeout,
        )
        if status != 200:
            log.warning("QiNora outbound/next-queued failed: %s %s", status, resp[:300])
            return []
        return json.loads(resp)

    def ack(self, item: dict, action: str, error_message: str | None = None) -> None:
        body = (
            json.dumps({"error_message": error_message}).encode("utf-8")
            if action == "fail"
            else b"{}"
        )
        status, text = self._post(f"/outbound/{item['queue']}/{item['id']}/{action}", body)
        if status >= 300:
            log.warning(
                "QiNora %s rejected for %s item %s: %s %s",
                action,
                item["queue"],
                item["id"],
                status,
                text,
            )

    def collect_carrier_rfqs(self) -> None:
        status, text = self._post("/outbound/collect-carrier-rfqs", b"{}")
        if status != 200:
            log.warning("QiNora collect-carrier-rfqs failed: %s %s", status, text)


# --------------------------------------------------------------------------- passes


@dataclass
class RunStats:
    forwarded: int = 0
    sent: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)


def _address(entry: dict | None) -> tuple[str, str]:
    """(address, display name) out of a Graph emailAddress wrapper."""
    email = (entry or {}).get("emailAddress") or {}
    address = (email.get("address") or "").strip()
    name = (email.get("name") or "").strip()
    if not address and name:
        name, address = parseaddr(name)
    return address, name


def build_webhook_payload(message: dict, headers: dict[str, str], mailbox: str) -> dict:
    sender, sender_name = _address(message.get("from"))
    recipients = message.get("toRecipients") or []
    recipient, _ = _address(recipients[0]) if recipients else ("", "")
    if not recipient:
        recipient = "" if mailbox == "me" else mailbox
    body = (message.get("body") or {}).get("content") or ""
    return {
        "sender": sender,
        "sender_name": sender_name,
        "recipient": recipient,
        "subject": message.get("subject") or "(no subject)",
        "body_text": body[:BODY_LIMIT] or "(empty body)",
        "message_id": message.get("internetMessageId") or headers.get("message-id"),
        "in_reply_to": headers.get("in-reply-to"),
        "references": headers.get("references"),
    }


def forward_new_mail(graph: GraphClient, api: QinoraClient, s: Settings, stats: RunStats) -> None:
    for mailbox in s.mailboxes:
        try:
            messages = graph.list_unread(mailbox, s.max_messages_per_run)
        except HttpError as exc:
            stats.errors.append(f"list_unread({mailbox}): {exc}")
            log.error("Could not list unread mail in %s: %s", mailbox, exc)
            continue
        for message in messages:
            try:
                headers = graph.headers(mailbox, message["id"])
            except HttpError as exc:
                log.warning(
                    "Header fetch failed for %s, continuing without: %s", message["id"], exc
                )
                headers = {}
            payload = build_webhook_payload(message, headers, mailbox)
            if not payload["sender"] or not payload["recipient"]:
                log.warning("Skipping message %s without sender/recipient", message["id"])
                continue
            key = payload["message_id"] or message["id"]
            if api.forward_email(payload, key):
                try:
                    graph.mark_read(mailbox, message["id"])
                except HttpError as exc:
                    log.error("Forwarded %s but could not mark it read: %s", message["id"], exc)
                stats.forwarded += 1


def send_queued_replies(
    graph: GraphClient, api: QinoraClient, s: Settings, stats: RunStats
) -> None:
    for item in api.next_queued():
        try:
            _send_item(graph, s, item)
            api.ack(item, "ack")
            stats.sent += 1
        except Exception as exc:  # noqa: BLE001 - report every failure back to QiNora
            log.error("Failed to send %s item %s: %s", item.get("queue"), item.get("id"), exc)
            api.ack(item, "fail", str(exc))
            stats.failed += 1
    api.collect_carrier_rfqs()


def _send_item(graph: GraphClient, s: Settings, item: dict) -> None:
    in_reply_to = item.get("in_reply_to_message_id")
    if in_reply_to:
        # Reply from whichever mailbox actually holds the original thread.
        for mailbox in s.mailboxes:
            original = graph.find_by_internet_message_id(mailbox, in_reply_to)
            if original:
                graph.reply(mailbox, original, item["body_text"])
                return
        log.info("No original message for %s found, sending as a new mail", in_reply_to)
    graph.send(s.send_mailbox, item["recipient"], item["subject"], item["body_text"])


def run_once() -> RunStats:
    s = Settings.from_env()
    graph = GraphClient(s)
    api = QinoraClient(s)
    stats = RunStats()
    forward_new_mail(graph, api, s, stats)
    send_queued_replies(graph, api, s, stats)
    log.info(
        "Outlook bridge pass done: forwarded=%d sent=%d failed=%d errors=%d",
        stats.forwarded,
        stats.sent,
        stats.failed,
        len(stats.errors),
    )
    return stats


# --------------------------------------------------------------------------- login helper


def device_code_login() -> None:
    """Interactive one-off: obtain a delegated refresh token for one mailbox.

    Run this yourself on your own machine, signed in as the mailbox (e.g.
    test.spedition@sandahls.com) in the browser. Nothing here reads or
    stores the password - Microsoft's login page handles it.
    """
    tenant = os.environ.get("OUTLOOK_TENANT_ID") or "organizations"
    client_id = _required(os.environ, "OUTLOOK_CLIENT_ID")
    status, body = _request(
        "POST",
        f"{LOGIN}/{tenant}/oauth2/v2.0/devicecode",
        form_body={"client_id": client_id, "scope": DELEGATED_SCOPES},
    )
    if status != 200:
        raise SystemExit(f"devicecode failed: {status} {body.decode('utf-8', 'replace')}")
    dc = json.loads(body)
    print(dc["message"])
    interval = int(dc.get("interval", 5))
    deadline = time.time() + int(dc.get("expires_in", 900))
    while time.time() < deadline:
        time.sleep(interval)
        status, body = _request(
            "POST",
            f"{LOGIN}/{tenant}/oauth2/v2.0/token",
            form_body={
                "client_id": client_id,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": dc["device_code"],
            },
        )
        payload = json.loads(body)
        if status == 200:
            print("\nSigned in. Store this as OUTLOOK_REFRESH_TOKEN (Secrets Manager in AWS):\n")
            print(payload["refresh_token"])
            return
        if payload.get("error") in {"authorization_pending", "slow_down"}:
            continue
        raise SystemExit(
            f"login failed: {payload.get('error')}: {payload.get('error_description')}"
        )
    raise SystemExit("Device code expired before sign-in completed - run again.")


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"), format="%(levelname)s %(message)s"
    )
    args = argv if argv is not None else sys.argv[1:]
    if args and args[0] == "login":
        device_code_login()
        return
    run_once()


if __name__ == "__main__":
    main()
