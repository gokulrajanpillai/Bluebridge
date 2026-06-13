"""Activity log and container stdout/stderr retrieval via ARM REST."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.services import arm

log = logging.getLogger(__name__)

# Resources that expose container-level stdout/stderr logs
_CONTAINER_LOG_TYPES = {
    "microsoft.containerinstance/containergroups",
}

# Resources that expose App Service deployment logs
_WEBAPP_LOG_TYPES = {
    "microsoft.web/sites",
    "microsoft.web/sites/slots",
}


class PermissionDeniedError(Exception):
    def __init__(self, operation: str, required_role: str = "") -> None:
        self.operation = operation
        self.required_role = required_role
        hint = f" Required role: **{required_role}**." if required_role else ""
        super().__init__(f"Permission denied for {operation}.{hint}")


def _permission_hint(exc: httpx.HTTPStatusError) -> str:
    """Map HTTP 403 responses to a human-readable permission hint."""
    if exc.response.status_code == 403:
        return "Monitoring Reader"
    return ""


# ── Activity Log ──────────────────────────────────────────────────────────────

def get_activity_logs(
    resource_id: str,
    tenant_id: str = "",
    hours: int = 24,
) -> list[dict[str, Any]]:
    """Return activity log events for *resource_id* covering the last *hours* hours."""
    parts = resource_id.strip("/").split("/")
    sub_id = parts[1] if len(parts) >= 2 else ""
    if not sub_id:
        return []

    since = (datetime.now(UTC) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    escaped = resource_id.replace("'", "''")

    try:
        raw = arm._paginate(
            f"/subscriptions/{sub_id}/providers/Microsoft.Insights/activityLogs",
            "2017-03-01-preview",
            tenant_id=tenant_id,
            params={
                "$filter": f"resourceId eq '{escaped}' and eventTimestamp ge '{since}'",
                "$select": (
                    "eventTimestamp,operationName,status,caller,level,correlationId,description"
                ),
            },
        )
    except httpx.HTTPStatusError as exc:
        role = _permission_hint(exc)
        raise PermissionDeniedError("read activity logs", role) from exc

    events = []
    for e in raw:
        events.append({
            "timestamp": e.get("eventTimestamp", ""),
            "operation": (e.get("operationName") or {}).get("localizedValue")
                or (e.get("operationName") or {}).get("value", ""),
            "status": (e.get("status") or {}).get("localizedValue", ""),
            "caller": e.get("caller", ""),
            "level": e.get("level", ""),
            "description": e.get("description", ""),
            "correlation_id": e.get("correlationId", ""),
        })
    return events


# ── Container Instance logs ───────────────────────────────────────────────────

def get_container_group_containers(
    subscription_id: str,
    resource_group: str,
    group_name: str,
    tenant_id: str = "",
) -> list[str]:
    """Return container names within a container group."""
    try:
        data = arm._get(
            f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/"
            f"Microsoft.ContainerInstance/containerGroups/{group_name}",
            "2023-05-01",
            tenant_id=tenant_id,
        )
    except httpx.HTTPStatusError as exc:
        raise PermissionDeniedError("read container group", _permission_hint(exc)) from exc
    containers = data.get("properties", {}).get("containers", [])
    return [c.get("name", "") for c in containers if c.get("name")]


def get_container_logs(
    subscription_id: str,
    resource_group: str,
    group_name: str,
    container_name: str,
    tenant_id: str = "",
    tail: int = 300,
) -> str:
    """Return stdout/stderr log text from a Container Instance container."""
    try:
        data = arm._get(
            f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/"
            f"Microsoft.ContainerInstance/containerGroups/{group_name}/containers/"
            f"{container_name}/logs",
            "2023-05-01",
            tenant_id=tenant_id,
            params={"tail": tail},
        )
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 403:
            raise PermissionDeniedError(
                "read container logs",
                "Contributor or AcrPull on the container group",
            ) from exc
        raise
    return data.get("content", "")


# ── App Service deployment logs ───────────────────────────────────────────────

def get_webapp_deployment_logs(
    subscription_id: str,
    resource_group: str,
    site_name: str,
    tenant_id: str = "",
) -> list[dict[str, Any]]:
    """Return recent deployment log entries for an App Service."""
    try:
        data = arm._get(
            f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/"
            f"Microsoft.Web/sites/{site_name}/deployments",
            "2022-03-01",
            tenant_id=tenant_id,
        )
    except httpx.HTTPStatusError as exc:
        raise PermissionDeniedError("read deployment logs", "Website Contributor") from exc
    entries = []
    for d in data.get("value", []):
        p = d.get("properties", {})
        entries.append({
            "id": d.get("name", ""),
            "status": p.get("status", 0),
            "message": p.get("message", ""),
            "author": p.get("author", ""),
            "deployer": p.get("deployer", ""),
            "created": p.get("startTime", ""),
            "completed": p.get("endTime", ""),
            "active": p.get("active", False),
        })
    return entries
