"""Resources tab — subscription picker, resource tree, search, filters, portal links."""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any
import urllib.parse

import flet as ft

from app import theme
from app.components.toast import show_toast
from app.components.tree_node import TreeNode, _resource_type_icon
from app.services import arm
from app.state import state

log = logging.getLogger(__name__)

_ARM_BASE_PORTAL = "https://portal.azure.com"


def _portal_url(tenant_id: str, resource_id: str) -> str:
    return f"{_ARM_BASE_PORTAL}/#@{tenant_id}/resource{resource_id}"


def build(page: ft.Page) -> ft.Control:
    is_dark = state.dark_mode
    bg = theme.DARK_BG if is_dark else theme.LIGHT_BG
    surface = theme.DARK_SURFACE if is_dark else theme.LIGHT_SURFACE
    border = theme.DARK_BORDER if is_dark else theme.LIGHT_BORDER
    text = theme.DARK_TEXT if is_dark else theme.LIGHT_TEXT
    muted = theme.DARK_TEXT_MUTED if is_dark else theme.LIGHT_TEXT_MUTED

    # ── Local state ───────────────────────────────────────────────────────────
    _rgs: list[dict] = []
    _resources: list[dict] = []
    _search_term = {"v": ""}
    _type_filter: set[str] = set()
    _location_filter: set[str] = set()

    # ── Refs ──────────────────────────────────────────────────────────────────
    sub_dd_ref = ft.Ref[ft.Dropdown]()
    search_ref = ft.Ref[ft.TextField]()
    tree_col_ref = ft.Ref[ft.Column]()
    spinner_ref = ft.Ref[ft.ProgressRing]()
    empty_ref = ft.Ref[ft.Container]()
    error_ref = ft.Ref[ft.Container]()
    type_filter_col_ref = ft.Ref[ft.Column]()
    loc_filter_col_ref = ft.Ref[ft.Column]()
    resource_count_ref = ft.Ref[ft.Text]()

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _set_loading(v: bool) -> None:
        spinner_ref.current.visible = v
        empty_ref.current.visible = False
        error_ref.current.visible = False
        if v:
            tree_col_ref.current.controls = []
        page.update()

    def _set_error(msg: str) -> None:
        spinner_ref.current.visible = False
        error_ref.current.content = ft.Column(
            [
                ft.Icon(ft.Icons.ERROR_OUTLINE, color=theme.ERROR, size=32),
                ft.Text(msg, color=theme.ERROR, size=theme.SIZE_BODY, text_align=ft.TextAlign.CENTER),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=theme.S2,
        )
        error_ref.current.visible = True
        page.update()

    def _matches(name: str, rtype: str, location: str) -> bool:
        term = _search_term["v"].lower()
        if term and term not in name.lower() and term not in rtype.lower():
            return False
        if _type_filter and rtype.lower() not in _type_filter:
            return False
        if _location_filter and location.lower() not in _location_filter:
            return False
        return True

    def _build_tree() -> None:
        term = _search_term["v"].lower()
        # Group resources by RG
        rg_map: dict[str, list[dict]] = defaultdict(list)
        for res in _resources:
            rg_name = ""
            # resourceId: /subscriptions/{sub}/resourceGroups/{rg}/providers/...
            parts = res.get("id", "").split("/")
            if "resourceGroups" in parts:
                rg_name = parts[parts.index("resourceGroups") + 1]
            rg_map[rg_name.lower()].append(res)

        # Collect all unique resource types + locations for filter panels
        all_types = sorted({r.get("type", "").lower() for r in _resources if r.get("type")})
        all_locs = sorted({r.get("location", "").lower() for r in _resources if r.get("location")})

        # Rebuild filter dropdowns
        type_filter_col_ref.current.controls = _build_filter_checks(
            all_types, _type_filter, lambda: _build_tree()
        )
        loc_filter_col_ref.current.controls = _build_filter_checks(
            all_locs, _location_filter, lambda: _build_tree()
        )

        nodes: list[ft.Control] = []
        matched_count = 0

        for rg in _rgs:
            rg_name = rg.get("name", "")
            rg_resources = rg_map.get(rg_name.lower(), [])

            # Filter resources
            filtered_res = [
                r for r in rg_resources
                if _matches(r.get("name", ""), r.get("type", ""), r.get("location", ""))
            ]

            if term and not filtered_res:
                continue  # skip RGs with no matches when searching

            matched_count += len(filtered_res)

            # Group by resource type within this RG
            type_map: dict[str, list[dict]] = defaultdict(list)
            for r in filtered_res:
                type_map[r.get("type", "Unknown")].append(r)

            def _make_resource_nodes(resources: list[dict], rtype: str, h: str) -> list[TreeNode]:
                nodes_inner = []
                for r in resources:
                    res_name = r.get("name", "—")
                    res_id = r.get("id", "")
                    tid = state.active_tenant_id or ""

                    def _open_portal(rid=res_id, tenant=tid) -> None:
                        page.launch_url(_portal_url(tenant, rid))

                    nodes_inner.append(
                        TreeNode(
                            label=res_name,
                            icon=_resource_type_icon(rtype),
                            icon_color=theme.ACCENT,
                            on_action=_open_portal,
                            depth=3,
                            highlight=h,
                            is_dark=is_dark,
                        )
                    )
                return nodes_inner

            def _make_type_nodes(tm: dict, h: str) -> list[TreeNode]:
                tnodes = []
                for rtype, res_list in sorted(tm.items()):
                    short_type = rtype.split("/")[-1] if "/" in rtype else rtype
                    tnodes.append(
                        TreeNode(
                            label=short_type,
                            icon=_resource_type_icon(rtype),
                            icon_color=muted,
                            count=len(res_list),
                            children_builder=lambda rl=res_list, rt=rtype, hh=h: _make_resource_nodes(rl, rt, hh),
                            depth=2,
                            highlight=h,
                            is_dark=is_dark,
                        )
                    )
                return tnodes

            rg_node = TreeNode(
                label=rg_name,
                icon=ft.Icons.FOLDER_OUTLINED,
                icon_color=theme.WARN,
                count=len(filtered_res),
                children_builder=lambda tm=type_map, h=term: _make_type_nodes(tm, h),
                depth=1,
                highlight=term,
                is_dark=is_dark,
            )
            if term:
                rg_node.expand_all()
            nodes.append(rg_node)

        resource_count_ref.current.value = f"{matched_count} resource{'s' if matched_count != 1 else ''}"
        tree_col_ref.current.controls = nodes
        empty_ref.current.visible = len(nodes) == 0
        spinner_ref.current.visible = False
        page.update()

    def _build_filter_checks(
        items: list[str],
        active_set: set[str],
        on_change_cb: callable,
    ) -> list[ft.Control]:
        controls = []
        for item in items[:30]:  # cap to avoid huge lists
            display = item.split("/")[-1] if "/" in item else item
            cb = ft.Checkbox(
                value=item in active_set,
                label=display,
                label_style=ft.TextStyle(size=theme.SIZE_XS, color=text),
                fill_color=theme.ACCENT,
                active_color=theme.ACCENT,
            )

            def _on_cb(e: ft.ControlEvent, it=item, s=active_set) -> None:
                if e.control.value:
                    s.add(it)
                else:
                    s.discard(it)
                on_change_cb()

            cb.on_change = _on_cb
            controls.append(cb)
        return controls

    # ── Data loading ──────────────────────────────────────────────────────────
    async def _load_resources(sub_id: str, force: bool = False) -> None:
        tid = state.active_tenant_id or ""
        cache_key = (tid, sub_id)

        _set_loading(True)
        nonlocal _rgs, _resources

        try:
            if not force and cache_key in state.resource_cache:
                cached = state.resource_cache[cache_key]
                _rgs = cached["rgs"]
                _resources = cached["resources"]
            else:
                rg_result, res_result = await asyncio.gather(
                    arm.list_resource_groups(sub_id, tenant_id=tid or None),
                    arm.list_resources(sub_id, tenant_id=tid or None),
                    return_exceptions=True,
                )
                if isinstance(rg_result, Exception):
                    raise rg_result
                if isinstance(res_result, Exception):
                    raise res_result
                _rgs = rg_result
                _resources = res_result
                state.resource_cache[cache_key] = {"rgs": _rgs, "resources": _resources}

            _type_filter.clear()
            _location_filter.clear()
            _build_tree()
        except Exception as exc:
            log.exception("Resource load failed")
            _set_error(str(exc))
        finally:
            spinner_ref.current.visible = False
            page.update()

    def _on_sub_change(e: ft.ControlEvent) -> None:
        sub_id = e.control.value
        if sub_id:
            state.selected_subscription_resources = sub_id
            asyncio.ensure_future(_load_resources(sub_id))

    # ── Search ────────────────────────────────────────────────────────────────
    _search_debounce: asyncio.Task | None = None

    def _on_search(e: ft.ControlEvent) -> None:
        nonlocal _search_debounce
        _search_term["v"] = e.control.value or ""
        if _search_debounce and not _search_debounce.done():
            _search_debounce.cancel()
        _search_debounce = asyncio.ensure_future(_debounced_search())

    async def _debounced_search() -> None:
        await asyncio.sleep(0.3)
        _build_tree()

    # ── Keyboard shortcut Ctrl+F ──────────────────────────────────────────────
    def _on_keyboard(e: ft.KeyboardEvent) -> None:
        if e.ctrl and e.key == "F":
            if search_ref.current:
                search_ref.current.focus()

    page.on_keyboard_event = _on_keyboard

    # ── Pubsub ────────────────────────────────────────────────────────────────
    def _on_refresh_signal(topic: str) -> None:
        if topic == "refresh" and state.selected_subscription_resources:
            asyncio.ensure_future(_load_resources(state.selected_subscription_resources, force=True))

    page.pubsub.subscribe(_on_refresh_signal)

    # ── Layout ────────────────────────────────────────────────────────────────
    def _sub_options() -> list[ft.dropdown.Option]:
        return [
            ft.dropdown.Option(
                key=s.get("subscriptionId") or s.get("id", ""),
                text=s.get("displayName") or s.get("name", "—"),
            )
            for s in state.subscriptions
            if s.get("state", "Enabled") == "Enabled"
        ]

    sub_dropdown = ft.Dropdown(
        ref=sub_dd_ref,
        options=_sub_options(),
        value=state.selected_subscription_resources,
        on_change=_on_sub_change,
        hint_text="Select subscription…",
        hint_style=ft.TextStyle(color=muted, size=theme.SIZE_SM),
        border_color=border,
        focused_border_color=theme.ACCENT,
        text_style=ft.TextStyle(color=text, size=theme.SIZE_SM),
        width=320,
        dense=True,
        content_padding=ft.padding.symmetric(horizontal=theme.S3, vertical=theme.S1),
    )

    search_field = ft.TextField(
        ref=search_ref,
        hint_text="Search resources… (Ctrl+F)",
        hint_style=ft.TextStyle(color=muted, size=theme.SIZE_SM),
        prefix_icon=ft.Icons.SEARCH,
        border_color=border,
        focused_border_color=theme.ACCENT,
        text_style=ft.TextStyle(color=text, size=theme.SIZE_SM),
        content_padding=ft.padding.symmetric(horizontal=theme.S3, vertical=theme.S1),
        height=36,
        width=280,
        on_change=_on_search,
    )

    top_bar = ft.Container(
        content=ft.Row(
            [
                ft.Text("Subscription", size=theme.SIZE_SM, color=muted),
                sub_dropdown,
                ft.Container(expand=True),
                search_field,
                ft.Text(ref=resource_count_ref, value="", size=theme.SIZE_XS, color=muted),
                ft.IconButton(
                    icon=ft.Icons.REFRESH_OUTLINED,
                    icon_color=muted,
                    icon_size=16,
                    tooltip="Reload resources",
                    on_click=lambda e: asyncio.ensure_future(
                        _load_resources(state.selected_subscription_resources or "", force=True)
                    ) if state.selected_subscription_resources else None,
                ),
            ],
            spacing=theme.S3,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        bgcolor=surface,
        padding=ft.padding.symmetric(horizontal=theme.S4, vertical=theme.S2),
        border=ft.border.only(bottom=ft.BorderSide(1, border)),
        height=48,
    )

    # Filter side panel
    filter_panel = ft.Container(
        content=ft.Column(
            [
                ft.Text("Type", size=theme.SIZE_SM, color=muted, weight=ft.FontWeight.W_600),
                ft.Column(ref=type_filter_col_ref, controls=[], spacing=2, scroll=ft.ScrollMode.AUTO),
                ft.Divider(height=1, color=border),
                ft.Text("Location", size=theme.SIZE_SM, color=muted, weight=ft.FontWeight.W_600),
                ft.Column(ref=loc_filter_col_ref, controls=[], spacing=2, scroll=ft.ScrollMode.AUTO),
            ],
            spacing=theme.S2,
            tight=True,
            scroll=ft.ScrollMode.AUTO,
        ),
        width=160,
        padding=ft.padding.all(theme.S3),
        bgcolor=surface,
        border=ft.border.only(right=ft.BorderSide(1, border)),
    )

    tree_area = ft.Column(
        ref=tree_col_ref,
        controls=[],
        spacing=0,
        expand=True,
        scroll=ft.ScrollMode.AUTO,
    )

    empty_state = ft.Container(
        ref=empty_ref,
        content=ft.Column(
            [
                ft.Icon(ft.Icons.FOLDER_OPEN_OUTLINED, color=muted, size=40),
                ft.Text("No resources found", color=muted, size=theme.SIZE_BODY),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=theme.S3,
        ),
        alignment=ft.alignment.center,
        expand=True,
        visible=False,
    )

    error_state = ft.Container(
        ref=error_ref,
        alignment=ft.alignment.center,
        expand=True,
        visible=False,
    )

    spinner = ft.Container(
        content=ft.ProgressRing(
            ref=spinner_ref,
            width=32,
            height=32,
            stroke_width=3,
            color=theme.ACCENT,
            visible=False,
        ),
        alignment=ft.alignment.center,
        expand=True,
    )

    main_area = ft.Stack(
        [
            ft.Container(
                content=ft.Column(
                    [tree_area],
                    expand=True,
                    scroll=ft.ScrollMode.AUTO,
                ),
                expand=True,
                bgcolor=bg,
                padding=ft.padding.all(theme.S3),
            ),
            spinner,
            empty_state,
            error_state,
        ],
        expand=True,
    )

    # ── Auto-load ─────────────────────────────────────────────────────────────
    async def _auto_load() -> None:
        await asyncio.sleep(0.1)
        sub_id = state.selected_subscription_resources
        if not sub_id and state.subscriptions:
            for s in state.subscriptions:
                if s.get("state", "Enabled") == "Enabled":
                    sub_id = s.get("subscriptionId") or s.get("id", "")
                    state.selected_subscription_resources = sub_id
                    if sub_dd_ref.current:
                        sub_dd_ref.current.value = sub_id
                    break
        if sub_id:
            await _load_resources(sub_id)

    asyncio.ensure_future(_auto_load())

    return ft.Column(
        [
            top_bar,
            ft.Row(
                [
                    filter_panel,
                    main_area,
                ],
                spacing=0,
                expand=True,
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
        ],
        spacing=0,
        expand=True,
    )
