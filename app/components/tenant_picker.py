"""Tenant switcher dropdown for the app bar."""
from __future__ import annotations

import asyncio
from typing import Callable

import flet as ft

from app import theme
from app.state import state


def build(
    page: ft.Page,
    on_tenant_changed: Callable[[str], None],
) -> ft.Dropdown:
    """Return a Dropdown populated with available tenants."""

    def _make_options() -> list[ft.dropdown.Option]:
        opts = []
        for t in state.tenants:
            tid = t.get("tenantId", "")
            name = t.get("displayName") or tid
            opts.append(ft.dropdown.Option(key=tid, text=name))
        return opts

    def _on_change(e: ft.ControlEvent) -> None:
        if e.control.value and e.control.value != state.active_tenant_id:
            on_tenant_changed(e.control.value)

    dd = ft.Dropdown(
        options=_make_options(),
        value=state.active_tenant_id,
        on_change=_on_change,
        dense=True,
        border_color=theme.DARK_BORDER,
        focused_border_color=theme.ACCENT,
        text_style=ft.TextStyle(size=theme.SIZE_SM, color=theme.DARK_TEXT),
        width=200,
        content_padding=ft.padding.symmetric(horizontal=theme.S3, vertical=theme.S1),
    )
    return dd
