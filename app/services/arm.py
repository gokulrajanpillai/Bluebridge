"""Synchronous httpx ARM REST client — authenticated via auth.get_token."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.services.auth import get_token

log = logging.getLogger(__name__)

_ARM_BASE = "https://management.azure.com"
_API_VERSIONS = {
    "subscriptions": "2022-12-01",
    "pim_eligible": "2020-10-01",
    "pim_active": "2020-10-01",
    "pim_requests": "2020-10-01",
    "resources": "2021-04-01",
}

_client: httpx.Client | None = None


def _get_client() -> httpx.Client:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.Client(timeout=30.0, follow_redirects=True)
    return _client


def _headers(tenant_id: str = "") -> dict[str, str]:
    token = get_token(tenant_id=tenant_id)
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _get(path: str, api_version: str, tenant_id: str = "", params: dict | None = None) -> Any:
    qp = {"api-version": api_version, **(params or {})}
    resp = _get_client().get(
        f"{_ARM_BASE}{path}", headers=_headers(tenant_id), params=qp
    )
    resp.raise_for_status()
    return resp.json()


def _put(path: str, api_version: str, body: dict, tenant_id: str = "") -> Any:
    resp = _get_client().put(
        f"{_ARM_BASE}{path}",
        headers=_headers(tenant_id),
        params={"api-version": api_version},
        json=body,
    )
    resp.raise_for_status()
    return resp.json()


def _paginate(
    path: str, api_version: str, tenant_id: str = "", params: dict | None = None
) -> list[Any]:
    results: list[Any] = []
    qp: dict = {"api-version": api_version, **(params or {})}
    url: str | None = f"{_ARM_BASE}{path}"
    client = _get_client()
    hdrs = _headers(tenant_id)

    while url:
        resp = client.get(url, headers=hdrs, params=qp)
        resp.raise_for_status()
        data = resp.json()
        results.extend(data.get("value", []))
        url = data.get("nextLink")
        qp = {}

    return results


# ── Subscriptions ─────────────────────────────────────────────────────────────

def list_subscriptions(tenant_id: str = "") -> list[dict]:
    return _paginate("/subscriptions", _API_VERSIONS["subscriptions"], tenant_id=tenant_id)


# ── PIM ───────────────────────────────────────────────────────────────────────

def list_pim_eligible(subscription_id: str, tenant_id: str = "") -> list[dict]:
    scope = f"/subscriptions/{subscription_id}"
    return _paginate(
        f"{scope}/providers/Microsoft.Authorization/roleEligibilityScheduleInstances",
        _API_VERSIONS["pim_eligible"],
        tenant_id=tenant_id,
        params={"$filter": "asTarget()"},
    )


def list_pim_active(subscription_id: str, tenant_id: str = "") -> list[dict]:
    scope = f"/subscriptions/{subscription_id}"
    return _paginate(
        f"{scope}/providers/Microsoft.Authorization/roleAssignmentScheduleInstances",
        _API_VERSIONS["pim_active"],
        tenant_id=tenant_id,
        params={"$filter": "asTarget()"},
    )


def list_pim_pending(subscription_id: str, tenant_id: str = "") -> list[dict]:
    scope = f"/subscriptions/{subscription_id}"
    return _paginate(
        f"{scope}/providers/Microsoft.Authorization/roleAssignmentScheduleRequests",
        _API_VERSIONS["pim_requests"],
        tenant_id=tenant_id,
        params={"$filter": "asRequestor()"},
    )


def activate_role(
    subscription_id: str,
    request_name: str,
    role_definition_id: str,
    principal_id: str,
    scope: str,
    justification: str,
    duration_hours: int,
    tenant_id: str = "",
) -> dict:
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
                "startDateTime": None,
                "expiration": {"type": "AfterDuration", "duration": f"PT{duration_hours}H"},
            },
            "justification": justification,
            "linkedRoleEligibilityScheduleId": None,
            "scope": scope,
        }
    }
    return _put(path, _API_VERSIONS["pim_requests"], body, tenant_id=tenant_id)


def get_role_assignment_request(
    subscription_id: str, request_name: str, tenant_id: str = ""
) -> dict:
    path = (
        f"/subscriptions/{subscription_id}/providers/Microsoft.Authorization"
        f"/roleAssignmentScheduleRequests/{request_name}"
    )
    return _get(path, _API_VERSIONS["pim_requests"], tenant_id=tenant_id)


# ── Resources ─────────────────────────────────────────────────────────────────

def list_resource_groups(subscription_id: str, tenant_id: str = "") -> list[dict]:
    return _paginate(
        f"/subscriptions/{subscription_id}/resourcegroups",
        _API_VERSIONS["resources"],
        tenant_id=tenant_id,
    )


def list_resources(subscription_id: str, tenant_id: str = "") -> list[dict]:
    return _paginate(
        f"/subscriptions/{subscription_id}/resources",
        _API_VERSIONS["resources"],
        tenant_id=tenant_id,
    )
