/**
 * QiNora Gmail intake bridge.
 *
 * Runs INSIDE the Google Workspace mailbox that receives customer/carrier
 * emails (e.g. farah@qinora.org). On a time-driven trigger it finds unread
 * mail that hasn't been forwarded yet, POSTs each one to QiNora's
 * `/webhooks/email` endpoint with an HMAC-SHA256 signature, and labels the
 * message so it's never sent twice.
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
 *   3. Run the `installTrigger` function once from the editor (Run menu).
 *      Approve the Gmail + external-request permissions Google asks for.
 *      This installs a time-driven trigger that calls `forwardNewMail`
 *      every 5 minutes from then on - you don't need to run anything by
 *      hand again.
 *   4. Send a test email to this mailbox and check the QiNora Inbox page;
 *      it should appear within 5 minutes labelled "QiNora/Forwarded".
 *
 * Everything this script touches lives inside your own Google account and
 * Apps Script project - QiNora only ever sees the forwarded email content.
 */

var LABEL_NAME = "QiNora/Forwarded";
var GMAIL_SEARCH_QUERY = "is:unread in:inbox -label:" + LABEL_NAME;
var MAX_MESSAGES_PER_RUN = 20;

function installTrigger() {
  ScriptApp.getProjectTriggers().forEach(function (trigger) {
    if (trigger.getHandlerFunction() === "forwardNewMail") {
      ScriptApp.deleteTrigger(trigger);
    }
  });
  ScriptApp.newTrigger("forwardNewMail").timeBased().everyMinutes(5).create();
  Logger.log("Trigger installed - forwardNewMail will run every 5 minutes.");
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
    sender: message.getFrom().replace(/^.*<(.+)>$/, "$1"),
    subject: message.getSubject() || "(no subject)",
    body_text: message.getPlainBody().slice(0, 20000),
  };
  var body = JSON.stringify(payload);
  var signature = "sha256=" + toHex_(Utilities.computeHmacSha256Signature(body, secret));

  var response = UrlFetchApp.fetch(webhookUrl, {
    method: "post",
    contentType: "application/json",
    payload: body,
    headers: {
      "x-idempotency-key": message.getId(),
      "x-qinora-signature": signature,
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
