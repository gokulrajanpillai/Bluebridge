"""PIM data loading, normalisation, and caching."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Any

from app.services import arm
from app.state import state

log = logging.getLogger(__name__)


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def _fmt_relative(dt: datetime | None) -> str:
    """Return relative time string like 'in 475h 48m' or 'Expired'."""
    if dt is None:
        return "—"
    now = datetime.now(timezone.utc)
    delta = dt - now
    if delta.total_seconds() < 0:
        return "Expired"
    total_hours = int(delta.total_seconds() // 3600)
    minutes = int((delta.total_seconds() % 3600) // 60)
    if total_hours > 0:
        return f"in {total_hours}h {minutes}m"
    return f"in {minutes}m"


def _fmt_absolute(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    return dt.strftime("%-m/%-d/%Y, %-I:%M:%S %p") if hasattr(dt, "strftime") else str(dt)


def _scope_display(scope: str, subscriptions: list[dict]) -> str:
    """Convert /subscriptions/.../resourceGroups/... to a friendly name."""
    parts = scope.strip("/").split("/")
    # /subscriptions/{id}
    if len(parts) == 2 and parts[0] == "subscriptions":
        sub_id = parts[1]
        for s in subscriptions:
            if s.get("subscriptionId") == sub_id or s.get("id", "").endswith(sub_id):
                return s.get("displayName") or s.get("name") or sub_id
        return sub_id
    # /subscriptions/{id}/resourceGroups/{rg}
    if len(parts) >= 4 and parts[2] == "resourceGroups":
        return parts[3]
    # /subscriptions/{id}/resourceGroups/{rg}/providers/...
    if len(parts) >= 6:
        return "/".join(parts[4:])
    return scope


def _normalise_eligible(raw: dict, subscriptions: list[dict]) -> dict:
    props = raw.get("properties", {})
    scope = props.get("scope", "")
    end_dt = _parse_dt(props.get("endDateTime"))
    return {
        "id": raw.get("id", ""),
        "name": raw.get("name", ""),
        "status": "Eligible",
        "role_definition_id": props.get("roleDefinitionId", ""),
        "role_name": props.get("expandedProperties", {}).get("roleDefinition", {}).get("displayName", ""),
        "scope": scope,
        "scope_display": _scope_display(scope, subscriptions),
        "scope_type": props.get("expandedProperties", {}).get("scope", {}).get("type", ""),
        "member_type": props.get("memberType", ""),
        "principal_id": props.get("principalId", ""),
        "end_dt": end_dt,
        "expires_relative": _fmt_relative(end_dt),
        "expires_absolute": _fmt_absolute(end_dt),
        "_raw": raw,
    }


def _normalise_active(raw: dict, subscriptions: list[dict]) -> dict:
    props = raw.get("properties", {})
    scope = props.get("scope", "")
    end_dt = _parse_dt(props.get("endDateTime"))
    return {
        "id": raw.get("id", ""),
        "name": raw.get("name", ""),
        "status": "Active",
        "role_definition_id": props.get("roleDefinitionId", ""),
        "role_name": props.get("expandedProperties", {}).get("roleDefinition", {}).get("displayName", ""),
        "scope": scope,
        "scope_display": _scope_display(scope, subscriptions),
        "scope_type": props.get("expandedProperties", {}).get("scope", {}).get("type", ""),
        "member_type": props.get("memberType", ""),
        "principal_id": props.get("principalId", ""),
        "end_dt": end_dt,
        "expires_relative": _fmt_relative(end_dt),
        "expires_absolute": _fmt_absolute(end_dt),
        "_raw": raw,
    }


def _normalise_pending(raw: dict, subscriptions: list[dict]) -> dict:
    props = raw.get("properties", {})
    scope = props.get("scope", "")
    req_status = props.get("status", "PendingApproval")
    # Map ARM status strings to our display status
    status_map = {
        "PendingApproval": "PendingApproval",
        "Provisioning": "Provisioning",
        "Granted": "Active",
        "Denied": "Denied",
        "Failed": "Failed",
        "Canceled": "Failed",
        "Revoked": "Failed",
    }
    status = status_map.get(req_status, req_status)
    return {
        "id": raw.get("id", ""),
        "name": raw.get("name", ""),
        "status": status,
        "role_definition_id": props.get("roleDefinitionId", ""),
        "role_name": "",
        "scope": scope,
        "scope_display": _scope_display(scope, subscriptions),
        "scope_type": "",
        "member_type": "",
        "principal_id": props.get("principalId", ""),
        "end_dt": None,
        "expires_relative": "—",
        "expires_absolute": "—",
        "justification": props.get("justification", ""),
        "failure_reason": props.get("statusDetails", {}).get("statusReason", ""),
        "_raw": raw,
    }


async def load_pim_data(
    subscription_id: str,
    tenant_id: str | None = None,
    force: bool = False,
) -> dict[str, list]:
    """
    Load and cache PIM eligible, active, and pending assignments for a subscription.
    Returns { "eligible": [...], "active": [...], "pending": [...] }.
    """
    tid = tenant_id or state.active_tenant_id or ""
    cache_key = f"{tid}:{subscription_id}"

    if not force and cache_key in state.pim_cache:
        return state.pim_cache[cache_key]

    eligible_raw, active_raw, pending_raw = await asyncio.gather(
        arm.list_pim_eligible(subscription_id, tenant_id=tid or None),
        arm.list_pim_active(subscription_id, tenant_id=tid or None),
        arm.list_pim_pending(subscription_id, tenant_id=tid or None),
        return_exceptions=True,
    )

    subs = state.subscriptions

    def _safe_list(result, normalise_fn) -> list:
        if isinstance(result, Exception):
            log.warning("PIM load error: %s", result)
            return []
        return [normalise_fn(r, subs) for r in result]

    data = {
        "eligible": _safe_list(eligible_raw, _normalise_eligible),
        "active": _safe_list(active_raw, _normalise_active),
        "pending": _safe_list(pending_raw, _normalise_pending),
    }
    state.pim_cache[cache_key] = data
    return data
