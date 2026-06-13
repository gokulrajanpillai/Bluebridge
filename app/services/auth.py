"""Token cache + refresh on top of az_cli. Stateless — no global app state."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.services import az_cli

_REFRESH_BUFFER_SECONDS = 300

# Module-level token cache: (tenant_id, resource) → token dict
_token_cache: dict[tuple[str, str], dict[str, Any]] = {}


def _parse_expires_on(expires_on: str) -> datetime:
    for fmt in (
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
    ):
        try:
            return datetime.strptime(expires_on, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return datetime.fromisoformat(expires_on.replace("Z", "+00:00"))


def _is_expired(entry: dict[str, Any]) -> bool:
    expires_on = entry.get("expiresOn") or entry.get("expires_on", "")
    if not expires_on:
        return True
    try:
        exp = _parse_expires_on(str(expires_on))
        remaining = (exp - datetime.now(timezone.utc)).total_seconds()
        return remaining < _REFRESH_BUFFER_SECONDS
    except Exception:
        return True


def get_token(
    resource: str = "https://management.azure.com/",
    tenant_id: str = "",
) -> str:
    """Return a valid bearer token string, fetching/refreshing via az CLI as needed."""
    cache_key = (tenant_id, resource)
    entry = _token_cache.get(cache_key)
    if entry and not _is_expired(entry):
        return entry["accessToken"]
    token_data = az_cli.get_access_token(resource=resource, tenant_id=tenant_id or None)
    _token_cache[cache_key] = token_data
    return token_data["accessToken"]


def clear_token_cache(tenant_id: str = "") -> None:
    """Evict all cached tokens for a tenant (call on tenant switch or logout)."""
    for key in list(_token_cache):
        if key[0] == tenant_id or not tenant_id:
            del _token_cache[key]


def load_tenants_and_subscriptions() -> tuple[list[dict], list[dict]]:
    """Return (tenants, subscriptions). Callers store these in session state."""
    tenants = az_cli.list_tenants()
    subscriptions = az_cli.list_accounts()
    return tenants, subscriptions
