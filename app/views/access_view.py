"""Access tab — subscription picker + PIM role tables + activation bar."""

from __future__ import annotations

import asyncio
import logging

import flet as ft

from app import theme
from app.components.status_chip import build as chip
from app.components.toast import show_toast
from app.services import arm, pim
from app.state import state

log = logging.getLogger(__name__)

# ── Column widths ─────────────────────────────────────────────────────────────
_COL = {
    "check": 36,
    "status": 110,
    "role": 160,
    "resource": 220,
    "via": 80,
    "expires": 170,
    "action": 80,
}


def build(page: ft.Page) -> ft.Control:
    is_dark = state.dark_mode
    bg = theme.DARK_BG if is_dark else theme.LIGHT_BG
    surface = theme.DARK_SURFACE if is_dark else theme.LIGHT_SURFACE
    surface2 = theme.DARK_SURFACE2 if is_dark else theme.LIGHT_SURFACE2
    border = theme.DARK_BORDER if is_dark else theme.LIGHT_BORDER
    text = theme.DARK_TEXT if is_dark else theme.LIGHT_TEXT
    muted = theme.DARK_TEXT_MUTED if is_dark else theme.LIGHT_TEXT_MUTED

    # ── State (local to this view instance) ──────────────────────────────────
    _selected: set[str] = set()  # set of role IDs
    _all_rows: list[dict] = []  # full data set (unfiltered)
    _filtered_rows: list[dict] = []  # after filter rail

    # Filter rail checkboxes
    _show_active = {"v": True}
    _show_eligible = {"v": True}
    _show_pending = {"v": True}
    _hide_duplicates = {"v": False}

    # ── Refs ──────────────────────────────────────────────────────────────────
    sub_dd_ref = ft.Ref[ft.Dropdown]()
    table_col_ref = ft.Ref[ft.Column]()
    spinner_ref = ft.Ref[ft.ProgressRing]()
    empty_ref = ft.Ref[ft.Container]()
    error_ref = ft.Ref[ft.Container]()
    sel_count_ref = ft.Ref[ft.Text]()
    activate_btn_ref = ft.Ref[ft.FilledButton]()
    justification_ref = ft.Ref[ft.TextField]()
    duration_dd_ref = ft.Ref[ft.Dropdown]()
    # Filter counts
    active_count_ref = ft.Ref[ft.Text]()
    eligible_count_ref = ft.Ref[ft.Text]()
    pending_count_ref = ft.Ref[ft.Text]()

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _cell(value: str, width: int, bold: bool = False) -> ft.Container:
        return ft.Container(
            content=ft.Text(
                value,
                size=theme.SIZE_TABLE,
                color=text,
                weight=ft.FontWeight.W_500 if bold else ft.FontWeight.W_400,
                max_lines=2,
                overflow=ft.TextOverflow.ELLIPSIS,
                tooltip=value,
            ),
            width=width,
            padding=ft.padding.symmetric(horizontal=theme.S2),
        )

    def _header_cell(label: str, width: int) -> ft.Container:
        return ft.Container(
            content=ft.Text(
                label,
                size=theme.SIZE_XS,
                color=muted,
                weight=ft.FontWeight.W_600,
            ),
            width=width,
            padding=ft.padding.symmetric(horizontal=theme.S2),
        )

    def _build_header() -> ft.Container:
        return ft.Container(
            content=ft.Row(
                [
                    ft.Container(width=_COL["check"]),
                    _header_cell("Status", _COL["status"]),
                    _header_cell("Role", _COL["role"]),
                    _header_cell("Resource", _COL["resource"]),
                    _header_cell("Via", _COL["via"]),
                    _header_cell("Expires", _COL["expires"]),
                    _header_cell("", _COL["action"]),
                ],
                spacing=0,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=surface2,
            padding=ft.padding.symmetric(vertical=theme.S1),
            border=ft.border.only(bottom=ft.BorderSide(1, border)),
        )

    def _build_row(row: dict) -> ft.Container:
        rid = row["id"]
        is_sel = rid in _selected
        is_active = row["status"] == "Active"

        def _toggle_check(e: ft.ControlEvent) -> None:
            if e.control.value:
                _selected.add(rid)
            else:
                _selected.discard(rid)
            _refresh_action_bar()

        expires_col = ft.Container(
            content=ft.Column(
                [
                    ft.Text(
                        row["expires_relative"],
                        size=theme.SIZE_TABLE,
                        color=text,
                    ),
                    ft.Text(
                        row["expires_absolute"],
                        size=theme.SIZE_XS,
                        color=muted,
                    ),
                ],
                spacing=1,
                tight=True,
            ),
            width=_COL["expires"],
            padding=ft.padding.symmetric(horizontal=theme.S2),
        )

        action_btn = ft.Container(
            content=ft.TextButton(
                "Activate",
                on_click=lambda e, r=row: _quick_activate(r),
                style=ft.ButtonStyle(
                    color=theme.ACCENT,
                    padding=ft.padding.symmetric(horizontal=theme.S2, vertical=2),
                ),
                visible=row["status"] == "Eligible",
            ),
            width=_COL["action"],
        )

        return ft.Container(
            content=ft.Row(
                [
                    ft.Container(
                        content=ft.Checkbox(
                            value=is_sel,
                            on_change=_toggle_check,
                            fill_color=theme.ACCENT,
                            active_color=theme.ACCENT,
                            disabled=is_active,
                        ),
                        width=_COL["check"],
                        alignment=ft.alignment.center,
                    ),
                    ft.Container(
                        content=chip(row["status"]),
                        width=_COL["status"],
                        padding=ft.padding.symmetric(horizontal=theme.S2),
                    ),
                    _cell(row.get("role_name") or "—", _COL["role"], bold=True),
                    _cell(row.get("scope_display") or "—", _COL["resource"]),
                    _cell(row.get("member_type") or "—", _COL["via"]),
                    expires_col,
                    action_btn,
                ],
                spacing=0,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=ft.Colors.with_opacity(0.06, theme.ACCENT) if is_sel else surface,
            border=ft.border.only(bottom=ft.BorderSide(1, border)),
            padding=ft.padding.symmetric(vertical=6),
        )

    def _apply_filters() -> list[dict]:
        rows = list(_all_rows)
        if not _show_active["v"]:
            rows = [r for r in rows if r["status"] != "Active"]
        if not _show_eligible["v"]:
            rows = [r for r in rows if r["status"] != "Eligible"]
        if not _show_pending["v"]:
            rows = [r for r in rows if r["status"] not in ("PendingApproval", "Provisioning")]
        if _hide_duplicates["v"]:
            seen: set[tuple] = set()
            unique = []
            for r in rows:
                key = (r.get("role_definition_id", ""), r.get("scope", ""), r["status"])
                if key not in seen:
                    seen.add(key)
                    unique.append(r)
            rows = unique
        return rows

    def _refresh_table() -> None:
        nonlocal _filtered_rows
        _filtered_rows = _apply_filters()
        _selected.clear()

        controls: list[ft.Control] = [_build_header()]
        for row in _filtered_rows:
            controls.append(_build_row(row))

        table_col_ref.current.controls = controls
        empty_ref.current.visible = len(_filtered_rows) == 0 and len(_all_rows) > 0
        error_ref.current.visible = False
        _refresh_action_bar()
        _update_filter_counts()
        page.update()

    def _refresh_action_bar() -> None:
        sel_count_ref.current.value = f"{len(_selected)} selected"
        activate_btn_ref.current.disabled = len(_selected) == 0
        page.update()

    def _update_filter_counts() -> None:
        active_count_ref.current.value = str(sum(1 for r in _all_rows if r["status"] == "Active"))
        eligible_count_ref.current.value = str(
            sum(1 for r in _all_rows if r["status"] == "Eligible")
        )
        pending_count_ref.current.value = str(
            sum(1 for r in _all_rows if r["status"] in ("PendingApproval", "Provisioning"))
        )
        page.update()

    def _set_loading(v: bool) -> None:
        spinner_ref.current.visible = v
        empty_ref.current.visible = False
        error_ref.current.visible = False
        if v:
            table_col_ref.current.controls = [_build_header()]
        page.update()

    def _set_error(msg: str) -> None:
        spinner_ref.current.visible = False
        empty_ref.current.visible = False
        error_ref.current.content = ft.Column(
            [
                ft.Icon(ft.Icons.ERROR_OUTLINE, color=theme.ERROR, size=32),
                ft.Text(
                    msg, color=theme.ERROR, size=theme.SIZE_BODY, text_align=ft.TextAlign.CENTER
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=theme.S2,
        )
        error_ref.current.visible = True
        page.update()

    # ── Data loading ──────────────────────────────────────────────────────────
    async def _load_pim(sub_id: str, force: bool = False) -> None:
        _set_loading(True)
        nonlocal _all_rows
        try:
            data = await pim.load_pim_data(sub_id, force=force)
            _all_rows = data["eligible"] + data["active"] + data["pending"]
            _refresh_table()
        except Exception as exc:
            log.exception("PIM load failed")
            _set_error(str(exc))
        finally:
            _set_loading(False)

    def _on_sub_change(e: ft.ControlEvent) -> None:
        sub_id = e.control.value
        if sub_id:
            state.selected_subscription_access = sub_id
            asyncio.ensure_future(_load_pim(sub_id))

    # ── Activation ────────────────────────────────────────────────────────────
    def _quick_activate(row: dict) -> None:
        _selected.add(row["id"])
        _refresh_action_bar()
        asyncio.ensure_future(_activate_selected())

    async def _activate_selected() -> None:
        if not _selected:
            return
        justification = justification_ref.current.value or ""
        try:
            duration = int(duration_dd_ref.current.value or "1")
        except ValueError:
            duration = 1

        sub_id = state.selected_subscription_access
        if not sub_id:
            show_toast(page, "No subscription selected", "error")
            return
        if not justification.strip():
            show_toast(page, "Justification is required", "warn")
            return

        activate_btn_ref.current.disabled = True
        page.update()

        rows_to_activate = [r for r in _filtered_rows if r["id"] in _selected]
        for row in rows_to_activate:
            # Inline status update: mark as Provisioning while polling
            row["status"] = "Provisioning"
            row["expires_relative"] = "…"
        _refresh_table()

        for row in rows_to_activate:
            asyncio.ensure_future(_submit_activation(row, sub_id, justification, duration))

    async def _submit_activation(row: dict, sub_id: str, justification: str, duration: int) -> None:
        import uuid

        req_name = str(uuid.uuid4())
        try:
            result = await arm.activate_role(
                subscription_id=sub_id,
                request_name=req_name,
                role_definition_id=row["role_definition_id"],
                principal_id=row["principal_id"],
                scope=row["scope"],
                justification=justification,
                duration_hours=duration,
                tenant_id=state.active_tenant_id,
            )
            req_name = result.get("name", req_name)
            # Poll until terminal state
            asyncio.ensure_future(_poll_activation(row, sub_id, req_name))
        except Exception as exc:
            row["status"] = "Failed"
            row["expires_relative"] = "—"
            _refresh_table()
            show_toast(page, f"Activation failed: {exc}", "error")

    async def _poll_activation(row: dict, sub_id: str, req_name: str) -> None:
        """Poll every 10s until terminal state, then update the row in place."""
        terminal = {"Granted", "Denied", "Failed", "Canceled", "Revoked"}
        for _ in range(30):  # max ~5 min
            await asyncio.sleep(10)
            try:
                result = await arm.get_role_assignment_request(
                    sub_id, req_name, tenant_id=state.active_tenant_id
                )
                props = result.get("properties", {})
                arm_status = props.get("status", "")
                if arm_status in terminal:
                    status_map = {
                        "Granted": "Active",
                        "Denied": "Denied",
                        "Failed": "Failed",
                        "Canceled": "Failed",
                        "Revoked": "Failed",
                    }
                    new_status = status_map.get(arm_status, arm_status)
                    row["status"] = new_status
                    if new_status == "Active":
                        show_toast(page, f"Activated: {row.get('role_name', 'role')}", "success")
                    elif new_status == "Denied":
                        reason = props.get("statusDetails", {}).get("statusReason", "")
                        show_toast(page, f"Denied: {reason or 'request denied'}", "error")
                    else:
                        show_toast(
                            page, f"Activation failed for {row.get('role_name', 'role')}", "error"
                        )
                    _refresh_table()
                    return
                elif arm_status == "PendingApproval":
                    row["status"] = "PendingApproval"
                    _refresh_table()
            except Exception:
                log.debug("Poll error (transient)", exc_info=True)

    # ── Bulk select ───────────────────────────────────────────────────────────
    def _select_all(_: ft.ControlEvent) -> None:
        for row in _filtered_rows:
            if row["status"] == "Eligible":
                _selected.add(row["id"])
        _refresh_table()

    # ── Filter rail ───────────────────────────────────────────────────────────
    def _on_hide_dup_change(e: ft.ControlEvent) -> None:
        _hide_duplicates["v"] = e.control.value
        _refresh_table()

    def _make_filter_check(label: str, state_dict: dict, count_ref: ft.Ref) -> ft.Row:
        def _on_change(e: ft.ControlEvent) -> None:
            state_dict["v"] = e.control.value
            _refresh_table()

        return ft.Row(
            [
                ft.Checkbox(
                    value=state_dict["v"],
                    on_change=_on_change,
                    fill_color=theme.ACCENT,
                    active_color=theme.ACCENT,
                    label=label,
                    label_style=ft.TextStyle(size=theme.SIZE_SM, color=text),
                ),
                ft.Text(ref=count_ref, value="0", size=theme.SIZE_XS, color=muted),
            ],
            spacing=theme.S2,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    filter_rail = ft.Container(
        content=ft.Column(
            [
                ft.Text("Filter", size=theme.SIZE_SM, color=muted, weight=ft.FontWeight.W_600),
                ft.Divider(height=1, color=border),
                _make_filter_check("Active", _show_active, active_count_ref),
                _make_filter_check("Eligible", _show_eligible, eligible_count_ref),
                _make_filter_check("Pending", _show_pending, pending_count_ref),
                ft.Divider(height=1, color=border),
                ft.Row(
                    [
                        ft.Checkbox(
                            value=_hide_duplicates["v"],
                            on_change=_on_hide_dup_change,
                            fill_color=theme.ACCENT,
                            active_color=theme.ACCENT,
                            label="Hide duplicates",
                            label_style=ft.TextStyle(size=theme.SIZE_SM, color=text),
                        ),
                    ],
                ),
            ],
            spacing=theme.S2,
            tight=True,
        ),
        width=160,
        padding=ft.padding.all(theme.S3),
        bgcolor=surface,
        border=ft.border.only(right=ft.BorderSide(1, border)),
    )

    # ── Table area ────────────────────────────────────────────────────────────
    table_col = ft.Column(
        ref=table_col_ref,
        controls=[_build_header()],
        spacing=0,
        scroll=ft.ScrollMode.AUTO,
    )

    overlay_spinner = ft.Container(
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

    empty_state = ft.Container(
        ref=empty_ref,
        content=ft.Column(
            [
                ft.Icon(ft.Icons.LOCK_OUTLINED, color=muted, size=40),
                ft.Text(
                    "No roles in this subscription",
                    color=muted,
                    size=theme.SIZE_BODY,
                    text_align=ft.TextAlign.CENTER,
                ),
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

    table_area = ft.Stack(
        [
            ft.Container(content=table_col, expand=True, bgcolor=bg),
            overlay_spinner,
            empty_state,
            error_state,
        ],
        expand=True,
    )

    # ── Subscription dropdown ─────────────────────────────────────────────────
    def _sub_options() -> list[ft.dropdown.Option]:
        return [
            ft.dropdown.Option(
                key=s.get("subscriptionId") or s.get("id", ""),
                text=f"{s.get('displayName') or s.get('name', '—')}",
            )
            for s in state.subscriptions
            if s.get("state", "Enabled") == "Enabled"
        ]

    sub_dropdown = ft.Dropdown(
        ref=sub_dd_ref,
        options=_sub_options(),
        value=state.selected_subscription_access,
        on_change=_on_sub_change,
        hint_text="Select subscription…",
        hint_style=ft.TextStyle(color=muted, size=theme.SIZE_SM),
        border_color=border,
        focused_border_color=theme.ACCENT,
        text_style=ft.TextStyle(size=theme.SIZE_SM, color=text),
        width=320,
        dense=True,
        content_padding=ft.padding.symmetric(horizontal=theme.S3, vertical=theme.S1),
    )

    top_bar = ft.Container(
        content=ft.Row(
            [
                ft.Text("Subscription", size=theme.SIZE_SM, color=muted),
                sub_dropdown,
                ft.Container(expand=True),
                ft.IconButton(
                    icon=ft.Icons.REFRESH_OUTLINED,
                    icon_color=muted,
                    icon_size=16,
                    tooltip="Reload PIM data",
                    on_click=lambda e: asyncio.ensure_future(
                        _load_pim(state.selected_subscription_access or "", force=True)
                    )
                    if state.selected_subscription_access
                    else None,
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

    # ── Action bar ────────────────────────────────────────────────────────────
    action_bar = ft.Container(
        content=ft.Row(
            [
                ft.TextField(
                    ref=justification_ref,
                    hint_text="Justification (required)",
                    hint_style=ft.TextStyle(color=muted, size=theme.SIZE_SM),
                    border_color=border,
                    focused_border_color=theme.ACCENT,
                    text_style=ft.TextStyle(color=text, size=theme.SIZE_SM),
                    content_padding=ft.padding.symmetric(horizontal=theme.S3, vertical=theme.S1),
                    height=36,
                    expand=True,
                    max_length=500,
                ),
                ft.Dropdown(
                    ref=duration_dd_ref,
                    options=[ft.dropdown.Option(key=str(h), text=f"{h}h") for h in range(1, 9)],
                    value="1",
                    width=80,
                    dense=True,
                    border_color=border,
                    focused_border_color=theme.ACCENT,
                    text_style=ft.TextStyle(color=text, size=theme.SIZE_SM),
                    content_padding=ft.padding.symmetric(horizontal=theme.S2, vertical=0),
                    tooltip="Activation duration",
                ),
                ft.Text(ref=sel_count_ref, value="0 selected", color=muted, size=theme.SIZE_SM),
                ft.TextButton(
                    "Select eligible",
                    on_click=_select_all,
                    style=ft.ButtonStyle(color=theme.ACCENT),
                ),
                ft.FilledButton(
                    ref=activate_btn_ref,
                    text="Activate",
                    icon=ft.Icons.BOLT,
                    on_click=lambda e: asyncio.ensure_future(_activate_selected()),
                    disabled=True,
                    style=ft.ButtonStyle(
                        bgcolor=theme.SUCCESS,
                        color="#ffffff",
                        disabled_bgcolor=ft.Colors.with_opacity(0.3, theme.SUCCESS),
                        shape=ft.RoundedRectangleBorder(radius=theme.RADIUS_MD),
                        padding=ft.padding.symmetric(horizontal=theme.S4, vertical=theme.S2),
                    ),
                ),
            ],
            spacing=theme.S3,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        bgcolor=surface,
        padding=ft.padding.symmetric(horizontal=theme.S4, vertical=theme.S2),
        border=ft.border.only(top=ft.BorderSide(1, border)),
    )

    # ── Pubsub: refresh signal from shell ─────────────────────────────────────
    def _on_refresh_signal(topic: str) -> None:
        if topic == "refresh" and state.selected_subscription_access:
            asyncio.ensure_future(_load_pim(state.selected_subscription_access, force=True))

    page.pubsub.subscribe(_on_refresh_signal)

    # ── Auto-load if subscription already selected ────────────────────────────
    async def _auto_load() -> None:
        await asyncio.sleep(0.1)  # let Flet mount refs first
        sub_id = state.selected_subscription_access
        if not sub_id and state.subscriptions:
            for s in state.subscriptions:
                if s.get("state", "Enabled") == "Enabled":
                    sub_id = s.get("subscriptionId") or s.get("id", "")
                    state.selected_subscription_access = sub_id
                    if sub_dd_ref.current:
                        sub_dd_ref.current.value = sub_id
                    break
        if sub_id:
            await _load_pim(sub_id)

    asyncio.ensure_future(_auto_load())

    return ft.Column(
        [
            top_bar,
            ft.Row(
                [
                    filter_rail,
                    table_area,
                ],
                spacing=0,
                expand=True,
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
            action_bar,
        ],
        spacing=0,
        expand=True,
    )
