"""Snackbar-based toast notifications."""
from __future__ import annotations

import flet as ft
from app import theme


def show_toast(
    page: ft.Page,
    message: str,
    kind: str = "info",   # "info" | "success" | "warn" | "error"
    duration_ms: int = 4000,
) -> None:
    color_map = {
        "info": theme.ACCENT,
        "success": theme.SUCCESS,
        "warn": theme.WARN,
        "error": theme.ERROR,
    }
    bg = color_map.get(kind, theme.ACCENT)

    page.snack_bar = ft.SnackBar(
        content=ft.Text(message, color="#ffffff", size=theme.SIZE_BODY),
        bgcolor=bg,
        duration=duration_ms,
        behavior=ft.SnackBarBehavior.FLOATING,
    )
    page.snack_bar.open = True
    page.update()
