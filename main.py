"""BlueBridge — Azure Navigator. Flet entry point."""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

import flet as ft

from app import theme
from app.services import az_cli, auth
from app.state import state

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("bluebridge")


async def main(page: ft.Page) -> None:
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
    # Flet bundles its own font fallbacks; Inter is loaded if assets/fonts exist.
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

    # ── Routing ───────────────────────────────────────────────────────────────
    def route_to_app() -> None:
        page.go("/app")

    def route_to_login() -> None:
        page.go("/login")

    async def _check_existing_login() -> None:
        """On launch: if already signed in, skip login page."""
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

    # Start at login by default; _check_existing_login will redirect if needed
    page.go("/login")

    # Check for existing login in background so the landing page renders first
    asyncio.ensure_future(_check_existing_login())


def run() -> None:
    ft.app(target=main, assets_dir="assets")


if __name__ == "__main__":
    run()
