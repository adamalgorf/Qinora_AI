/**
 * QiNora Gmail intake bridge.
 *
 * Runs INSIDE the Google Workspace mailbox that receives customer/carrier
 * emails (e.g. farah@qinora.org). On a time-driven trigger it finds unread
 * mail that hasn't been forwarded yet, POSTs each one to QiNora's
 * `/webhooks/email` endpoint with an HMAC-SHA256 signature, and labels the
 * message so it's never sent twice (forwardNewMail). A second time-driven
 * trigger runs the mirror image (sendQueuedReplies): it polls QiNora's
 * `/outbound/next-queued` endpoint for quote replies AND automatic carrier
 * RFQ emails, actually sends each one with GmailApp.sendEmail(...) (QiNora's
 * backend has no Gmail credentials of its own), and reports back
 * sent/failed per item so QiNora's outbound queues stay in sync. It also
 * pings QiNora's `/outbound/collect-carrier-rfqs` endpoint on the same
 * cadence, so the carrier-RFQ sourcing sweep (application/carrier_rfq_collector.py)
 * runs on the same 5-minute heartbeat without a separate scheduler.
 *
 * QiNora never receives this mailbox's password - this script authenticates
 * to Gmail using the Apps Script project's own Google session (the person
 * who opens script.google.com and authorizes it), and authenticates to
 * QiNora using a shared webhook secret stored in Script Properties, not in
 * this source.
 *
 * SETUP (do this once, logged in as the mailbox this should watch):
 *   1. Go to https://script.google.com -> New project. Replace the default
 *      Code.gs contents with this file.
 *   2. Project Settings (gear icon) -> Script Properties -> add:
 *        QINORA_WEBHOOK_SECRET = <the EMAIL_WEBHOOK_SECRET value from the
 *          qinora-backend service's Environment tab on Render>
 *        QINORA_WEBHOOK_URL    = https://qinora-backend.onrender.com/webhooks/email
 *          (optional - this is also the default if you skip it)
 *        QINORA_OUTBOUND_BASE_URL = https://qinora-backend.onrender.com/outbound
 *          (optional - this is also the default if you skip it; used for
 *          next-queued/ack/fail/collect-carrier-rfqs, all under this prefix)
 *   3. Run the `installTrigger` function once from the editor (Run menu).
 *      Approve the Gmail permissions Google asks for - this now includes
 *      SEND, not just read/label, because sendQueuedReplies() actually
 *      sends mail on this mailbox's behalf (GmailApp.sendEmail). If this
 *      script was authorized before this feature existed, re-run
 *      `installTrigger` once and re-approve when prompted. This installs
 *      two time-driven triggers - forwardNewMail and sendQueuedReplies -
 *      each running every 5 minutes from then on; you don't need to run
 *      anything by hand again.
 *   4. Send a test email to this mailbox and check the QiNora Inbox page;
 *      it should appear within 5 minutes labelled "QiNora/Forwarded". Send
 *      a customer/carrier a quote or RFQ from QiNora and confirm it lands
 *      in this mailbox's Sent folder within 5 minutes too.
 *
 * Everything this script touches lives inside your own Google account and
 * Apps Script project - QiNora only ever sees the forwarded email content
 * and the outbound rows it queued itself.
 */

var LABEL_NAME = "QiNora/Forwarded";
var GMAIL_SEARCH_QUERY = "is:unread in:inbox -label:" + LABEL_NAME;
var MAX_MESSAGES_PER_RUN = 20;

function installTrigger() {
  ScriptApp.getProjectTriggers().forEach(function (trigger) {
    var handler = trigger.getHandlerFunction();
    if (handler === "forwardNewMail" || handler === "sendQueuedReplies") {
      ScriptApp.deleteTrigger(trigger);
    }
  });
  ScriptApp.newTrigger("forwardNewMail").timeBased().everyMinutes(1).create();
  ScriptApp.newTrigger("sendQueuedReplies").timeBased().everyMinutes(5).create();
  Logger.log(
    "Triggers installed - forwardNewMail runs every minute, sendQueuedReplies every 5 minutes."
  );
}

