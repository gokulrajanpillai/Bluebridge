"""Token cache + refresh + tenant management on top of az_cli."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from app.services import az_cli
from app.state import state


_REFRESH_BUFFER_SECONDS = 300  # refresh 5 min before expiry


def _parse_expires_on(expires_on: str) -> datetime:
    """Parse az expiresOn string to an aware UTC datetime."""
    # az returns either ISO format or a date-time string
    for fmt in (
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
    ):
        try:
            dt = datetime.strptime(expires_on, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    # Last resort: assume UTC
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


async def get_token(
    resource: str = "https://management.azure.com/",
    tenant_id: str | None = None,
) -> str:
    """
    Return a valid bearer token string, fetching/refreshing via az CLI as needed.
    Results are cached in state._token_cache.
    """
    tid = tenant_id or state.active_tenant_id or ""
    cache_key = (tid, resource)

    entry = state._token_cache.get(cache_key)
    if entry and not _is_expired(entry):
        return entry["accessToken"]

    # Fetch fresh token
    token_data = await az_cli.get_access_token(resource=resource, tenant_id=tid or None)
    state._token_cache[cache_key] = token_data
    return token_data["accessToken"]


async def populate_identity(account: dict[str, Any]) -> None:
    """Fill state identity fields from an `az account show` dict."""
    user = account.get("user", {})
    state.account_name = account.get("name") or user.get("name", "")
    state.account_upn = user.get("name", "")
    state.account_id = account.get("id", "")
    state.active_tenant_id = account.get("tenantId", "")


async def load_tenants_and_subscriptions() -> None:
    """Populate state.tenants and state.subscriptions."""
    tenants, accounts = await asyncio.gather(
        az_cli.list_tenants(),
        az_cli.list_accounts(),
    )
    state.tenants = tenants
    state.subscriptions = accounts

    # Set active tenant name
    for t in tenants:
        if t.get("tenantId") == state.active_tenant_id:
            state.active_tenant_name = t.get("displayName") or state.active_tenant_id
            break
    if not state.active_tenant_name:
        state.active_tenant_name = state.active_tenant_id


async def switch_tenant(tenant_id: str) -> None:
    """
    Switch the active tenant: re-login if needed, invalidate caches, reload data.
    """
    if tenant_id == state.active_tenant_id:
        return

    state.clear_caches_for_tenant(state.active_tenant_id or "")
    await az_cli.login(tenant_id=tenant_id)

    account = await az_cli.get_account()
    if account:
        await populate_identity(account)
        state.active_tenant_id = tenant_id

    await load_tenants_and_subscriptions()
