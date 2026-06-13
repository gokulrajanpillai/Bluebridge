"""PIM data loading, normalisation, and caching. Stateless — caller owns cache."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from app.services import arm

log = logging.getLogger(__name__)

# Module-level cache: "{tenant_id}:{subscription_id}" → {eligible, active, pending}
_pim_cache: dict[str, dict[str, list]] = {}

# Module-level cache: "{tenant_id}:{subscription_id}:resources" → list[dict]
_resources_cache: dict[str, list] = {}


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def _fmt_relative(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    now = datetime.now(UTC)
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
    parts = scope.strip("/").split("/")
    if len(parts) == 2 and parts[0] == "subscriptions":
        sub_id = parts[1]
        for s in subscriptions:
            if s.get("subscriptionId") == sub_id or s.get("id", "").endswith(sub_id):
                return s.get("displayName") or s.get("name") or sub_id
        return sub_id
    if len(parts) >= 4 and parts[2] == "resourceGroups":
        return parts[3]
    if len(parts) >= 6:
        return "/".join(parts[4:])
    return scope


def _normalise(raw: dict, status: str, subscriptions: list[dict]) -> dict:
    props = raw.get("properties", {})
    scope = props.get("scope", "")
    end_dt = _parse_dt(props.get("endDateTime"))
    return {
        "id": raw.get("id", ""),
        "name": raw.get("name", ""),
        "status": status,
        "role_definition_id": props.get("roleDefinitionId", ""),
        "role_name": (
            props.get("expandedProperties", {}).get("roleDefinition", {}).get("displayName", "")
        ),
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
    status_map = {
        "PendingApproval": "PendingApproval",
        "Provisioning": "Provisioning",
        "Granted": "Active",
        "Denied": "Denied",
        "Failed": "Failed",
        "Canceled": "Failed",
        "Revoked": "Failed",
    }
    status = status_map.get(props.get("status", ""), props.get("status", "Pending"))
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


def load_pim_data(
    subscription_id: str,
    tenant_id: str,
    subscriptions: list[dict],
    force: bool = False,
) -> dict[str, list]:
    """Return {eligible, active, pending} for a subscription. Results are module-cached."""
    cache_key = f"{tenant_id}:{subscription_id}"
    if not force and cache_key in _pim_cache:
        return _pim_cache[cache_key]

    def _safe(fn: Any, *args: Any) -> list[dict]:
        try:
            return fn(*args)
        except Exception as exc:
            log.warning("PIM load error (%s): %s", fn.__name__, exc)
            return []

    eligible_raw = _safe(arm.list_pim_eligible, subscription_id, tenant_id)
    active_raw = _safe(arm.list_pim_active, subscription_id, tenant_id)
    pending_raw = _safe(arm.list_pim_pending, subscription_id, tenant_id)

    data: dict[str, list] = {
        "eligible": [_normalise(r, "Eligible", subscriptions) for r in eligible_raw],
        "active": [_normalise(r, "Active", subscriptions) for r in active_raw],
        "pending": [_normalise_pending(r, subscriptions) for r in pending_raw],
    }
    _pim_cache[cache_key] = data
    return data


def clear_cache(tenant_id: str = "") -> None:
    """Evict cached PIM data for a tenant (or all if tenant_id is empty)."""
    for key in list(_pim_cache):
        if not tenant_id or key.startswith(f"{tenant_id}:"):
            del _pim_cache[key]


def load_resources(
    subscription_id: str,
    tenant_id: str,
    force: bool = False,
) -> list[dict]:
    """Return normalised resource list for a subscription. Results are module-cached."""
    cache_key = f"{tenant_id}:{subscription_id}:resources"
    if not force and cache_key in _resources_cache:
        return _resources_cache[cache_key]

    try:
        raw = arm.list_resources(subscription_id, tenant_id)
    except Exception as exc:
        log.warning("Resources load error for %s: %s", subscription_id, exc)
        return []

    resources: list[dict] = []
    for r in raw:
        rtype = r.get("type", "")
        resource_id = r.get("id", "")
        parts = resource_id.split("/")
        rg = ""
        for i, p in enumerate(parts):
            if p.lower() == "resourcegroups" and i + 1 < len(parts):
                rg = parts[i + 1]
                break
        resources.append({
            "id": resource_id,
            "name": r.get("name", ""),
            "type": rtype,
            "type_short": rtype.split("/")[-1] if "/" in rtype else rtype,
            "provider": rtype.split("/")[0] if "/" in rtype else "",
            "resource_group": rg,
            "location": r.get("location", ""),
            "tags": r.get("tags", {}),
        })

    _resources_cache[cache_key] = resources
    return resources


def clear_resources_cache(tenant_id: str = "", subscription_id: str = "") -> None:
    """Evict cached resource data."""
    for key in list(_resources_cache):
        parts = key.split(":")
        key_tenant = parts[0] if parts else ""
        key_sub = parts[1] if len(parts) > 1 else ""
        if (not tenant_id or key_tenant == tenant_id) and (
            not subscription_id or key_sub == subscription_id
        ):
            del _resources_cache[key]
