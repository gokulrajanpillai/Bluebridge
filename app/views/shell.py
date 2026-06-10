"""App shell — top bar, tenant switcher, tabs, status bar."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Callable

import flet as ft

from app import theme
from app.components.toast import show_toast
from app.services import auth, az_cli
from app.state import state

log = logging.getLogger(__name__)


def build(page: ft.Page, on_sign_out: Callable[[], None]) -> ft.View:
    is_dark = state.dark_mode
    bg = theme.DARK_BG if is_dark else theme.LIGHT_BG
    surface = theme.DARK_SURFACE if is_dark else theme.LIGHT_SURFACE
    surface2 = theme.DARK_SURFACE2 if is_dark else theme.LIGHT_SURFACE2
    border = theme.DARK_BORDER if is_dark else theme.LIGHT_BORDER
    text = theme.DARK_TEXT if is_dark else theme.LIGHT_TEXT
    muted = theme.DARK_TEXT_MUTED if is_dark else theme.LIGHT_TEXT_MUTED

    # ── Refs ─────────────────────────────────────────────────────────────────
    last_updated_ref = ft.Ref[ft.Text]()
    progress_ref = ft.Ref[ft.ProgressBar]()
    status_bar_ref = ft.Ref[ft.Text]()
    tenant_dd_ref = ft.Ref[ft.Dropdown]()
    theme_icon_ref = ft.Ref[ft.IconButton]()

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _now_str() -> str:
        return datetime.now(timezone.utc).strftime("%H:%M:%S")

    def _set_progress(visible: bool) -> None:
        progress_ref.current.visible = visible
        page.update()

    def _update_last_refreshed() -> None:
        ts = _now_str()
        state.last_refreshed = ts
        last_updated_ref.current.value = f"Updated {ts}"
        page.update()

    # ── Tenant switching ──────────────────────────────────────────────────────
    async def _do_switch_tenant(tenant_id: str) -> None:
        from app import settings as app_settings
        _set_progress(True)
        try:
            await auth.switch_tenant(tenant_id)
            tenant_dd_ref.current.options = _make_tenant_options()
            tenant_dd_ref.current.value = state.active_tenant_id
            _update_last_refreshed()
            app_settings.persist_from_state()
            show_toast(page, f"Switched to {state.active_tenant_name}", "success")
        except Exception as exc:
            log.exception("Tenant switch failed")
            show_toast(page, f"Tenant switch failed: {exc}", "error")
        finally:
            _set_progress(False)

    def on_tenant_changed(tenant_id: str) -> None:
        asyncio.ensure_future(_do_switch_tenant(tenant_id))

    def _make_tenant_options() -> list[ft.dropdown.Option]:
        opts = []
        for t in state.tenants:
            tid = t.get("tenantId", "")
            name = t.get("displayName") or tid
            opts.append(ft.dropdown.Option(key=tid, text=name))
        return opts

    # ── Sign out ──────────────────────────────────────────────────────────────
    async def _do_sign_out(_: ft.ControlEvent) -> None:
        try:
            await az_cli.logout()
        except Exception:
            pass
        state.clear_for_signout()
        on_sign_out()

    # ── Theme toggle ──────────────────────────────────────────────────────────
    def _toggle_theme(_: ft.ControlEvent) -> None:
        from app import settings as app_settings
        state.dark_mode = not state.dark_mode
        if state.dark_mode:
            page.theme_mode = ft.ThemeMode.DARK
            theme_icon_ref.current.icon = ft.Icons.LIGHT_MODE_OUTLINED
        else:
            page.theme_mode = ft.ThemeMode.LIGHT
            theme_icon_ref.current.icon = ft.Icons.DARK_MODE_OUTLINED
        app_settings.persist_from_state()
        page.update()

    # ── Refresh ───────────────────────────────────────────────────────────────
    async def _do_refresh(_: ft.ControlEvent) -> None:
        _set_progress(True)
        try:
            await auth.load_tenants_and_subscriptions()
            tenant_dd_ref.current.options = _make_tenant_options()
            tenant_dd_ref.current.value = state.active_tenant_id
            _update_last_refreshed()
            # Signal tabs to reload (Phase 3/4 will hook into this)
            page.pubsub.send_all("refresh")
        except Exception as exc:
            log.exception("Refresh failed")
            show_toast(page, f"Refresh failed: {exc}", "error")
        finally:
            _set_progress(False)

    # ── App bar ───────────────────────────────────────────────────────────────
    tenant_dropdown = ft.Dropdown(
        ref=tenant_dd_ref,
        options=_make_tenant_options(),
        value=state.active_tenant_id,
        on_change=lambda e: on_tenant_changed(e.control.value) if e.control.value else None,
        dense=True,
        border_color=border,
        focused_border_color=theme.ACCENT,
        text_style=ft.TextStyle(size=theme.SIZE_SM, color=text),
        width=210,
        content_padding=ft.padding.symmetric(horizontal=theme.S2, vertical=0),
        hint_text="Select tenant",
        hint_style=ft.TextStyle(size=theme.SIZE_SM, color=muted),
    )

    identity_row = ft.Row(
        [
            ft.Container(
                width=8,
                height=8,
                border_radius=4,
                bgcolor=theme.SUCCESS,
                tooltip="Signed in",
            ),
            ft.Text(
                state.account_upn or state.account_name or "—",
                size=theme.SIZE_SM,
                color=muted,
                max_lines=1,
                overflow=ft.TextOverflow.ELLIPSIS,
                width=180,
            ),
        ],
        spacing=theme.S1,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    app_bar_left = ft.Row(
        [
            ft.Icon(ft.Icons.CLOUD_OUTLINED, color=theme.ACCENT, size=22),
            ft.Text(
                "BlueBridge",
                size=theme.SIZE_BODY,
                weight=ft.FontWeight.W_600,
                color=text,
            ),
            ft.VerticalDivider(width=1, color=border),
            tenant_dropdown,
            identity_row,
        ],
        spacing=theme.S3,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    app_bar_right = ft.Row(
        [
            ft.Text(
                ref=last_updated_ref,
                value=f"Updated {state.last_refreshed or _now_str()}",
                size=theme.SIZE_XS,
                color=muted,
            ),
            ft.IconButton(
                icon=ft.Icons.REFRESH_OUTLINED,
                icon_color=muted,
                icon_size=18,
                tooltip="Refresh (Ctrl+R)",
                on_click=lambda e: asyncio.ensure_future(_do_refresh(e)),
            ),
            ft.IconButton(
                ref=theme_icon_ref,
                icon=ft.Icons.LIGHT_MODE_OUTLINED if is_dark else ft.Icons.DARK_MODE_OUTLINED,
                icon_color=muted,
                icon_size=18,
                tooltip="Toggle theme",
                on_click=_toggle_theme,
            ),
            ft.IconButton(
                icon=ft.Icons.LOGOUT_OUTLINED,
                icon_color=muted,
                icon_size=18,
                tooltip="Sign out",
                on_click=lambda e: asyncio.ensure_future(_do_sign_out(e)),
            ),
        ],
        spacing=0,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    app_bar_row = ft.Container(
        content=ft.Row(
            [app_bar_left, ft.Container(expand=True), app_bar_right],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        bgcolor=surface,
        padding=ft.padding.symmetric(horizontal=theme.S4, vertical=theme.S2),
        border=ft.border.only(bottom=ft.BorderSide(1, border)),
        height=52,
    )

    progress_bar = ft.ProgressBar(
        ref=progress_ref,
        color=theme.ACCENT,
        bgcolor="transparent",
        height=2,
        visible=False,
    )

    # ── Tabs ─────────────────────────────────────────────────────────────────
    from app.views.access_view import build as build_access
    from app.views.resources_view import build as build_resources

    access_content = build_access(page)
    resources_content = build_resources(page)

    tab_bar = ft.Tabs(
        selected_index=0,
        animation_duration=200,
        tab_alignment=ft.TabAlignment.START,
        indicator_color=theme.ACCENT,
        indicator_tab_size=True,
        label_color=text,
        unselected_label_color=muted,
        divider_color=border,
        tabs=[
            ft.Tab(
                text="Access",
                icon=ft.Icons.LOCK_OUTLINED,
                content=ft.Container(content=access_content, expand=True, bgcolor=bg),
            ),
            ft.Tab(
                text="Resources",
                icon=ft.Icons.FOLDER_OUTLINED,
                content=ft.Container(content=resources_content, expand=True, bgcolor=bg),
            ),
        ],
        expand=True,
    )

    # ── Status bar ────────────────────────────────────────────────────────────
    sub_count = len(state.subscriptions)
    status_bar = ft.Container(
        content=ft.Row(
            [
                ft.Text(
                    ref=status_bar_ref,
                    value=f"{sub_count} subscription{'s' if sub_count != 1 else ''}  ·  {state.active_tenant_name or '—'}",
                    size=theme.SIZE_XS,
                    color=muted,
                ),
            ],
        ),
        bgcolor=surface2,
        padding=ft.padding.symmetric(horizontal=theme.S4, vertical=theme.S1),
        border=ft.border.only(top=ft.BorderSide(1, border)),
        height=26,
    )

    # ── Keyboard shortcuts ────────────────────────────────────────────────────
    def on_keyboard(e: ft.KeyboardEvent) -> None:
        if e.ctrl and e.key == "R":
            asyncio.ensure_future(_do_refresh(None))

    page.on_keyboard_event = on_keyboard

    # ── View ─────────────────────────────────────────────────────────────────
    return ft.View(
        route="/app",
        controls=[
            ft.Column(
                [
                    app_bar_row,
                    progress_bar,
                    ft.Container(content=tab_bar, expand=True, bgcolor=bg),
                    status_bar,
                ],
                spacing=0,
                expand=True,
            )
        ],
        padding=0,
        bgcolor=bg,
    )
