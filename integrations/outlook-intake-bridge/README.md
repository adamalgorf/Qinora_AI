# QiNora Outlook / Microsoft 365 intake bridge

Replaces the Gmail Apps Script (`../gmail-intake-bridge/Code.gs`) now that the
QiNora mailboxes live in Sandahls' Microsoft 365 tenant:

| Mailbox | Role |
| --- | --- |
| `test.spedition@sandahls.com` | Speditör / forwarder inbox - customers and carriers write here; quotes, clarifications and carrier RFQs go out from here |
| `qinora.ai@sandahls.com` | Second forwarder inbox, watched the same way |
| *(driver mailbox - not yet provided)* | Add to `OUTLOOK_MAILBOXES` when it exists |

The bridge is `backend/src/qinora/workers/outlook_bridge.py`. It is a normal
QiNora worker (no extra dependencies - standard library only) that runs one
pass per invocation, exactly like the other `qinora.workers.*` entrypoints:

1. **Inbound** - unread Inbox mail in every watched mailbox is POSTed to
   `POST /webhooks/email` with the same HMAC-SHA256 signature and
   `x-idempotency-key` (the RFC 822 Message-ID) Code.gs used, then marked
   read.
2. **Outbound** - `GET /outbound/next-queued` is polled; each item is sent
   through Microsoft Graph, threaded as a reply in the original Outlook
   conversation when `in_reply_to_message_id` is set, and acked/failed back.
3. `POST /outbound/collect-carrier-rfqs` is pinged on every pass.

Nothing in the backend changed - the HTTP contract in
`interfaces/http/routers/outbound.py` and `webhooks.py` is untouched, so the
Gmail script keeps working for `farah@qinora.org` if it is ever needed again.

## Why not just the mailbox passwords?

Microsoft disabled basic authentication (IMAP/POP/SMTP with a password) for
Exchange Online in 2022. The only way for software to read or send mail on a
Microsoft 365 mailbox is OAuth through an **Entra ID app registration**, so
the passwords for the two accounts are not used (and must not be put in any
config or repo). Pick one of the two auth modes below.

## Option A - application auth (recommended for production)

Needs a Sandahls Microsoft 365 admin (their IT) once:

1. Entra admin center → **App registrations** → *New registration*:
   name `QiNora mail bridge`, single tenant, no redirect URI.
   Note the **Application (client) ID** and **Directory (tenant) ID**.
2. **API permissions** → *Add* → Microsoft Graph → **Application permissions**
   → `Mail.ReadWrite` and `Mail.Send` → *Grant admin consent*.
3. **Certificates & secrets** → *New client secret* (12–24 months) → copy the
   value.
4. Strongly recommended - limit the app to just the QiNora mailboxes
   (otherwise application permissions cover *every* mailbox in the tenant).
   In Exchange Online PowerShell:

   ```powershell
   New-DistributionGroup -Name "QiNora mailboxes" -Type Security -Members test.spedition@sandahls.com,qinora.ai@sandahls.com
   New-ApplicationAccessPolicy -AppId <client id> -PolicyScopeGroupId "QiNora mailboxes" -AccessRight RestrictAccess -Description "QiNora bridge"
   Test-ApplicationAccessPolicy -Identity test.spedition@sandahls.com -AppId <client id>
   ```

Then configure `OUTLOOK_TENANT_ID`, `OUTLOOK_CLIENT_ID`,
`OUTLOOK_CLIENT_SECRET`, `OUTLOOK_MAILBOXES`, `OUTLOOK_SEND_MAILBOX`.

## Option B - delegated auth (no admin consent for mail permissions)

Works when Sandahls allows users to consent to apps themselves (default
tenant setting is often "no", in which case you still need IT for the app
registration - but not for Exchange policies).

1. App registration as above, but tick *Allow public client flows* under
   **Authentication**, and add **Delegated** permissions `Mail.ReadWrite`,
   `Mail.Send`, `offline_access`.
2. On your own machine, with the backend venv active:

   ```bash
   OUTLOOK_TENANT_ID=<tenant> OUTLOOK_CLIENT_ID=<client id> \
     python -m qinora.workers.outlook_bridge login
   ```

   It prints a code and a URL - open the URL in a browser, **sign in as the
   mailbox** (e.g. `test.spedition@sandahls.com`), enter the code. The
   process never sees the password. It then prints a refresh token.
3. Store it as `OUTLOOK_REFRESH_TOKEN`. In this mode the worker reaches only
   that one mailbox (Graph `/me`), so run one worker per mailbox if both must
   be watched.

Refresh tokens stay valid as long as they are used at least every 90 days;
the worker runs every minute so that is never an issue in practice.

## Deploying

* **AWS** - `infra/aws` already knows about the bridge. Pass the credentials
  as Terraform variables (`TF_VAR_outlook_client_secret=...` or
  `TF_VAR_outlook_refresh_token=...`, plus `-var outlook_tenant_id=...
  -var outlook_client_id=...`). When either credential is non-empty an
  extra ECS scheduled task `qinora-outlook-bridge` (rate: 1 minute) is
  created alongside the other three workers; it reads the backend URL from
  the App Runner service, so no manual wiring. Logs land in
  `/ecs/qinora-workers` with stream prefix `outlook_bridge`.
* **Local** - fill in the `OUTLOOK_*` block in `.env`, then
  `docker compose --profile outlook up`.
* **One-off run** - `QINORA_API_BASE_URL=... EMAIL_WEBHOOK_SECRET=... OUTLOOK_...=... python -m qinora.workers.outlook_bridge`.

## Smoke test

1. Send a mail from any address to `test.spedition@sandahls.com`.
2. Within a minute it should show up on the QiNora Inbox page and be marked
   read in Outlook.
3. Send a quote from QiNora - it should appear in the mailbox's *Sent Items*,
   nested under the customer's original conversation.

## Environment reference

| Variable | Required | Notes |
| --- | --- | --- |
| `OUTLOOK_TENANT_ID` | yes | tenant GUID or `sandahls.com` |
| `OUTLOOK_CLIENT_ID` | yes | app registration client ID |
| `OUTLOOK_CLIENT_SECRET` | A | application auth |
| `OUTLOOK_REFRESH_TOKEN` | B | delegated auth (overrides A if both set) |
| `OUTLOOK_MAILBOXES` | A | comma-separated; ignored in mode B (`/me`) |
| `OUTLOOK_SEND_MAILBOX` | no | defaults to the first mailbox |
| `OUTLOOK_SENDER_NAME` | no | display name, default `Sandahls` |
| `OUTLOOK_MAX_MESSAGES_PER_RUN` | no | default 20 |
| `QINORA_API_BASE_URL` | yes | backend base URL, no trailing slash |
| `EMAIL_WEBHOOK_SECRET` | yes | same value the backend has |
