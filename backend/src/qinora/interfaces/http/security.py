import hmac
from hashlib import sha256


def verify_hmac_signature(secret: str, body: bytes, signature: str | None) -> bool:
    if not secret or not signature:
        return False

    expected = hmac.new(secret.encode("utf-8"), body, sha256).hexdigest()
    provided = signature.removeprefix("sha256=")
    return hmac.compare_digest(expected, provided)
