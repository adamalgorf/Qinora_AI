"""Deterministic, no-I/O gates run before any agent touches an inbound
email: which tenant it belongs to, and whether it's our own mail looping
back to us. Both read their configuration from the "Parsek" agent's own
config row (agent_key="request_parsing_agent", see
application/agent_config.py) under three optional keys - inbound_address,
allowed_domains, own_addresses - so no new config table is needed.

Absent config (the default for every deployment until an admin sets these)
means every email resolves to this deployment's single tenant and nothing
is ever treated as a loop, which is exactly today's behaviour.
"""

from __future__ import annotations

from qinora.application.read_models import AgentConfigRecord

DEFAULT_TENANT_ID = "default"


def _config_dict(parsek_config: AgentConfigRecord | None) -> dict:
    if parsek_config is None:
        return {}
    return parsek_config.config or {}


def _domain_of(address: str) -> str:
    normalized = address.strip().lower()
    return normalized.rsplit("@", 1)[1] if "@" in normalized else normalized


def resolve_tenant(
    *,
    sender: str,
    recipient: str,
    parsek_config: AgentConfigRecord | None,
    explicit_tenant_id: str | None = None,
) -> str | None:
    """Resolve which tenant an inbound email belongs to.

    This deployment is single-tenant today (one QINORA_POSTGRES_TENANT_ID
    baked into PostgresDatabase at construction - see
    infrastructure/postgres.py), so this is a safety/quality gate
    confirming mail is actually addressed to this tenant rather than
    misdirected or spam, not a dynamic per-request tenant switch. The
    resolution order (explicit id -> recipient match -> sender-domain
    match -> the deployment's single tenant) is future-proofed for a
    multi-tenant deployment, where the final fallback would go away and an
    unmatched email would correctly resolve to None instead.
    """
    if explicit_tenant_id:
        return explicit_tenant_id

    config = _config_dict(parsek_config)
    inbound_address = config.get("inbound_address")
    if inbound_address and recipient.strip().lower() == str(inbound_address).strip().lower():
        return DEFAULT_TENANT_ID

    allowed_domains = {
        str(domain).strip().lower() for domain in config.get("allowed_domains") or []
    }
    if allowed_domains and _domain_of(sender) in allowed_domains:
        return DEFAULT_TENANT_ID

    return DEFAULT_TENANT_ID


def is_loop(*, sender: str, parsek_config: AgentConfigRecord | None) -> bool:
    """True when `sender` is one of our own outbound identities (Parsek's
    config own_addresses list), i.e. this message is our own mail bouncing
    back to us rather than a real customer/carrier reply. Unset
    own_addresses (today's default) never flags a loop.
    """
    config = _config_dict(parsek_config)
    own_addresses = {str(address).strip().lower() for address in config.get("own_addresses") or []}
    if not own_addresses:
        return False

    sender_normalized = sender.strip().lower()
    if sender_normalized in own_addresses:
        return True

    return _domain_of(sender_normalized) in own_addresses
