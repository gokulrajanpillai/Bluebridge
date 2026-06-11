"""Async subprocess wrapper around the az CLI."""

from __future__ import annotations

import asyncio
import contextlib
import json
import shutil
import sys
from typing import Any


class AzCliError(Exception):
    """Raised when az CLI exits with a non-zero code or produces unexpected output."""

    def __init__(self, message: str, returncode: int = -1, stderr: str = "") -> None:
        super().__init__(message)
        self.returncode = returncode
        self.stderr = stderr


class AzNotInstalledError(AzCliError):
    """az CLI binary not found on PATH."""


async def _run(
    *args: str,
    timeout: float = 60.0,
    input_data: str | None = None,
) -> tuple[str, str]:
    """
    Run `az <args>` and return (stdout, stderr).
    Raises AzNotInstalledError if az is missing, AzCliError on non-zero exit.
    """
    az_bin = _find_az()
    if az_bin is None:
        raise AzNotInstalledError(
            "Azure CLI (az) not found on PATH. Install it from https://aka.ms/install-azure-cli"
        )

    cmd = [az_bin, *args, "--output", "json"]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.PIPE if input_data else None,
        )
        stdin_bytes = input_data.encode() if input_data else None
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(stdin_bytes), timeout=timeout
        )
    except TimeoutError:
        with contextlib.suppress(Exception):
            proc.kill()
        raise AzCliError(f"az {' '.join(args)} timed out after {timeout}s") from None
    except FileNotFoundError:
        raise AzNotInstalledError(
            "Azure CLI (az) not found on PATH. Install it from https://aka.ms/install-azure-cli"
        ) from None

    stdout = stdout_bytes.decode(errors="replace").strip()
    stderr = stderr_bytes.decode(errors="replace").strip()

    if proc.returncode != 0:
        # Surface the most useful part of the error message
        detail = _extract_error(stderr) or stderr or f"exit code {proc.returncode}"
        raise AzCliError(detail, returncode=proc.returncode or -1, stderr=stderr)

    return stdout, stderr


def _find_az() -> str | None:
    """Return the az binary path, handling Windows where it may be az.cmd."""
    if sys.platform == "win32":
        for name in ("az.cmd", "az.ps1", "az"):
            found = shutil.which(name)
            if found:
                return found
        return None
    return shutil.which("az")


def _extract_error(stderr: str) -> str:
    """Try to pull a human-readable error from az stderr JSON or plain text."""
    try:
        data = json.loads(stderr)
        return data.get("error", {}).get("message") or data.get("message") or ""
    except Exception:
        # Return first non-empty line
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


async def check_az_installed() -> bool:
    """Return True if az CLI is available, False otherwise (no exception)."""
    return _find_az() is not None


async def get_account() -> dict[str, Any] | None:
    """
    Return the current account info dict (from `az account show`), or None if
    not logged in.
    """
    try:
        stdout, _ = await _run("account", "show", timeout=10.0)
        return _parse_json(stdout)
    except AzCliError:
        return None


async def list_accounts() -> list[dict[str, Any]]:
    """Return all subscriptions visible to the current credential."""
    stdout, _ = await _run("account", "list", "--all", timeout=30.0)
    result = _parse_json(stdout)
    return result if isinstance(result, list) else []


async def list_tenants() -> list[dict[str, Any]]:
    """Return all tenants the current credential has access to."""
    try:
        stdout, _ = await _run("account", "tenant", "list", timeout=30.0)
        result = _parse_json(stdout)
        return result if isinstance(result, list) else []
    except AzCliError:
        # Fallback: derive tenants from account list
        accounts = await list_accounts()
        seen: dict[str, dict] = {}
        for acc in accounts:
            tid = acc.get("tenantId") or acc.get("homeTenantId", "")
            if tid and tid not in seen:
                seen[tid] = {
                    "tenantId": tid,
                    "displayName": acc.get("tenantDisplayName") or tid,
                }
        return list(seen.values())


async def login(tenant_id: str | None = None) -> dict[str, Any]:
    """
    Run `az login [--tenant <id>]`, opening the system browser for SSO.
    Returns the first account dict from the result list.
    Timeout is long (5 min) to allow the user to complete browser flow.
    """
    args = ["login"]
    if tenant_id:
        args += ["--tenant", tenant_id]
    stdout, _ = await _run(*args, timeout=300.0)
    result = _parse_json(stdout)
    if isinstance(result, list) and result:
        return result[0]
    if isinstance(result, dict):
        return result
    raise AzCliError("az login returned unexpected output")


async def logout() -> None:
    """Sign out the current credential."""
    with contextlib.suppress(AzCliError):
        await _run("logout", timeout=15.0)


async def get_access_token(
    resource: str = "https://management.azure.com/",
    tenant_id: str | None = None,
) -> dict[str, Any]:
    """
    Return a token dict with keys: accessToken, expiresOn, subscription, tenant, tokenType.
    Uses `az account get-access-token`.
    """
    args = ["account", "get-access-token", "--resource", resource]
    if tenant_id:
        args += ["--tenant", tenant_id]
    stdout, _ = await _run(*args, timeout=30.0)
    result = _parse_json(stdout)
    if not result or "accessToken" not in result:
        raise AzCliError("get-access-token returned no token")
    return result


async def set_active_subscription(subscription_id: str) -> None:
    """Set the active subscription for the az CLI context."""
    await _run("account", "set", "--subscription", subscription_id, timeout=15.0)
