"""Landing / sign-in page."""

from __future__ import annotations

import asyncio
import contextlib

import flet as ft

from app import theme
from app.services import auth, az_cli
from app.state import state


def build(page: ft.Page, on_signed_in: callable) -> ft.View:
    """Return the /login view."""

    # ── Refs for dynamic elements ─────────────────────────────────────────────
    btn_ref = ft.Ref[ft.FilledButton]()
    status_ref = ft.Ref[ft.Text]()
    spinner_ref = ft.Ref[ft.ProgressRing]()
    error_ref = ft.Ref[ft.Container]()

    def _set_loading(loading: bool, message: str = "Complete sign-in in your browser…") -> None:
        btn_ref.current.disabled = loading
        spinner_ref.current.visible = loading
        status_ref.current.value = message if loading else ""
        status_ref.current.visible = loading
        error_ref.current.visible = False
        page.update()

    def _set_error(message: str, show_install_link: bool = False) -> None:
        btn_ref.current.disabled = False
        spinner_ref.current.visible = False
        status_ref.current.visible = False
        error_ref.current.content = ft.Column(
            [
                ft.Row(
                    [
                        ft.Icon(ft.Icons.ERROR_OUTLINE, color=theme.ERROR, size=16),
                        ft.Text(message, color=theme.ERROR, size=theme.SIZE_BODY, expand=True),
                    ],
                    spacing=theme.S2,
                ),
                ft.TextButton(
                    "Install Azure CLI →",
                    url="https://aka.ms/install-azure-cli",
                    visible=show_install_link,
                    style=ft.ButtonStyle(color=theme.ACCENT),
                ),
            ],
            spacing=theme.S1,
            tight=True,
        )
        error_ref.current.visible = True
        page.update()

    async def _do_login(_: ft.ControlEvent) -> None:
        _set_loading(True)
        try:
            if not await az_cli.check_az_installed():
                _set_error(
                    "Azure CLI not found. Please install it to continue.",
                    show_install_link=True,
                )
                return

            account_data = await az_cli.login()
            await auth.populate_identity(account_data)
            await auth.load_tenants_and_subscriptions()
            state.signed_in = True
            on_signed_in()
        except az_cli.AzNotInstalledError:
            _set_error(
                "Azure CLI not found. Please install it to continue.",
                show_install_link=True,
            )
        except az_cli.AzCliError as exc:
            msg = str(exc)
            if "cancel" in msg.lower() or "interrupt" in msg.lower():
                _set_error("Sign-in was cancelled.")
            else:
                _set_error(f"Sign-in failed: {msg}")
        except asyncio.CancelledError:
            _set_error("Sign-in was cancelled.")
        finally:
            # If we navigated away, btn_ref might be gone — guard
            with contextlib.suppress(Exception):
                _set_loading(False, "")

    # ── Layout ────────────────────────────────────────────────────────────────
    is_dark = state.dark_mode
    bg = theme.DARK_BG if is_dark else theme.LIGHT_BG
    surface = theme.DARK_SURFACE if is_dark else theme.LIGHT_SURFACE
    text = theme.DARK_TEXT if is_dark else theme.LIGHT_TEXT
    muted = theme.DARK_TEXT_MUTED if is_dark else theme.LIGHT_TEXT_MUTED

    card = ft.Container(
        content=ft.Column(
            [
                # Logo mark
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Icon(
                                ft.Icons.CLOUD_OUTLINED,
                                color=theme.ACCENT,
                                size=40,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                    margin=ft.margin.only(bottom=theme.S3),
                ),
                # App name
                ft.Text(
                    "BlueBridge",
                    size=theme.SIZE_HERO,
                    weight=ft.FontWeight.W_700,
                    color=text,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Text(
                    "Azure Navigator",
                    size=theme.SIZE_BODY,
                    color=muted,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Container(height=theme.S6),
                # Sign-in button
                ft.FilledButton(
                    ref=btn_ref,
                    text="Sign in with Microsoft",
                    icon=ft.Icons.LOGIN,
                    on_click=lambda e: asyncio.ensure_future(_do_login(e)),
                    style=ft.ButtonStyle(
                        bgcolor=theme.ACCENT,
                        color="#ffffff",
                        padding=ft.padding.symmetric(horizontal=theme.S6, vertical=theme.S3),
                        shape=ft.RoundedRectangleBorder(radius=theme.RADIUS_MD),
                    ),
                    width=260,
                ),
                # Spinner + status
                ft.Row(
                    [
                        ft.ProgressRing(
                            ref=spinner_ref,
                            width=16,
                            height=16,
                            stroke_width=2,
                            color=theme.ACCENT,
                            visible=False,
                        ),
                        ft.Text(
                            ref=status_ref,
                            value="",
                            color=muted,
                            size=theme.SIZE_SM,
                            visible=False,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                    spacing=theme.S2,
                ),
                # Error container
                ft.Container(
                    ref=error_ref,
                    visible=False,
                    padding=ft.padding.all(theme.S2),
                ),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=theme.S2,
        ),
        width=360,
        padding=ft.padding.all(theme.S8),
        bgcolor=surface,
        border_radius=theme.RADIUS_LG,
        shadow=ft.BoxShadow(
            spread_radius=0,
            blur_radius=40,
            color=ft.Colors.with_opacity(0.3, "#000000"),
            offset=ft.Offset(0, 8),
        ),
    )

    return ft.View(
        route="/login",
        controls=[
            ft.Container(
                content=card,
                expand=True,
                alignment=ft.alignment.center,
                bgcolor=bg,
                gradient=ft.LinearGradient(
                    begin=ft.alignment.top_left,
                    end=ft.alignment.bottom_right,
                    colors=[bg, theme.DARK_SURFACE if is_dark else theme.LIGHT_SURFACE2],
                ),
            )
        ],
        padding=0,
        bgcolor=bg,
    )
