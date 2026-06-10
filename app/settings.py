"""Persistent settings — stored in %APPDATA%/BlueBridge/settings.json."""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_APP_NAME = "BlueBridge"


def _settings_path() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / _APP_NAME / "settings.json"


def load() -> dict[str, Any]:
    path = _settings_path()
    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            log.warning("Failed to load settings: %s", exc)
    return {}


def save(data: dict[str, Any]) -> None:
    path = _settings_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as exc:
        log.warning("Failed to save settings: %s", exc)


def apply_to_state() -> None:
    """Load persisted settings into app state."""
    from app.state import state
    data = load()
    state.dark_mode = data.get("dark_mode", True)
    state.active_tenant_id = data.get("last_tenant") or None
    # Per-tenant last subscription
    last_subs = data.get("last_subscriptions", {})
    if state.active_tenant_id:
        state.selected_subscription_access = last_subs.get(state.active_tenant_id)
    state._refresh_interval_minutes = data.get("refresh_interval_minutes", 60)


def persist_from_state() -> None:
    """Save current app state into settings file."""
    from app.state import state
    data = load()
    data["dark_mode"] = state.dark_mode
    data["last_tenant"] = state.active_tenant_id
    last_subs = data.get("last_subscriptions", {})
    if state.active_tenant_id and state.selected_subscription_access:
        last_subs[state.active_tenant_id] = state.selected_subscription_access
    data["last_subscriptions"] = last_subs
    data["refresh_interval_minutes"] = getattr(state, "_refresh_interval_minutes", 60)
    save(data)
