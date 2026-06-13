"""BlueBridge — Azure PIM Access Manager."""

from __future__ import annotations

import concurrent.futures
import uuid
from datetime import datetime
from typing import Any

import streamlit as st

from app.services import acr as acr_svc
from app.services import arm, az_cli, pim
from app.services import logs as logs_svc
from app.services import storage as storage_svc
from app.services.auth import clear_token_cache, load_tenants_and_subscriptions
from app.services.logs import PermissionDeniedError

st.set_page_config(
    page_title="BlueBridge",
    page_icon="🌉",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .status-eligible { color: #3b82f6; font-weight: 600; }
    .status-active   { color: #22c55e; font-weight: 600; }
    .status-pending  { color: #f59e0b; font-weight: 600; }
    .status-denied   { color: #ef4444; font-weight: 600; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Resource type icons ───────────────────────────────────────────────────────

_RESOURCE_ICONS: dict[str, str] = {
    "microsoft.compute/virtualmachines": "🖥️",
    "microsoft.compute/virtualmachinescalesets": "🖥️",
    "microsoft.storage/storageaccounts": "🗄️",
    "microsoft.keyvault/vaults": "🔑",
    "microsoft.web/sites": "🌐",
    "microsoft.web/serverfarms": "🌐",
    "microsoft.sql/servers": "🗃️",
    "microsoft.sql/servers/databases": "🗃️",
    "microsoft.network/virtualnetworks": "🔗",
    "microsoft.network/networksecuritygroups": "🛡️",
    "microsoft.network/publicipaddresses": "🌍",
    "microsoft.network/applicationgateways": "🔀",
    "microsoft.network/loadbalancers": "⚖️",
    "microsoft.containerservice/managedclusters": "☸️",
    "microsoft.containerregistry/registries": "📦",
    "microsoft.containerinstance/containergroups": "📫",
    "microsoft.app/containerapps": "📫",
    "microsoft.app/managedenvironments": "📫",
    "microsoft.dbforpostgresql/servers": "🐘",
    "microsoft.dbforpostgresql/flexibleservers": "🐘",
    "microsoft.dbformysql/servers": "🐬",
    "microsoft.dbformysql/flexibleservers": "🐬",
    "microsoft.cache/redis": "⚡",
    "microsoft.servicebus/namespaces": "📨",
    "microsoft.eventhub/namespaces": "📡",
    "microsoft.insights/components": "📊",
    "microsoft.logic/workflows": "⚙️",
    "microsoft.documentdb/databaseaccounts": "🌿",
    "microsoft.search/searchservices": "🔍",
    "microsoft.cognitiveservices/accounts": "🧠",
    "microsoft.machinelearningservices/workspaces": "🤖",
    "microsoft.automation/automationaccounts": "🔄",
    "microsoft.datafactory/factories": "🏭",
    "microsoft.databricks/workspaces": "🔥",
    "microsoft.apimanagement/service": "🔌",
    "microsoft.appconfiguration/configurationstores": "⚙️",
    "microsoft.cdn/profiles": "🌐",
}


def _resource_icon(rtype: str) -> str:
    return _RESOURCE_ICONS.get(rtype.lower(), "📄")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _tenant_label(t: dict) -> str:
    return t.get("displayName") or t.get("tenantId", "Unknown")


def _subscriptions_for_tenant(tenant_id: str) -> list[dict]:
    return [
        s for s in st.session_state.subscriptions
        if s.get("tenantId") == tenant_id or s.get("homeTenantId") == tenant_id
    ]


def _load_pim_for_tenant(tenant_id: str, force: bool = False) -> dict[str, list]:
    subs = _subscriptions_for_tenant(tenant_id)
    all_eligible: list[dict] = []
    all_active: list[dict] = []
    all_pending: list[dict] = []

    all_subs = st.session_state.subscriptions
    t_label = next(
        (_tenant_label(t) for t in st.session_state.tenants if t.get("tenantId") == tenant_id),
        tenant_id,
    )

    for sub in subs:
        raw_id = sub.get("id") or sub.get("subscriptionId", "")
        sub_id = raw_id.lstrip("/").removeprefix("subscriptions/")
        if not sub_id:
            continue
        data = pim.load_pim_data(sub_id, tenant_id, all_subs, force=force)
        sub_name = sub.get("name") or sub.get("displayName") or sub_id
        for item in data["eligible"] + data["active"] + data["pending"]:
            item.setdefault("_tenant_label", t_label)
            item.setdefault("_sub_name", sub_name)
            item.setdefault("_sub_id", sub_id)
            item.setdefault("_tenant_id", tenant_id)
        all_eligible.extend(data["eligible"])
        all_active.extend(data["active"])
        all_pending.extend(data["pending"])

    # Back-fill role names on pending from eligible/active lookup
    _role_map = {
        i["role_definition_id"]: i["role_name"]
        for i in all_eligible + all_active
        if i.get("role_name") and i.get("role_definition_id")
    }
    for item in all_pending:
        if not item.get("role_name"):
            item["role_name"] = _role_map.get(item["role_definition_id"], "")

    return {"eligible": all_eligible, "active": all_active, "pending": all_pending}


def _portal_url(tenant_id: str, resource_id: str) -> str:
    return f"https://portal.azure.com/#@{tenant_id}/resource{resource_id}"


def _rg_from_id(resource_id: str) -> str:
    parts = resource_id.strip("/").split("/")
    for i, p in enumerate(parts):
        if p.lower() == "resourcegroups" and i + 1 < len(parts):
            return parts[i + 1]
    return ""


def _name_from_id(resource_id: str) -> str:
    return resource_id.rstrip("/").split("/")[-1]


# ── Bulk activation ───────────────────────────────────────────────────────────

# ── Auto-refreshing fragments ─────────────────────────────────────────────────

@st.fragment(run_every="60s")
def _active_tab_content() -> None:
    _all_active: list[dict] = []
    for _tid in st.session_state.get("_selected_tids", []):
        try:
            _d = _load_pim_for_tenant(_tid, force=True)
            _all_active.extend(_d["active"])
        except Exception:  # noqa: S110
            pass
    st.caption(f"Auto-refreshes every 60s · Last: {datetime.now().strftime('%H:%M:%S')}")
    if not _all_active:
        st.info("No active role assignments found.")
        return
    h1, h2, h3, h4 = st.columns([3, 3, 2, 2])
    h1.markdown("**Role**")
    h2.markdown("**Scope**")
    h3.markdown("**Tenant**")
    h4.markdown("**Expires**")
    st.divider()
    for row in _all_active:
        c1, c2, c3, c4 = st.columns([3, 3, 2, 2])
        c1.markdown(f"**{row.get('role_name') or '—'}**")
        c2.text(row.get("scope_display") or "—")
        c3.caption(row.get("_tenant_label", ""))
        c4.caption(f"🟢 {row.get('expires_relative', '—')}")


@st.fragment(run_every="30s")
def _pending_tab_content() -> None:
    _all_pending: list[dict] = []
    for _tid in st.session_state.get("_selected_tids", []):
        try:
            _d = _load_pim_for_tenant(_tid, force=True)
            _all_pending.extend(_d["pending"])
        except Exception:  # noqa: S110
            pass
    st.caption(f"Auto-refreshes every 30s · Last: {datetime.now().strftime('%H:%M:%S')}")
    if not _all_pending:
        st.info("No pending role requests found.")
        return
    h1, h2, h3, h4 = st.columns([3, 3, 2, 2])
    h1.markdown("**Role**")
    h2.markdown("**Scope**")
    h3.markdown("**Tenant**")
    h4.markdown("**Status**")
    st.divider()
    for row in _all_pending:
        status = row.get("status", "")
        c1, c2, c3, c4 = st.columns([3, 3, 2, 2])
        role = row.get("role_name") or row.get("role_definition_id", "—").split("/")[-1]
        c1.markdown(f"**{role}**")
        c2.text(row.get("scope_display") or "—")
        c3.caption(row.get("_tenant_label", ""))
        icon = "🟡" if "Pending" in status or "Provisioning" in status else "🔴"
        c4.caption(f"{icon} {status}")
        if row.get("failure_reason"):
            st.caption(f"  ↳ {row['failure_reason']}")


# ── Resource detail panels ────────────────────────────────────────────────────

@st.fragment(run_every="30s")
def _render_activity_log(resource_id: str, sub_id: str, tenant_id: str) -> None:
    st.caption(f"Auto-refreshes every 30s · Last: {datetime.now().strftime('%H:%M:%S')}")
    col_h, col_dl = st.columns([8, 2])
    col_h.markdown("##### Activity Log (last 24h)")
    try:
        events = logs_svc.get_activity_logs(resource_id, tenant_id=tenant_id, hours=24)
    except PermissionDeniedError as exc:
        st.warning(f"⛔ {exc}")
        return
    except Exception as exc:
        st.error(f"Error loading activity log: {exc}")
        return
    if not events:
        st.info("No activity log entries in the last 24 hours.")
        return
    log_text = "\n".join(
        f"[{e['timestamp']}] {e['level']:8s} | {e['operation']} | {e['status']} | {e['caller']}"
        for e in events
    )
    col_dl.download_button(
        "⬇ Export",
        data=log_text,
        file_name=f"activity_log_{_name_from_id(resource_id)}.txt",
        mime="text/plain",
        key=f"dl_actlog_{resource_id[:20]}",
    )
    for e in events[:100]:
        lvl = e.get("level", "")
        if lvl == "Critical":
            icon = "🔴"
        elif lvl == "Error":
            icon = "🟠"
        elif lvl == "Warning":
            icon = "🟡"
        else:
            icon = "⚪"
        ts = e.get("timestamp", "")[:19].replace("T", " ")
        st.markdown(
            f"`{ts}` {icon} **{e.get('operation', '—')}**"
            f" · {e.get('status', '')} · `{e.get('caller', '')}`"
        )
        if e.get("description"):
            st.caption(f"  {e['description']}")
    if len(events) > 100:
        st.caption(f"Showing 100 of {len(events)} events.")


def _render_container_logs(resource: dict) -> None:
    sub_id = resource.get("_sub_id", "")
    tenant_id = resource.get("_tenant_id", "")
    rg = resource.get("resource_group", "")
    group_name = resource.get("name", "")

    st.markdown("##### Container Logs")

    try:
        containers = logs_svc.get_container_group_containers(sub_id, rg, group_name, tenant_id)
    except PermissionDeniedError as exc:
        st.warning(f"⛔ {exc}")
        return
    except Exception as exc:
        st.error(f"Error fetching containers: {exc}")
        return

    if not containers:
        st.info("No containers found in this container group.")
        return

    selected_container = st.selectbox("Container", containers, key=f"ci_sel_{resource['id'][:20]}")
    tail = st.slider("Lines to fetch", 50, 1000, 200, 50, key=f"ci_tail_{resource['id'][:20]}")

    if st.button("🔄 Fetch Logs", key=f"ci_fetch_{resource['id'][:20]}"):
        try:
            content = logs_svc.get_container_logs(
                sub_id, rg, group_name, selected_container, tenant_id, tail=tail
            )
            st.session_state[f"_ci_log_{resource['id']}"] = content
        except PermissionDeniedError as exc:
            st.warning(f"⛔ {exc}")
        except Exception as exc:
            st.error(f"Error fetching logs: {exc}")

    log_content = st.session_state.get(f"_ci_log_{resource['id']}", "")
    if log_content:
        col_hd, col_dl = st.columns([8, 2])
        col_hd.caption(f"{len(log_content.splitlines())} lines")
        col_dl.download_button(
            "⬇ Export",
            data=log_content,
            file_name=f"{group_name}_{selected_container}.log",
            mime="text/plain",
            key=f"dl_ci_{resource['id'][:20]}",
        )
        st.code(log_content, language=None)


def _render_webapp_logs(resource: dict) -> None:
    sub_id = resource.get("_sub_id", "")
    tenant_id = resource.get("_tenant_id", "")
    rg = resource.get("resource_group", "")
    site_name = resource.get("name", "")

    st.markdown("##### Deployment History")
    try:
        deployments = logs_svc.get_webapp_deployment_logs(sub_id, rg, site_name, tenant_id)
    except PermissionDeniedError as exc:
        st.warning(f"⛔ {exc}")
        return
    except Exception as exc:
        st.error(f"Error loading deployments: {exc}")
        return

    if not deployments:
        st.info("No deployments found.")
        return

    for d in deployments[:20]:
        status = d.get("status", 0)
        icon = "✅" if status == 4 else "❌" if status in (3, 5) else "⏳"
        active_badge = " 🔵 **active**" if d.get("active") else ""
        created = d.get("created", "")[:19].replace("T", " ")
        st.markdown(
            f"{icon} `{created}`{active_badge}  ·  {d.get('message', '—')[:120]}"
        )


def _render_acr_detail(resource: dict) -> None:
    sub_id = resource.get("_sub_id", "")
    tenant_id = resource.get("_tenant_id", "")
    rg = resource.get("resource_group", "")
    registry_name = resource.get("name", "")

    st.markdown("##### Repositories")

    try:
        login_server = acr_svc.get_login_server(sub_id, rg, registry_name, tenant_id)
    except Exception as exc:
        st.error(f"Could not resolve registry endpoint: {exc}")
        return

    st.caption(f"Registry: `{login_server}`")

    if st.button("🔄 Load Repositories", key=f"acr_load_{resource['id'][:20]}"):
        try:
            repos = acr_svc.list_repositories(login_server, tenant_id)
            st.session_state[f"_acr_repos_{resource['id']}"] = repos
            st.session_state.pop(f"_acr_tags_{resource['id']}", None)
        except PermissionDeniedError as exc:
            st.warning(f"⛔ {exc}")
        except Exception as exc:
            st.error(f"Error loading repositories: {exc}")

    repos: list[str] = st.session_state.get(f"_acr_repos_{resource['id']}", [])

    if repos:
        st.caption(f"{len(repos)} repositories")
        selected_repo = st.selectbox(
            "Repository", repos, key=f"acr_repo_{resource['id'][:20]}"
        )

        if st.button("🔄 Load Tags", key=f"acr_tags_btn_{resource['id'][:20]}"):
            try:
                tags = acr_svc.list_tags(login_server, selected_repo, tenant_id)
                st.session_state[f"_acr_tags_{resource['id']}"] = tags
            except PermissionDeniedError as exc:
                st.warning(f"⛔ {exc}")
            except Exception as exc:
                st.error(f"Error loading tags: {exc}")

        tags: list[str] = st.session_state.get(f"_acr_tags_{resource['id']}", [])
        if tags:
            st.caption(f"{len(tags)} tags")
            h1, h2 = st.columns([2, 6])
            h1.markdown("**Tag**")
            h2.markdown("**Pull command**")
            st.divider()
            for tag in tags[:50]:
                c1, c2 = st.columns([2, 6])
                c1.code(tag, language=None)
                c2.code(f"docker pull {login_server}/{selected_repo}:{tag}", language="bash")
            if len(tags) > 50:
                st.caption(f"Showing 50 of {len(tags)} tags.")
    elif f"_acr_repos_{resource['id']}" not in st.session_state:
        st.caption("Click **Load Repositories** to list images in this registry.")


def _render_storage_detail(resource: dict) -> None:
    sub_id = resource.get("_sub_id", "")  # noqa: F841
    tenant_id = resource.get("_tenant_id", "")
    account_name = resource.get("name", "")

    st.markdown("##### Blob Storage")
    st.caption(f"Account: `{account_name}.blob.core.windows.net`")

    if st.button("🔄 Load Containers", key=f"st_load_{resource['id'][:20]}"):
        try:
            containers = storage_svc.list_containers(account_name, tenant_id)
            st.session_state[f"_st_containers_{resource['id']}"] = containers
            st.session_state.pop(f"_st_blobs_{resource['id']}", None)
        except PermissionDeniedError as exc:
            st.warning(f"⛔ {exc}")
        except Exception as exc:
            st.error(f"Error loading containers: {exc}")

    containers: list[dict] = st.session_state.get(f"_st_containers_{resource['id']}", [])

    if not containers and f"_st_containers_{resource['id']}" not in st.session_state:
        st.caption("Click **Load Containers** to browse blob storage.")
        return

    if not containers:
        st.info("No containers found (or access denied).")
        return

    container_names = [c["name"] for c in containers]
    sel_container = st.selectbox("Container", container_names, key=f"st_cont_{resource['id'][:20]}")

    # Browse path state
    browse_key = f"_st_path_{resource['id']}"
    if browse_key not in st.session_state:
        st.session_state[browse_key] = ""

    current_prefix = st.session_state[browse_key]

    # Breadcrumb
    if current_prefix:
        crumb_parts = current_prefix.rstrip("/").split("/")
        crumb_cols = st.columns([1] + [2] * len(crumb_parts))
        if crumb_cols[0].button("📁 /", key=f"crumb_root_{resource['id'][:20]}"):
            st.session_state[browse_key] = ""
            st.session_state.pop(f"_st_blobs_{resource['id']}", None)
            st.rerun()
        for idx, part in enumerate(crumb_parts):
            if crumb_cols[idx + 1].button(
                f"📁 {part}", key=f"crumb_{idx}_{resource['id'][:20]}"
            ):
                st.session_state[browse_key] = "/".join(crumb_parts[: idx + 1]) + "/"
                st.session_state.pop(f"_st_blobs_{resource['id']}", None)
                st.rerun()

    if st.button("🔄 List", key=f"st_list_{resource['id'][:20]}"):
        try:
            result = storage_svc.list_blobs(
                account_name, sel_container, prefix=current_prefix, tenant_id=tenant_id
            )
            st.session_state[f"_st_blobs_{resource['id']}"] = result
        except PermissionDeniedError as exc:
            st.warning(f"⛔ {exc}")
        except Exception as exc:
            st.error(f"Error listing blobs: {exc}")

    blob_result: dict | None = st.session_state.get(f"_st_blobs_{resource['id']}")
    if blob_result is None:
        return

    prefixes = blob_result.get("prefixes", [])
    blobs = blob_result.get("blobs", [])

    # Virtual directories
    for vdir in prefixes:
        col_icon, col_name = st.columns([0.3, 9])
        col_icon.write("📁")
        if col_name.button(vdir, key=f"vdir_{vdir}_{resource['id'][:20]}"):
            st.session_state[browse_key] = vdir
            st.session_state.pop(f"_st_blobs_{resource['id']}", None)
            st.rerun()

    # Blobs
    if blobs:
        for blob in blobs[:200]:
            c_icon, c_name, c_size, c_mod, c_dl = st.columns([0.3, 5, 1.5, 2, 1])
            c_icon.write("📄")
            c_name.code(blob["name"].split("/")[-1], language=None)
            c_size.caption(storage_svc._fmt_size(blob["size"]))
            c_mod.caption(blob.get("last_modified", "")[:16])
            if c_dl.button("⬇", key=f"dl_{blob['name']}_{resource['id'][:20]}", help="Download"):
                try:
                    data = storage_svc.download_blob(
                        account_name, sel_container, blob["name"], tenant_id
                    )
                    st.session_state[f"_dl_data_{blob['name']}"] = data
                    st.session_state[f"_dl_name_{blob['name']}"] = blob["name"].split("/")[-1]
                except PermissionDeniedError as exc:
                    st.warning(f"⛔ {exc}")
                except Exception as exc:
                    st.error(f"Download failed: {exc}")

            # Show download button if data was fetched
            cached_data = st.session_state.get(f"_dl_data_{blob['name']}")
            if cached_data is not None:
                st.download_button(
                    f"Save {blob['name'].split('/')[-1]}",
                    data=cached_data,
                    file_name=st.session_state.get(f"_dl_name_{blob['name']}", "file"),
                    key=f"save_{blob['name']}_{resource['id'][:20]}",
                )

        if len(blobs) > 200:
            st.caption(f"Showing 200 of {len(blobs)} blobs. Navigate into directories for more.")
    elif not prefixes:
        st.info("This container is empty.")


def _render_resource_detail(resource: dict) -> None:
    """Render the detail panel for a selected resource."""
    rtype = resource.get("type", "").lower()
    name = resource.get("name", "")
    icon = _resource_icon(rtype)
    resource_id = resource.get("id", "")
    tenant_id = resource.get("_tenant_id", "")

    col_hd, col_portal, col_close = st.columns([7, 2, 1])
    col_hd.markdown(f"### {icon} {name}")
    col_hd.caption(
        f"{resource.get('type', '')}  ·  "
        f"{resource.get('resource_group', '')}  ·  {resource.get('location', '')}"
    )
    col_portal.link_button(
        "Open in Portal ↗",
        _portal_url(tenant_id, resource_id),
        use_container_width=True,
    )
    if col_close.button("✕", key="close_detail", help="Close detail panel"):
        del st.session_state["detail_resource"]
        st.rerun()

    # Determine which tabs to show
    extra_tabs: list[str] = []
    if rtype == "microsoft.storage/storageaccounts":
        extra_tabs.append("Storage")
    elif rtype == "microsoft.containerregistry/registries":
        extra_tabs.append("Registry")
    elif rtype in ("microsoft.containerinstance/containergroups",):
        extra_tabs.append("Container Logs")
    elif rtype in ("microsoft.web/sites", "microsoft.web/sites/slots"):
        extra_tabs.append("Deployments")

    tab_labels = ["Activity Log"] + extra_tabs
    tabs = st.tabs(tab_labels)

    with tabs[0]:
        _render_activity_log(resource_id, resource.get("_sub_id", ""), tenant_id)

    if extra_tabs:
        with tabs[1]:
            if rtype == "microsoft.storage/storageaccounts":
                _render_storage_detail(resource)
            elif rtype == "microsoft.containerregistry/registries":
                _render_acr_detail(resource)
            elif rtype == "microsoft.containerinstance/containergroups":
                _render_container_logs(resource)
            elif rtype in ("microsoft.web/sites", "microsoft.web/sites/slots"):
                _render_webapp_logs(resource)


# ── Auth gate ─────────────────────────────────────────────────────────────────

if "account" not in st.session_state:
    st.session_state.account = az_cli.get_account()

if not st.session_state.account:
    st.title("🌉 BlueBridge")
    st.markdown("#### Azure PIM Access Manager")
    st.markdown("Sign in with your Microsoft account to view and activate PIM roles.")
    st.divider()

    if not az_cli.check_az_installed():
        st.error(
            "Azure CLI not found on PATH. "
            "Install it from https://aka.ms/install-azure-cli and restart."
        )
        st.stop()

    if st.button("🔑 Sign in with Microsoft", type="primary"):
        with st.spinner("Opening browser for authentication…"):
            try:
                az_cli.login()
                st.session_state.account = az_cli.get_account()
                st.rerun()
            except az_cli.AzCliError as exc:
                st.error(f"Login failed: {exc}")
    st.stop()

# ── Load tenants & subscriptions (once per session) ───────────────────────────

if "tenants" not in st.session_state:
    with st.spinner("Loading tenants…"):
        tenants, subscriptions = load_tenants_and_subscriptions()
        st.session_state.tenants = tenants
        st.session_state.subscriptions = subscriptions

# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("### 🌉 BlueBridge")

    account = st.session_state.account
    upn = account.get("user", {}).get("name") or account.get("name", "")
    st.caption(f"Signed in as **{upn}**")
    st.divider()

    tenants: list[dict] = st.session_state.tenants
    tenant_options = {t["tenantId"]: _tenant_label(t) for t in tenants}

    if not tenant_options:
        st.warning("No tenants found.")
        selected_tenant_ids: list[str] = []
    else:
        selected_tenant_ids = st.multiselect(
            "Tenants",
            options=list(tenant_options.keys()),
            default=list(tenant_options.keys()),
            format_func=lambda tid: tenant_options.get(tid, tid),
        )

    st.divider()
    col_refresh, col_signout = st.columns(2)
    with col_refresh:
        if st.button("🔄 Refresh", use_container_width=True):
            for tid in selected_tenant_ids:
                pim.clear_cache(tid)
                clear_token_cache(tid)
            pim.clear_resources_cache()
            st.rerun()
    with col_signout:
        if st.button("🚪 Sign out", use_container_width=True):
            az_cli.logout()
            pim.clear_cache()
            pim.clear_resources_cache()
            clear_token_cache()
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

# ── Main area ─────────────────────────────────────────────────────────────────

st.title("🌉 BlueBridge")
st.markdown("Azure PIM Access Manager")

if not selected_tenant_ids:
    st.info("Select one or more tenants in the sidebar.")
    st.stop()

st.session_state["_selected_tids"] = selected_tenant_ids

# Load PIM data (cached)
with st.spinner("Loading PIM data…"):
    all_eligible: list[dict] = []
    all_active: list[dict] = []
    all_pending: list[dict] = []
    load_errors: list[str] = []

    for tid in selected_tenant_ids:
        try:
            data = _load_pim_for_tenant(tid)
            all_eligible.extend(data["eligible"])
            all_active.extend(data["active"])
            all_pending.extend(data["pending"])
        except Exception as exc:
            load_errors.append(f"{tenant_options.get(tid, tid)}: {exc}")

for err in load_errors:
    st.warning(f"Could not load tenant — {err}")

tab_eligible, tab_active, tab_pending, tab_resources = st.tabs([
    f"Eligible ({len(all_eligible)})",
    f"Active ({len(all_active)})",
    f"Pending ({len(all_pending)})",
    "Resources",
])

# ── Eligible tab ──────────────────────────────────────────────────────────────

with tab_eligible:
    if not all_eligible:
        st.info("No eligible role assignments found.")
    else:
        col_sa, col_cl, _sp = st.columns([1, 1, 10])
        if col_sa.button("Select All", key="sel_all"):
            for _i in range(len(all_eligible)):
                st.session_state[f"_chk_{_i}"] = True
        if col_cl.button("Clear", key="clr_all"):
            for _i in range(len(all_eligible)):
                st.session_state[f"_chk_{_i}"] = False

        h0, h1, h2, h3, h4 = st.columns([0.5, 3, 3, 2, 2])
        h0.markdown("**✓**")
        h1.markdown("**Role**")
        h2.markdown("**Scope**")
        h3.markdown("**Tenant**")
        h4.markdown("**Eligible until**")
        st.divider()

        selected_indices: list[int] = []
        for _i, row in enumerate(all_eligible):
            c0, c1, c2, c3, c4 = st.columns([0.5, 3, 3, 2, 2])
            if c0.checkbox("", key=f"_chk_{_i}", label_visibility="collapsed"):
                selected_indices.append(_i)
            c1.markdown(f"**{row.get('role_name') or '—'}**")
            c2.text(row.get("scope_display") or "—")
            c3.caption(row.get("_tenant_label", ""))
            c4.caption(row.get("expires_relative", "—"))

        st.divider()
        n = len(selected_indices)
        col_j, col_d, col_b = st.columns([5, 2, 2])
        justification = col_j.text_input(
            "Justification", placeholder="Reason for activation…", key="bulk_just"
        )
        duration = col_d.selectbox(
            "Duration", [1, 2, 4, 8], format_func=lambda h: f"{h}h", index=1, key="bulk_dur"
        )
        btn_label = f"⚡ Activate {n}" if n > 0 else "⚡ Activate"
        activate_clicked = col_b.button(
            btn_label, type="primary", disabled=(n == 0),
            key="activate_btn", use_container_width=True,
        )

        if n == 0:
            st.caption("Check boxes above, then enter justification and click Activate.")

        if activate_clicked:
            if not justification.strip():
                st.error("Justification is required.")
            else:
                selected_rows = [all_eligible[_i] for _i in selected_indices]
                ok_count = 0
                fail_count = 0

                with st.status(f"Activating {n} role(s)…", expanded=True) as status_box:
                    with concurrent.futures.ThreadPoolExecutor(max_workers=min(n, 8)) as executor:
                        def _make_future(row: dict) -> Any:
                            scope = row.get("scope", "")
                            parts = scope.strip("/").split("/")
                            sub_id = parts[1] if len(parts) >= 2 else ""
                            return executor.submit(
                                arm.activate_role,
                                subscription_id=sub_id,
                                request_name=str(uuid.uuid4()),
                                role_definition_id=row["role_definition_id"],
                                principal_id=row["principal_id"],
                                scope=scope,
                                justification=justification.strip(),
                                duration_hours=int(duration),
                                tenant_id=row.get("_tenant_id", ""),
                            )
                        futures = {_make_future(r): r for r in selected_rows}
                        for future in concurrent.futures.as_completed(futures):
                            row = futures[future]
                            role = row.get("role_name", "?")
                            try:
                                future.result()
                                status_box.write(f"✅ **{role}** — activation requested")
                                ok_count += 1
                            except Exception as exc:
                                status_box.write(f"❌ **{role}** — {exc}")
                                fail_count += 1

                    summary = f"{ok_count} succeeded"
                    if fail_count:
                        summary += f", {fail_count} failed"
                    status_box.update(
                        label=f"Done — {summary}",
                        state="complete" if fail_count == 0 else "error",
                    )

                for row in selected_rows:
                    pim.clear_cache(row.get("_tenant_id", ""))

                if ok_count > 0:
                    st.rerun()

# ── Active tab ────────────────────────────────────────────────────────────────

with tab_active:
    _active_tab_content()

# ── Pending tab ───────────────────────────────────────────────────────────────

with tab_pending:
    _pending_tab_content()

# ── Resources tab ─────────────────────────────────────────────────────────────

with tab_resources:
    st.markdown("#### Azure Resources")

    all_subs = st.session_state.subscriptions
    sub_options: dict[str, str] = {}
    sub_tenant_map: dict[str, str] = {}
    for s in all_subs:
        tid = s.get("tenantId") or s.get("homeTenantId", "")
        if tid not in selected_tenant_ids:
            continue
        raw_id = s.get("id") or s.get("subscriptionId", "")
        sub_id = raw_id.lstrip("/").removeprefix("subscriptions/")
        sub_name = s.get("displayName") or s.get("name") or sub_id
        if sub_id and sub_id not in sub_options:
            sub_options[sub_id] = sub_name
            sub_tenant_map[sub_id] = tid

    if not sub_options:
        st.info("No subscriptions available for selected tenants.")
    else:
        sel_sub_id = st.selectbox(
            "Subscription",
            options=list(sub_options.keys()),
            format_func=lambda sid: sub_options.get(sid, sid),
            key="resources_sub",
        )
        sub_tenant_id = sub_tenant_map.get(sel_sub_id, "")

        with st.spinner("Loading resources…"):
            try:
                resources = pim.load_resources(sel_sub_id, sub_tenant_id)
            except Exception as exc:
                st.error(f"Failed to load resources: {exc}")
                resources = []

        if not resources:
            st.info("No resources found in this subscription.")
        else:
            # ── Filters ───────────────────────────────────────────────────────
            fc1, fc2, fc3, fc4 = st.columns([3, 2, 2, 2])
            search = fc1.text_input("🔍 Search by name", placeholder="…", key="res_search")
            all_rgs = sorted({r["resource_group"] for r in resources if r["resource_group"]})
            all_types = sorted({r["type_short"] for r in resources if r["type_short"]})
            all_locs = sorted({r["location"] for r in resources if r["location"]})
            sel_rgs = fc2.multiselect("Resource Group", all_rgs, key="res_rg")
            sel_types = fc3.multiselect("Type", all_types, key="res_type")
            sel_locs = fc4.multiselect("Location", all_locs, key="res_loc")

            filtered = resources
            if search:
                sl = search.lower()
                filtered = [r for r in filtered if sl in r["name"].lower()]
            if sel_rgs:
                filtered = [r for r in filtered if r["resource_group"] in sel_rgs]
            if sel_types:
                filtered = [r for r in filtered if r["type_short"] in sel_types]
            if sel_locs:
                filtered = [r for r in filtered if r["location"] in sel_locs]

            st.caption(f"{len(filtered)} of {len(resources)} resources")

            # ── Table header ──────────────────────────────────────────────────
            th0, th1, th2, th3, th4, th5, th6 = st.columns([0.4, 3, 2.5, 2.5, 1.5, 0.8, 0.8])
            th0.markdown("**·**")
            th1.markdown("**Name**")
            th2.markdown("**Type**")
            th3.markdown("**Resource Group**")
            th4.markdown("**Location**")
            th5.markdown("**Portal**")
            th6.markdown("**Details**")
            st.divider()

            for r in filtered[:500]:
                c0, c1, c2, c3, c4, c5, c6 = st.columns([0.4, 3, 2.5, 2.5, 1.5, 0.8, 0.8])
                c0.write(_resource_icon(r["type"]))
                c1.markdown(f"**{r['name']}**")
                c2.caption(r.get("type_short", ""))
                c3.caption(r.get("resource_group", ""))
                c4.caption(r.get("location", ""))
                c5.markdown(f"[↗]({_portal_url(sub_tenant_id, r['id'])})")

                btn_key = f"view_{r['id'][:40]}"
                if c6.button("▶", key=btn_key, help="View details"):
                    r_with_meta = dict(r)
                    r_with_meta["_sub_id"] = sel_sub_id
                    r_with_meta["_tenant_id"] = sub_tenant_id
                    st.session_state["detail_resource"] = r_with_meta
                    st.rerun()

            if len(filtered) > 500:
                st.caption(f"Showing first 500 of {len(filtered)}. Use filters to narrow results.")

        # ── Resource detail panel ─────────────────────────────────────────────
        if st.session_state.get("detail_resource"):
            st.divider()
            _render_resource_detail(st.session_state["detail_resource"])
