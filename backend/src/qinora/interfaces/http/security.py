import hmac
import json
import time
from base64 import urlsafe_b64decode, urlsafe_b64encode
from hashlib import sha256

from qinora.application.auth import AuthContext, Role


def verify_hmac_signature(secret: str, body: bytes, signature: str | None) -> bool:
    if not secret or not signature:
        return False

    expected = hmac.new(secret.encode("utf-8"), body, sha256).hexdigest()
    provided = signature.removeprefix("sha256=")
    return hmac.compare_digest(expected, provided)


class AuthTokenError(ValueError):
    pass


def create_auth_token(
    context: AuthContext,
    secret: str,
    expires_in_seconds: int = 60 * 60 * 8,
    now: int | None = None,
) -> str:
    issued_at = int(now if now is not None else time.time())
    payload = {
        "exp": issued_at + expires_in_seconds,
        "roles": sorted(role.value for role in context.roles),
        "sub": context.user_id,
        "tenant_id": context.tenant_id,
    }
    payload_segment = _base64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = _sign(payload_segment, secret)
    return f"{payload_segment}.{signature}"


def parse_auth_token(token: str, secret: str, now: int | None = None) -> AuthContext:
    try:
        payload_segment, signature = token.split(".", maxsplit=1)
    except ValueError as error:
        raise AuthTokenError("Malformed bearer token") from error

    expected_signature = _sign(payload_segment, secret)
    if not hmac.compare_digest(expected_signature, signature):
        raise AuthTokenError("Invalid bearer token signature")

    try:
        payload = json.loads(_base64url_decode(payload_segment))
        expires_at = int(payload["exp"])
        roles = frozenset(Role(role) for role in payload["roles"])
        user_id = str(payload["sub"])
        tenant_id = str(payload["tenant_id"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise AuthTokenError("Invalid bearer token payload") from error

    if expires_at <= int(now if now is not None else time.time()):
        raise AuthTokenError("Bearer token has expired")

    return AuthContext(user_id=user_id, tenant_id=tenant_id, roles=roles)


def _sign(payload_segment: str, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), payload_segment.encode("utf-8"), sha256).digest()
    return _base64url_encode(digest)


def _base64url_encode(value: bytes) -> str:
    return urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _base64url_decode(value: str) -> bytes:
    padded = value + ("=" * (-len(value) % 4))
    return urlsafe_b64decode(padded.encode("ascii"))
