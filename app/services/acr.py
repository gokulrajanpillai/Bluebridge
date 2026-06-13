"""Azure Container Registry — list repositories and tags via OCI Distribution API."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.services import arm
from app.services.auth import get_token
from app.services.logs import PermissionDeniedError

log = logging.getLogger(__name__)

_EXCHANGE_URL = "https://{login_server}/oauth2/exchange"
_OAUTH_TOKEN_URL = "https://{login_server}/oauth2/token"  # noqa: S105
_CATALOG_URL = "https://{login_server}/v2/_catalog"
_TAGS_URL = "https://{login_server}/v2/{repo}/tags/list"
_MANIFEST_URL = "https://{login_server}/v2/{repo}/manifests/{ref}"


def _acr_token(login_server: str, scope: str, tenant_id: str = "") -> str:
    """Exchange an ARM bearer token for an ACR-scoped access token."""
    arm_token = get_token(tenant_id=tenant_id)

    # Step 1 — ARM → ACR refresh token
    exch = httpx.post(
        _EXCHANGE_URL.format(login_server=login_server),
        data={
            "grant_type": "access_token",
            "service": login_server,
            "access_token": arm_token,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30.0,
        follow_redirects=True,
    )
    if exch.status_code == 401:
        raise PermissionDeniedError(
            "authenticate to registry",
            "AcrPull or AcrPush on the registry",
        )
    exch.raise_for_status()
    refresh_token = exch.json().get("refresh_token", "")

    # Step 2 — refresh token → scoped access token
    tok = httpx.post(
        _OAUTH_TOKEN_URL.format(login_server=login_server),
        data={
            "grant_type": "refresh_token",
            "service": login_server,
            "scope": scope,
            "refresh_token": refresh_token,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30.0,
        follow_redirects=True,
    )
    tok.raise_for_status()
    return tok.json().get("access_token", "")


def get_login_server(
    subscription_id: str,
    resource_group: str,
    registry_name: str,
    tenant_id: str = "",
) -> str:
    """Return the loginServer FQDN for a registry (e.g. myregistry.azurecr.io)."""
    data: dict[str, Any] = arm._get(
        f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
        f"/providers/Microsoft.ContainerRegistry/registries/{registry_name}",
        "2023-01-01-preview",
        tenant_id=tenant_id,
    )
    return data.get("properties", {}).get("loginServer", f"{registry_name}.azurecr.io")


def list_repositories(login_server: str, tenant_id: str = "") -> list[str]:
    token = _acr_token(login_server, "registry:catalog:*", tenant_id)
    resp = httpx.get(
        _CATALOG_URL.format(login_server=login_server),
        headers={"Authorization": f"Bearer {token}"},
        timeout=30.0,
        follow_redirects=True,
    )
    if resp.status_code == 401:
        raise PermissionDeniedError("list repositories", "AcrPull on the registry")
    resp.raise_for_status()
    return resp.json().get("repositories", [])


def list_tags(login_server: str, repo: str, tenant_id: str = "") -> list[str]:
    token = _acr_token(
        login_server, f"repository:{repo}:pull", tenant_id
    )
    resp = httpx.get(
        _TAGS_URL.format(login_server=login_server, repo=repo),
        headers={"Authorization": f"Bearer {token}"},
        timeout=30.0,
        follow_redirects=True,
    )
    if resp.status_code == 401:
        raise PermissionDeniedError("list tags", "AcrPull on the registry")
    resp.raise_for_status()
    return sorted(resp.json().get("tags", []) or [], reverse=True)


def get_manifest(
    login_server: str,
    repo: str,
    ref: str,
    tenant_id: str = "",
) -> dict[str, Any]:
    token = _acr_token(login_server, f"repository:{repo}:pull", tenant_id)
    resp = httpx.get(
        _MANIFEST_URL.format(login_server=login_server, repo=repo, ref=ref),
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.docker.distribution.manifest.v2+json",
        },
        timeout=30.0,
        follow_redirects=True,
    )
    resp.raise_for_status()
    return resp.json()
