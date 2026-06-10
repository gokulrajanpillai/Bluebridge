"""App shell — placeholder until Phase 2."""
from __future__ import annotations

import flet as ft
from app import theme
from app.state import state


def build(page: ft.Page, on_sign_out: callable) -> ft.View:
    """Return the /app shell view. Full implementation in Phase 2."""
    is_dark = state.dark_mode
    bg = theme.DARK_BG if is_dark else theme.LIGHT_BG
    text = theme.DARK_TEXT if is_dark else theme.LIGHT_TEXT

    return ft.View(
        route="/app",
        controls=[
            ft.Container(
                content=ft.Column(
                    [
                        ft.Text("BlueBridge", size=theme.SIZE_HERO, color=text, weight=ft.FontWeight.W_700),
                        ft.Text(
                            f"Signed in as {state.account_upn}",
                            color=theme.DARK_TEXT_MUTED if is_dark else theme.LIGHT_TEXT_MUTED,
                        ),
                        ft.Text(
                            "Shell coming in Phase 2…",
                            color=theme.DARK_TEXT_MUTED if is_dark else theme.LIGHT_TEXT_MUTED,
                        ),
                        ft.OutlinedButton("Sign out", on_click=lambda _: on_sign_out()),
                    ],
                    spacing=theme.S3,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                expand=True,
                alignment=ft.alignment.center,
                bgcolor=bg,
            )
        ],
        padding=0,
        bgcolor=bg,
    )
