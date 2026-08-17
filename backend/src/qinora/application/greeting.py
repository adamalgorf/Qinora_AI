"""Derives a first name to greet a customer by, so outbound emails read
"Hej Adam!" instead of a generic "Hej!" - the closest the intake pipeline
can get to a human assistant who already knows who they're writing to.

Prefers the sender's actual display name (captured from the Gmail "From"
header by integrations/gmail-intake-bridge/Code.gs - see
extractDisplayName_() there and EmailWebhookPayload.sender_name). Falls
back to guessing from the email address's local part (e.g.
"adam.algorf@x.se" -> "Adam") only when no display name was available,
which happens for older/forwarded messages or senders whose mail client
never set one.
"""

import re

_LOCAL_PART_NAME_RE = re.compile(r"[A-Za-zÅÄÖåäö]+")


def first_name(sender_name: str | None, sender_email: str) -> str:
    if sender_name and sender_name.strip():
        token = sender_name.strip().split()[0]
        token = token.strip(".,;:'\"")
        if token:
            return token[:1].upper() + token[1:].lower()

    local_part = sender_email.split("@", 1)[0]
    match = _LOCAL_PART_NAME_RE.match(local_part)
    if match:
        guess = match.group(0)
        return guess[:1].upper() + guess[1:].lower()

    return ""


def greeting(sender_name: str | None, sender_email: str) -> str:
    name = first_name(sender_name, sender_email)
    return f"Hej {name}!" if name else "Hej!"
