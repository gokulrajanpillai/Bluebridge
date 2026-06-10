"""BlueBridge — Azure Navigator. Flet entry point."""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

import flet as ft

from app import theme, settings as app_settings
from app.services import az_cli, auth
from app.state import state

# ── Logging ──────────────────────────────────────────────────────────────────
_log_dir = Path(
    __import__("os").environ.get(
        "APPDATA" if sys.platform == "win32" else "XDG_CONFIG_HOME",
        Path.home() / ("AppData/Roaming" if sys.platform == "win32" else ".config"),
    )
) / "BlueBridge"
_log_dir.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(_log_dir / "bluebridge.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("bluebridge")


async def main(page: ft.Page) -> None:
    # ── Load persisted settings ────────────────────────────────────────────────
    app_settings.apply_to_state()

    # ── Window setup ──────────────────────────────────────────────────────────
    page.title = "BlueBridge"
    page.window.width = 1280
    page.window.height = 820
    page.window.min_width = 900
    page.window.min_height = 600
    page.window.center()

    # ── Theme ─────────────────────────────────────────────────────────────────
    page.theme = theme.DARK_THEME
    page.dark_theme = theme.DARK_THEME
    page.theme_mode = ft.ThemeMode.DARK if state.dark_mode else ft.ThemeMode.LIGHT

    # ── Fonts ─────────────────────────────────────────────────────────────────
    assets_dir = Path(__file__).parent / "assets" / "fonts"
    if (assets_dir / "Inter-Regular.ttf").exists():
        page.fonts = {
            "Inter": str(assets_dir / "Inter-Regular.ttf"),
            "Inter Medium": str(assets_dir / "Inter-Medium.ttf"),
            "Inter SemiBold": str(assets_dir / "Inter-SemiBold.ttf"),
            "Inter Bold": str(assets_dir / "Inter-Bold.ttf"),
        }

    page.padding = 0
    page.spacing = 0

    # ── Global exception handler ──────────────────────────────────────────────
    def _on_error(e: ft.PageErrorEvent) -> None:
        log.error("Unhandled page error: %s", e.message)
        from app.components.toast import show_toast
        show_toast(page, f"Unexpected error: {e.message}", "error")

    page.on_error = _on_error

    # ── Persist settings on close ─────────────────────────────────────────────
    def _on_window_event(e: ft.WindowEvent) -> None:
        if e.type == ft.WindowEventType.CLOSE:
            app_settings.persist_from_state()

    page.window.on_event = _on_window_event

    # ── Routing ───────────────────────────────────────────────────────────────
    def route_to_app() -> None:
        page.go("/app")

    def route_to_login() -> None:
        app_settings.persist_from_state()
        page.go("/login")

    async def _check_existing_login() -> None:
        if not await az_cli.check_az_installed():
            route_to_login()
            return
        account = await az_cli.get_account()
        if account:
            try:
                await auth.populate_identity(account)
                await auth.load_tenants_and_subscriptions()
                state.signed_in = True
                route_to_app()
            except Exception as exc:
                log.warning("Auto-login check failed: %s", exc)
                route_to_login()
        else:
            route_to_login()

    def on_route_change(e: ft.RouteChangeEvent) -> None:
        page.views.clear()

        if page.route == "/login":
            from app.views.landing import build as build_landing
            page.views.append(build_landing(page, on_signed_in=route_to_app))

        elif page.route == "/app":
            from app.views.shell import build as build_shell
            page.views.append(build_shell(page, on_sign_out=route_to_login))
            _start_auto_refresh()

        else:
            page.go("/login")
            return

        page.update()

    def on_view_pop(e: ft.ViewPopEvent) -> None:
        page.views.pop()
        top = page.views[-1] if page.views else None
        if top:
            page.go(top.route)

    page.on_route_change = on_route_change
    page.on_view_pop = on_view_pop

    # ── Auto-refresh timer ────────────────────────────────────────────────────
    _refresh_task: asyncio.Task | None = None

    def _start_auto_refresh() -> None:
        nonlocal _refresh_task
        if _refresh_task and not _refresh_task.done():
            return
        _refresh_task = asyncio.ensure_future(_auto_refresh_loop())
        state.track_task(_refresh_task)

    async def _auto_refresh_loop() -> None:
        interval = getattr(state, "_refresh_interval_minutes", 60) * 60
        while state.signed_in:
            await asyncio.sleep(interval)
            if not state.signed_in:
                break
            log.info("Auto-refresh triggered")
            try:
                await auth.load_tenants_and_subscriptions()
                page.pubsub.send_all("refresh")
            except Exception as exc:
                log.warning("Auto-refresh failed: %s", exc)

    page.go("/login")
    asyncio.ensure_future(_check_existing_login())


def run() -> None:
    ft.app(target=main, assets_dir="assets")


if __name__ == "__main__":
    run()