function forwardNewMail() {
  var secret = getRequiredProperty_("QINORA_WEBHOOK_SECRET");
  var webhookUrl =
    PropertiesService.getScriptProperties().getProperty("QINORA_WEBHOOK_URL") ||
    "https://qinora-backend.onrender.com/webhooks/email";
  var label = getOrCreateLabel_(LABEL_NAME);

  var threads = GmailApp.search(GMAIL_SEARCH_QUERY, 0, MAX_MESSAGES_PER_RUN);
  var forwarded = 0;

  threads.forEach(function (thread) {
    thread.getMessages().forEach(function (message) {
      if (message.isUnread() === false) return;
      if (messageHasLabel_(message, LABEL_NAME)) return;

      var ok = sendToQinora_(message, secret, webhookUrl);
      if (ok) {
        thread.addLabel(label);
        forwarded += 1;
      }
    });
  });

  Logger.log("Forwarded " + forwarded + " message(s).");
}

function sendToQinora_(message, secret, webhookUrl) {
  var payload = {
    sender: extractEmailAddress_(message.getFrom()),
    recipient: extractEmailAddress_(message.getTo()),
    subject: message.getSubject() || "(no subject)",
    body_text: message.getPlainBody().slice(0, 20000),
    message_id: message.getHeader("Message-ID"),
    in_reply_to: message.getHeader("In-Reply-To"),
    references: message.getHeader("References"),
  };
  var body = JSON.stringify(payload);

  var response = UrlFetchApp.fetch(webhookUrl, {
    method: "post",
    contentType: "application/json",
    payload: body,
    headers: {
      "x-idempotency-key": message.getId(),
      "x-qinora-signature": signBody_(body, secret),
    },
    muteHttpExceptions: true,
  });

  var status = response.getResponseCode();
  if (status >= 200 && status < 300) {
    return true;
  }

  Logger.log(
    "QiNora webhook rejected message " +
      message.getId() +
      ": " +
      status +
      " " +
      response.getContentText()
  );
  return false;
}

// The mirror image of forwardNewMail() - polls QiNora for anything queued to
// go out (customer quote replies AND automatic carrier RFQ emails, both
// normalized to the same {queue, id, recipient, subject, body_text} shape -
// see interfaces/http/routers/outbound.py), actually sends each one with
// GmailApp.sendEmail (QiNora's backend has no Gmail credentials of its own),
// and reports sent/failed back per item so QiNora's queues stay in sync.
// Also pings /outbound/collect-carrier-rfqs on the same run, piggybacking
// the carrier-RFQ sourcing sweep onto this trigger's 5-minute cadence rather
// than needing a separate scheduler.
function sendQueuedReplies() {
  var secret = getRequiredProperty_("QINORA_WEBHOOK_SECRET");
  var baseUrl = getOutboundBaseUrl_();

  var items = fetchNextQueued_(baseUrl, secret);
  var sent = 0;
  var failed = 0;

  items.forEach(function (item) {
    try {
      GmailApp.sendEmail(item.recipient, item.subject, item.body_text, { name: "Sandahls" });
      ackOutboundItem_(baseUrl, secret, item, "ack", null);
      sent += 1;
    } catch (error) {
      Logger.log(
        "Failed to send " + item.queue + " item " + item.id + ": " + error
      );
      ackOutboundItem_(baseUrl, secret, item, "fail", String(error));
      failed += 1;
    }
  });

  Logger.log("Sent " + sent + " queued reply/replies, " + failed + " failed.");

  collectCarrierRfqs_(baseUrl, secret);
}

function fetchNextQueued_(baseUrl, secret) {
  // GET has no body to sign - the signature is computed over an empty
  // string on both sides (see interfaces/http/routers/outbound.py's module
  // docstring for why: simpler to keep byte-identical than canonicalizing a
  // URL/query string).
  var response = UrlFetchApp.fetch(baseUrl + "/next-queued", {
    method: "get",
    headers: { "x-qinora-signature": signBody_("", secret) },
    muteHttpExceptions: true,
  });

  if (response.getResponseCode() !== 200) {
    Logger.log(
      "QiNora outbound/next-queued failed: " +
        response.getResponseCode() +
        " " +
        response.getContentText()
    );
    return [];
  }

  return JSON.parse(response.getContentText());
}

