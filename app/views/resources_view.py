"""Resources tab — Phase 4 placeholder."""
from __future__ import annotations

import flet as ft
from app import theme
from app.state import state


def build(page: ft.Page) -> ft.Control:
    is_dark = state.dark_mode
    muted = theme.DARK_TEXT_MUTED if is_dark else theme.LIGHT_TEXT_MUTED

    return ft.Container(
        content=ft.Column(
            [
                ft.Icon(ft.Icons.FOLDER_OUTLINED, color=muted, size=40),
                ft.Text("Resources tab — coming in Phase 4", color=muted, size=theme.SIZE_BODY),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=theme.S3,
        ),
        expand=True,
        alignment=ft.alignment.center,
    )
