"""Synchronous subprocess wrapper around the az CLI."""

from __future__ import annotations

import contextlib
import json
import shutil
import subprocess
import sys
from typing import Any


class AzCliError(Exception):
    def __init__(self, message: str, returncode: int = -1, stderr: str = "") -> None:
        super().__init__(message)
        self.returncode = returncode
        self.stderr = stderr


class AzNotInstalledError(AzCliError):
    """az CLI binary not found on PATH."""


def _find_az() -> str | None:
    if sys.platform == "win32":
        for name in ("az.cmd", "az.ps1", "az"):
            found = shutil.which(name)
            if found:
                return found
        return None
    return shutil.which("az")


def _run(*args: str, timeout: float = 60.0, input_data: str | None = None) -> tuple[str, str]:
    az_bin = _find_az()
    if az_bin is None:
        raise AzNotInstalledError(
            "Azure CLI (az) not found on PATH. Install it from https://aka.ms/install-azure-cli"
        )
    cmd = [az_bin, *args, "--output", "json"]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            input=input_data,
        )
    except FileNotFoundError:
        raise AzNotInstalledError(
            "Azure CLI (az) not found on PATH. Install it from https://aka.ms/install-azure-cli"
        ) from None
    except subprocess.TimeoutExpired:
        raise AzCliError(f"az {' '.join(args)} timed out after {timeout}s") from None

    if result.returncode != 0:
        detail = _extract_error(result.stderr) or result.stderr or f"exit code {result.returncode}"
        raise AzCliError(detail, returncode=result.returncode, stderr=result.stderr)

    return result.stdout.strip(), result.stderr.strip()


def _extract_error(stderr: str) -> str:
    try:
        data = json.loads(stderr)
        return data.get("error", {}).get("message") or data.get("message") or ""
    except Exception:
        for line in stderr.splitlines():
            line = line.strip()
            if line and not line.startswith("WARNING"):
                return line
        return ""


def _parse_json(raw: str) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AzCliError(f"Failed to parse az output as JSON: {exc}\nOutput: {raw[:500]}") from exc


# ── Public API ────────────────────────────────────────────────────────────────

def check_az_installed() -> bool:
    return _find_az() is not None


def get_account() -> dict[str, Any] | None:
    try:
        stdout, _ = _run("account", "show", timeout=10.0)
        return _parse_json(stdout)
    except AzCliError:
        return None


def list_accounts() -> list[dict[str, Any]]:
    stdout, _ = _run("account", "list", "--all", timeout=30.0)
    result = _parse_json(stdout)
    return result if isinstance(result, list) else []


def list_tenants() -> list[dict[str, Any]]:
    try:
        stdout, _ = _run("account", "tenant", "list", timeout=30.0)
        result = _parse_json(stdout)
        return result if isinstance(result, list) else []
    except AzCliError:
        accounts = list_accounts()
        seen: dict[str, dict] = {}
        for acc in accounts:
            tid = acc.get("tenantId") or acc.get("homeTenantId", "")
            if tid and tid not in seen:
                seen[tid] = {
                    "tenantId": tid,
                    "displayName": acc.get("tenantDisplayName") or tid,
                }
        return list(seen.values())


def login(tenant_id: str | None = None) -> dict[str, Any]:
    """Open the system browser for Azure SSO. Returns first account dict."""
    args = ["login"]
    if tenant_id:
        args += ["--tenant", tenant_id]
    stdout, _ = _run(*args, timeout=300.0)
    result = _parse_json(stdout)
    if isinstance(result, list) and result:
        return result[0]
    if isinstance(result, dict):
        return result
    raise AzCliError("az login returned unexpected output")


def logout() -> None:
    with contextlib.suppress(AzCliError):
        _run("logout", timeout=15.0)


def get_access_token(
    resource: str = "https://management.azure.com/",
    tenant_id: str | None = None,
) -> dict[str, Any]:
    args = ["account", "get-access-token", "--resource", resource]
    if tenant_id:
        args += ["--tenant", tenant_id]
    stdout, _ = _run(*args, timeout=30.0)
    result = _parse_json(stdout)
    if not result or "accessToken" not in result:
        raise AzCliError("get-access-token returned no token")
    return result
