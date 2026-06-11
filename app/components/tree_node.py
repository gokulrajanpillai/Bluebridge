"""Lazy-expanding tree node for the resources hierarchy."""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from app import theme


def _resource_type_icon(resource_type: str) -> ft.IconData:
    rt = resource_type.lower()
    if "storageaccount" in rt or "storage" in rt:
        return ft.Icons.STORAGE_OUTLINED
    if "keyvault" in rt or "vault" in rt:
        return ft.Icons.KEY_OUTLINED
    if "site" in rt or "webapp" in rt or "appservice" in rt:
        return ft.Icons.WEB_OUTLINED
    if "sql" in rt or "database" in rt:
        return ft.Icons.TABLE_CHART_OUTLINED
    if "virtualnetwork" in rt or "network" in rt:
        return ft.Icons.DEVICE_HUB_OUTLINED
    if "virtualmachine" in rt or "compute" in rt:
        return ft.Icons.COMPUTER_OUTLINED
    if "containerregistry" in rt:
        return ft.Icons.INBOX_OUTLINED
    if "aks" in rt or "managedcluster" in rt:
        return ft.Icons.CLOUD_QUEUE_OUTLINED
    if "function" in rt:
        return ft.Icons.FUNCTIONS_OUTLINED
    if "logicapp" in rt:
        return ft.Icons.ACCOUNT_TREE_OUTLINED
    if "servicebus" in rt:
        return ft.Icons.BUS_ALERT_OUTLINED
    if "eventhub" in rt:
        return ft.Icons.STREAM_OUTLINED
    return ft.Icons.INVENTORY_2_OUTLINED


class TreeNode(ft.Column):
    """A single expandable node in the resource tree."""

    def __init__(
        self,
        label: str,
        icon: ft.Icons = ft.Icons.FOLDER_OUTLINED,
        icon_color: str = theme.ACCENT,
        count: int | None = None,
        children_builder: Callable[[], list[TreeNode]] | None = None,
        on_action: Callable[[], None] | None = None,
        depth: int = 0,
        highlight: str = "",
        is_dark: bool = True,
    ) -> None:
        super().__init__(spacing=0, tight=True)
        self._label = label
        self._icon = icon
        self._icon_color = icon_color
        self._count = count
        self._children_builder = children_builder
        self._on_action = on_action
        self._depth = depth
        self._highlight = highlight.lower()
        self._is_dark = is_dark
        self._expanded = False
        self._children_loaded = False

        text_color = theme.DARK_TEXT if is_dark else theme.LIGHT_TEXT
        muted = theme.DARK_TEXT_MUTED if is_dark else theme.LIGHT_TEXT_MUTED

        indent = self._depth * 16

        # Highlight matching text
        label_spans = self._make_label_spans(label, text_color)

        count_badge = ft.Container(
            content=ft.Text(str(count), size=theme.SIZE_XS, color=muted),
            bgcolor=ft.Colors.with_opacity(0.1, muted),
            padding=ft.padding.symmetric(horizontal=5, vertical=1),
            border_radius=10,
            visible=count is not None,
        )

        expand_icon_ref = ft.Ref[ft.Icon]()

        def _toggle(_: ft.ControlEvent) -> None:
            self._expanded = not self._expanded
            expand_icon_ref.current.name = (
                ft.Icons.EXPAND_MORE if self._expanded else ft.Icons.CHEVRON_RIGHT
            )
            children_col.visible = self._expanded
            if self._expanded and not self._children_loaded and self._children_builder:
                self._children_loaded = True
                children_col.controls = self._children_builder()
            self.update()

        row_controls = [ft.Container(width=indent)]
        if children_builder:
            row_controls.append(
                ft.GestureDetector(
                    content=ft.Icon(
                        ref=expand_icon_ref,
                        name=ft.Icons.CHEVRON_RIGHT,
                        size=16,
                        color=muted,
                    ),
                    on_tap=_toggle,
                )
            )
        else:
            row_controls.append(ft.Container(width=16))

        row_controls += [
            ft.Icon(self._icon, size=16, color=self._icon_color),
            ft.Row(label_spans, spacing=0, tight=True, expand=True),
            count_badge,
        ]

        if on_action:
            row_controls.append(
                ft.Container(
                    content=ft.IconButton(
                        icon=ft.Icons.OPEN_IN_NEW,
                        icon_size=14,
                        icon_color=muted,
                        tooltip="Open in Azure Portal",
                        on_click=lambda _: on_action(),
                    ),
                    visible=False,  # shown on hover via GestureDetector approach
                )
            )

        self._row = ft.Container(
            content=ft.Row(
                row_controls,
                spacing=theme.S2,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.padding.symmetric(vertical=4, horizontal=theme.S2),
            border_radius=theme.RADIUS_SM,
            on_click=_toggle
            if children_builder
            else (lambda _: on_action() if on_action else None),
        )

        children_col = ft.Column(controls=[], spacing=0, tight=True, visible=False)

        self.controls = [self._row, children_col]
        self._children_col = children_col

    def _make_label_spans(self, label: str, color: str) -> list[ft.Control]:
        if not self._highlight:
            return [ft.Text(label, size=theme.SIZE_TABLE, color=color)]
        lower = label.lower()
        idx = lower.find(self._highlight)
        if idx == -1:
            return [ft.Text(label, size=theme.SIZE_TABLE, color=color)]
        pre = label[:idx]
        match = label[idx : idx + len(self._highlight)]
        post = label[idx + len(self._highlight) :]
        spans = []
        if pre:
            spans.append(ft.Text(pre, size=theme.SIZE_TABLE, color=color))
        spans.append(
            ft.Text(
                match,
                size=theme.SIZE_TABLE,
                color=theme.ACCENT,
                weight=ft.FontWeight.W_700,
            )
        )
        if post:
            spans.append(ft.Text(post, size=theme.SIZE_TABLE, color=color))
        return spans

    def expand_all(self) -> None:
        if self._children_builder and not self._children_loaded:
            self._children_loaded = True
            self._children_col.controls = self._children_builder()
        self._expanded = True
        self._children_col.visible = True
        for child in self._children_col.controls:
            if isinstance(child, TreeNode):
                child.expand_all()
