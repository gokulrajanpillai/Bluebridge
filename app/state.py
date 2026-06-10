"""App-wide mutable state. One instance lives for the lifetime of the process."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AppState:
    # ── Auth / identity ───────────────────────────────────────────────────────
    signed_in: bool = False
    active_tenant_id: str | None = None
    active_tenant_name: str | None = None
    account_name: str | None = None       # display name
    account_upn: str | None = None        # user principal name
    account_id: str | None = None         # object id

    # ── Subscriptions ─────────────────────────────────────────────────────────
    tenants: list[dict[str, Any]] = field(default_factory=list)
    subscriptions: list[dict[str, Any]] = field(default_factory=list)

    # Access tab
    selected_subscription_access: str | None = None
    # Resources tab
    selected_subscription_resources: str | None = None

    # ── Token cache  { (tenant_id, resource) -> {token, expires_on} } ─────────
    _token_cache: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)

    # ── Data caches ───────────────────────────────────────────────────────────
    # PIM data: { tenant_id -> { "eligible": [...], "active": [...], "pending": [...] } }
    pim_cache: dict[str, dict[str, list]] = field(default_factory=dict)
    # Resources cache: { (tenant_id, sub_id) -> { "rgs": [...], "resources": [...] } }
    resource_cache: dict[tuple[str, str], dict[str, list]] = field(default_factory=dict)

    # ── UI ─────────────────────────────────────────────────────────────────────
    dark_mode: bool = True
    last_refreshed: str | None = None     # HH:MM:SS string

    # ── Background task handles (to cancel on sign-out / tenant switch) ────────
    _bg_tasks: list[asyncio.Task] = field(default_factory=list)

    def clear_for_signout(self) -> None:
        self.signed_in = False
        self.active_tenant_id = None
        self.active_tenant_name = None
        self.account_name = None
        self.account_upn = None
        self.account_id = None
        self.tenants.clear()
        self.subscriptions.clear()
        self.selected_subscription_access = None
        self.selected_subscription_resources = None
        self._token_cache.clear()
        self.pim_cache.clear()
        self.resource_cache.clear()
        self._cancel_bg_tasks()

    def clear_caches_for_tenant(self, tenant_id: str) -> None:
        self._token_cache = {
            k: v for k, v in self._token_cache.items() if k[0] != tenant_id
        }
        self.pim_cache.pop(tenant_id, None)
        keys = [k for k in self.resource_cache if k[0] == tenant_id]
        for k in keys:
            del self.resource_cache[k]

    def _cancel_bg_tasks(self) -> None:
        for t in self._bg_tasks:
            t.cancel()
        self._bg_tasks.clear()

    def track_task(self, task: asyncio.Task) -> None:
        self._bg_tasks.append(task)
        task.add_done_callback(lambda t: self._bg_tasks.remove(t) if t in self._bg_tasks else None)


# Singleton
state = AppState()
