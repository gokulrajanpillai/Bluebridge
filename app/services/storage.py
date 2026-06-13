"""Azure Blob Storage — list containers, browse blobs, download via data-plane REST."""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from typing import Any

import httpx

from app.services.auth import get_token
from app.services.logs import PermissionDeniedError

log = logging.getLogger(__name__)

_STORAGE_SCOPE = "https://storage.azure.com/"
_API_VERSION = "2020-10-02"


def _hdrs(tenant_id: str = "") -> dict[str, str]:
    token = get_token(resource=_STORAGE_SCOPE, tenant_id=tenant_id)
    return {
        "Authorization": f"Bearer {token}",
        "x-ms-version": _API_VERSION,
    }


def _check(resp: httpx.Response, operation: str, required_role: str) -> None:
    if resp.status_code == 403:
        raise PermissionDeniedError(operation, required_role)
    if resp.status_code == 401:
        raise PermissionDeniedError(
            operation,
            "Storage Blob Data Reader (data-plane RBAC required, not just management access)",
        )
    resp.raise_for_status()


# ── Containers ────────────────────────────────────────────────────────────────

def list_containers(account_name: str, tenant_id: str = "") -> list[dict[str, Any]]:
    """List all blob containers in *account_name*."""
    url = f"https://{account_name}.blob.core.windows.net/"
    resp = httpx.get(
        url, headers=_hdrs(tenant_id), params={"comp": "list"}, timeout=30.0
    )
    _check(resp, "list containers", "Storage Blob Data Reader")

    root = ET.fromstring(resp.text)  # noqa: S314
    containers = []
    for c in root.findall(".//Container"):
        containers.append({
            "name": c.findtext("Name") or "",
            "last_modified": c.findtext("Properties/Last-Modified") or "",
            "lease_state": c.findtext("Properties/LeaseState") or "",
        })
    return containers


# ── Blobs ─────────────────────────────────────────────────────────────────────

def list_blobs(
    account_name: str,
    container_name: str,
    prefix: str = "",
    delimiter: str = "/",
    tenant_id: str = "",
) -> dict[str, list]:
    """List blobs and virtual directories. Returns {"blobs": [...], "prefixes": [...]}."""
    url = f"https://{account_name}.blob.core.windows.net/{container_name}"
    params: dict[str, str] = {"restype": "container", "comp": "list"}
    if prefix:
        params["prefix"] = prefix
    if delimiter:
        params["delimiter"] = delimiter

    resp = httpx.get(url, headers=_hdrs(tenant_id), params=params, timeout=30.0)
    _check(resp, "list blobs", "Storage Blob Data Reader")

    root = ET.fromstring(resp.text)  # noqa: S314
    blobs = []
    for b in root.findall(".//Blob"):
        size_raw = b.findtext("Properties/Content-Length") or "0"
        blobs.append({
            "name": b.findtext("Name") or "",
            "size": int(size_raw) if size_raw.isdigit() else 0,
            "last_modified": b.findtext("Properties/Last-Modified") or "",
            "content_type": b.findtext("Properties/Content-Type") or "",
        })
    prefixes = [p.findtext("Name") or "" for p in root.findall(".//BlobPrefix")]
    return {"blobs": blobs, "prefixes": prefixes}


def download_blob(
    account_name: str,
    container_name: str,
    blob_name: str,
    tenant_id: str = "",
) -> bytes:
    """Download blob content as bytes."""
    url = f"https://{account_name}.blob.core.windows.net/{container_name}/{blob_name}"
    resp = httpx.get(url, headers=_hdrs(tenant_id), timeout=120.0, follow_redirects=True)
    _check(resp, f"download blob {blob_name}", "Storage Blob Data Reader")
    return resp.content


def _fmt_size(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size = int(size / 1024)
    return f"{size:.1f} TB"
