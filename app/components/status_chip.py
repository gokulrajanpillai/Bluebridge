"""Status pill chip for PIM role states."""
from __future__ import annotations

import flet as ft
from app import theme

_CONFIG = {
    "Active":          (theme.SUCCESS,  ft.Icons.CHECK_CIRCLE_OUTLINE),
    "Eligible":        (theme.ACCENT,   ft.Icons.CIRCLE_OUTLINED),
    "PendingApproval": (theme.WARN,     ft.Icons.HOURGLASS_EMPTY_OUTLINED),
    "Provisioning":    (theme.WARN,     ft.Icons.SYNC_OUTLINED),
    "Denied":          (theme.ERROR,    ft.Icons.CANCEL_OUTLINED),
    "Failed":          (theme.ERROR,    ft.Icons.ERROR_OUTLINE),
    "Expired":         (theme.DARK_TEXT_MUTED, ft.Icons.TIMER_OFF_OUTLINED),
}


def build(status: str) -> ft.Container:
    color, icon = _CONFIG.get(status, (theme.DARK_TEXT_MUTED, ft.Icons.HELP_OUTLINE))
    return ft.Container(
        content=ft.Row(
            [
                ft.Icon(icon, size=12, color=color),
                ft.Text(status, size=theme.SIZE_XS, color=color, weight=ft.FontWeight.W_500),
            ],
            spacing=4,
            tight=True,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        bgcolor=ft.Colors.with_opacity(0.12, color),
        padding=ft.padding.symmetric(horizontal=theme.S2, vertical=2),
        border_radius=theme.RADIUS_PILL,
        border=ft.border.all(1, ft.Colors.with_opacity(0.3, color)),
    )
