"""httpx-based ARM REST client — all calls are async and authenticated."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from app.services.auth import get_token

log = logging.getLogger(__name__)

_ARM_BASE = "https://management.azure.com"
_API_VERSIONS = {
    "subscriptions": "2022-12-01",
    "resourcegroups": "2021-04-01",
    "resources": "2021-04-01",
    "pim_eligible": "2020-10-01",
    "pim_active": "2020-10-01",
    "pim_requests": "2020-10-01",
    "role_definitions": "2022-04-01",
}

# Shared client — recreated on tenant switch
_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)
    return _client


async def _get(
    path: str,
    api_version: str,
    tenant_id: str | None = None,
    params: dict | None = None,
) -> Any:
    """GET {ARM_BASE}{path}?api-version=... and return parsed JSON body."""
    token = await get_token(tenant_id=tenant_id)
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    qp = {"api-version": api_version, **(params or {})}
    url = f"{_ARM_BASE}{path}"

    resp = await _get_client().get(url, headers=headers, params=qp)
    resp.raise_for_status()
    return resp.json()


async def _put(
    path: str,
    api_version: str,
    body: dict,
    tenant_id: str | None = None,
) -> Any:
    token = await get_token(tenant_id=tenant_id)
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    url = f"{_ARM_BASE}{path}"
    resp = await _get_client().put(url, headers=headers, params={"api-version": api_version}, json=body)
    resp.raise_for_status()
    return resp.json()


async def _paginate(
    path: str,
    api_version: str,
    tenant_id: str | None = None,
    params: dict | None = None,
) -> list[Any]:
    """Follow nextLink pagination and return all value items."""
    results: list[Any] = []
    token = await get_token(tenant_id=tenant_id)
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    qp = {"api-version": api_version, **(params or {})}
    url = f"{_ARM_BASE}{path}"
    client = _get_client()

    while url:
        resp = await client.get(url, headers=headers, params=qp)
        resp.raise_for_status()
        data = resp.json()
        results.extend(data.get("value", []))
        url = data.get("nextLink")
        qp = {}  # nextLink already contains all params

    return results


# ── Subscriptions ─────────────────────────────────────────────────────────────

async def list_subscriptions(tenant_id: str | None = None) -> list[dict]:
    return await _paginate(
        "/subscriptions",
        _API_VERSIONS["subscriptions"],
        tenant_id=tenant_id,
    )


# ── Resource groups & resources ───────────────────────────────────────────────

async def list_resource_groups(
    subscription_id: str,
    tenant_id: str | None = None,
) -> list[dict]:
    return await _paginate(
        f"/subscriptions/{subscription_id}/resourcegroups",
        _API_VERSIONS["resourcegroups"],
        tenant_id=tenant_id,
    )


async def list_resources(
    subscription_id: str,
    tenant_id: str | None = None,
) -> list[dict]:
    return await _paginate(
        f"/subscriptions/{subscription_id}/resources",
        _API_VERSIONS["resources"],
        tenant_id=tenant_id,
    )


# ── PIM ───────────────────────────────────────────────────────────────────────

async def list_pim_eligible(
    subscription_id: str,
    tenant_id: str | None = None,
) -> list[dict]:
    scope = f"/subscriptions/{subscription_id}"
    return await _paginate(
        f"{scope}/providers/Microsoft.Authorization/roleEligibilityScheduleInstances",
        _API_VERSIONS["pim_eligible"],
        tenant_id=tenant_id,
        params={"$filter": "asTarget()"},
    )


async def list_pim_active(
    subscription_id: str,
    tenant_id: str | None = None,
) -> list[dict]:
    scope = f"/subscriptions/{subscription_id}"
    return await _paginate(
        f"{scope}/providers/Microsoft.Authorization/roleAssignmentScheduleInstances",
        _API_VERSIONS["pim_active"],
        tenant_id=tenant_id,
        params={"$filter": "asTarget()"},
    )


async def list_pim_pending(
    subscription_id: str,
    tenant_id: str | None = None,
) -> list[dict]:
    scope = f"/subscriptions/{subscription_id}"
    return await _paginate(
        f"{scope}/providers/Microsoft.Authorization/roleAssignmentScheduleRequests",
        _API_VERSIONS["pim_requests"],
        tenant_id=tenant_id,
        params={"$filter": "asRequestor()"},
    )


async def activate_role(
    subscription_id: str,
    request_name: str,
    role_definition_id: str,
    principal_id: str,
    scope: str,
    justification: str,
    duration_hours: int,
    tenant_id: str | None = None,
) -> dict:
    """PUT a PIM roleAssignmentScheduleRequest to activate an eligible role."""
    import uuid
    req_name = request_name or str(uuid.uuid4())
    path = (
        f"/subscriptions/{subscription_id}/providers/Microsoft.Authorization"
        f"/roleAssignmentScheduleRequests/{req_name}"
    )
    body = {
        "properties": {
            "principalId": principal_id,
            "roleDefinitionId": role_definition_id,
            "requestType": "SelfActivate",
            "scheduleInfo": {
                "startDateTime": None,  # immediate
                "expiration": {
                    "type": "AfterDuration",
                    "duration": f"PT{duration_hours}H",
                },
            },
            "justification": justification,
            "linkedRoleEligibilityScheduleId": None,
            "scope": scope,
        }
    }
    return await _put(path, _API_VERSIONS["pim_requests"], body, tenant_id=tenant_id)


async def get_role_assignment_request(
    subscription_id: str,
    request_name: str,
    tenant_id: str | None = None,
) -> dict:
    path = (
        f"/subscriptions/{subscription_id}/providers/Microsoft.Authorization"
        f"/roleAssignmentScheduleRequests/{request_name}"
    )
    return await _get(path, _API_VERSIONS["pim_requests"], tenant_id=tenant_id)


async def get_role_definition(
    role_definition_id: str,
    tenant_id: str | None = None,
) -> dict:
    """Fetch a role definition by its full resource ID."""
    return await _get(role_definition_id, _API_VERSIONS["role_definitions"], tenant_id=tenant_id)