function ackOutboundItem_(baseUrl, secret, item, action, errorMessage) {
  var body = action === "fail" ? JSON.stringify({ error_message: errorMessage }) : "{}";
  var url = baseUrl + "/" + item.queue + "/" + item.id + "/" + action;

  var response = UrlFetchApp.fetch(url, {
    method: "post",
    contentType: "application/json",
    payload: body,
    headers: { "x-qinora-signature": signBody_(body, secret) },
    muteHttpExceptions: true,
  });

  if (response.getResponseCode() >= 300) {
    Logger.log(
      "QiNora " +
        action +
        " rejected for " +
        item.queue +
        " item " +
        item.id +
        ": " +
        response.getResponseCode() +
        " " +
        response.getContentText()
    );
  }
}

function collectCarrierRfqs_(baseUrl, secret) {
  var body = "{}";
  var response = UrlFetchApp.fetch(baseUrl + "/collect-carrier-rfqs", {
    method: "post",
    contentType: "application/json",
    payload: body,
    headers: { "x-qinora-signature": signBody_(body, secret) },
    muteHttpExceptions: true,
  });

  if (response.getResponseCode() !== 200) {
    Logger.log(
      "QiNora collect-carrier-rfqs failed: " +
        response.getResponseCode() +
        " " +
        response.getContentText()
    );
  }
}

function getOutboundBaseUrl_() {
  return (
    PropertiesService.getScriptProperties().getProperty("QINORA_OUTBOUND_BASE_URL") ||
    "https://qinora-backend.onrender.com/outbound"
  );
}

// Signs the exact UTF-8 bytes of body, not the raw JS string. This matters:
// computeHmacSha256Signature(string, secret) does not reliably hash the same
// bytes that actually go out over the wire once body contains non-ASCII
// characters (e.g. Swedish å/ä/ö in a forwarded email's text) - it can hash
// UTF-16 code units instead, producing a signature that never matches the
// backend's hmac.new(secret, body.encode("utf-8"), sha256) for any message
// with such characters, while pure-ASCII payloads sign correctly by
// coincidence. Converting to a UTF-8 byte array first removes the ambiguity.
// Both arguments have to be byte arrays together - computeHmacSha256Signature
// has no (Byte[], String) overload, only (String, String) or (Byte[], Byte[]).
function signBody_(body, secret) {
  var bodyBytes = Utilities.newBlob(body).getBytes();
  var secretBytes = Utilities.newBlob(secret).getBytes();
  return "sha256=" + toHex_(Utilities.computeHmacSha256Signature(bodyBytes, secretBytes));
}

// The QiNora webhook payload requires a bare address (recipient/sender are
// validated as EmailStr - see interfaces/http/schemas.py). getFrom()/getTo()
// can return "Display Name <addr@example.com>" and, for getTo(), multiple
// comma-separated addresses - this takes the first address and strips any
// display name.
function extractEmailAddress_(raw) {
  var first = (raw || "").split(",")[0];
  var match = first.match(/<([^<>]+)>/);
  return (match ? match[1] : first).trim();
}

function getOrCreateLabel_(name) {
  return GmailApp.getUserLabelByName(name) || GmailApp.createLabel(name);
}

function messageHasLabel_(message, labelName) {
  return message
    .getThread()
    .getLabels()
    .some(function (label) {
      return label.getName() === labelName;
    });
}

function getRequiredProperty_(key) {
  var value = PropertiesService.getScriptProperties().getProperty(key);
  if (!value) {
    throw new Error(
      "Missing script property " + key + " - set it under Project Settings > Script Properties."
    );
  }
  return value;
}

function toHex_(bytes) {
  return bytes
    .map(function (b) {
      var v = (b < 0 ? b + 256 : b).toString(16);
      return v.length === 1 ? "0" + v : v;
    })
    .join("");
}
