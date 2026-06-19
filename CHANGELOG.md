# Changelog

All notable changes to BlueBridge are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased]

## [0.7.2] — 2026-06-19

### Changed
- PyInstaller build switched from `--onedir` to `--onefile` — Windows/Linux releases are now a single portable executable with no `_internal` folder required alongside it
- `build.py` no longer requires Python 3.11+ (`tomllib` replaced with a stdlib regex parse of `pyproject.toml`)
- `requires-python` relaxed to `>=3.10` to match runtime compatibility

## [0.7.1] — 2026-06-18

### Fixed
- Removed duplicate `streamlit>=1.35.0` dependency entry in `pyproject.toml` introduced during merge

### Changed
- `README.md` rewritten to reflect the Streamlit-based architecture, PyInstaller packaging, and the full feature set introduced in 0.7.0 (resource detail panel, bulk PIM activation, activity log, storage/registry/container/deployment tabs)
- Removed stale Flet-era content from `[Unreleased]` section of changelog

## [0.7.0] — 2026-06-13

### Added
- Full rewrite of frontend from Flet to Streamlit — zero native-framework dependency
- Cross-platform PyInstaller packaging via `build.py [windows|macos|linux]`
- `launcher.py` auto-opens the system browser 3 s after server binds
- Updated GitHub Actions: CI runs `ruff check`; Release builds all three platforms in parallel via PyInstaller and publishes a GitHub Release
- **Resources tab** — lists all accessible resources with name, type, resource group, location and a direct Azure Portal deep-link per resource; searchable and filterable by RG, type and location
- **Resource detail panel** — click ▶ on any resource to open an inline detail view
  - Activity Log tab (auto-refreshes every 30 s) with 24 h history and plain-text export
  - Storage tab for `Microsoft.Storage/storageAccounts` — list containers, browse virtual directories, preview blob metadata, one-click download
  - Registry tab for `Microsoft.ContainerRegistry/registries` — list repos, list tags, copy `docker pull` command per image
  - Container Logs tab for `Microsoft.ContainerInstance/containerGroups` — fetch stdout/stderr with configurable tail, plain-text export
  - Deployments tab for `Microsoft.Web/sites` — deployment history with status icons
  - Permission-denied errors surface actionable role hints (e.g. "Storage Blob Data Reader required") rather than raw HTTP 403s
- **Bulk PIM activation** — checkbox-select multiple eligible roles, shared justification + duration, parallel activation via `ThreadPoolExecutor`; live per-role status via `st.status`
- **Active tab** auto-refreshes every 60 s using `st.fragment`
- **Pending tab** auto-refreshes every 30 s using `st.fragment`

### Changed
- `build.py` replaces the old Flet-based build script; uses `os.pathsep` for cross-platform `--add-data`
- `launcher.py` opens the browser automatically — no more manual URL copy

### Removed
- All Flet UI code (`app/views/`, `app/components/`, `app/theme.py`, `app/state.py`, `app/settings.py`, `main.py`, `tasks.py`, `.devcontainer/`)

## [0.6.0] — 2026-06-10

### Added
- `build.py` — helper script wrapping `flet build` for Windows / macOS / Linux with project metadata
- `assets/` directory with README explaining font and icon placement
- `pyproject.toml` version bumped to 0.5.0, added `[tool.flet]` metadata block and `bluebridge` entry-point script
- `.gitignore` already excludes `build/` output

## [0.5.0] — 2026-06-10

### Added
- Settings persistence (`app/settings.py`) — stores dark mode, last tenant, last subscription per tenant, refresh interval in platform-appropriate config dir (`%APPDATA%/BlueBridge/settings.json` on Windows)
- Auto-refresh loop in `main.py` — fires `page.pubsub.send_all("refresh")` on configurable interval (default 60 min), triggering background reload in both tabs
- Structured file logging — writes to `%APPDATA%/BlueBridge/bluebridge.log` alongside stdout
- Global page error handler — surfaces unhandled exceptions as error toasts instead of silent crashes
- Settings persist on window close and on sign-out / tenant switch
- Theme preference saved immediately on toggle
- Keyboard handler chain in Resources tab — Ctrl+F focuses search without clobbering shell's Ctrl+R

## [0.4.0] — 2026-06-10

### Added
- Tree node component (`app/components/tree_node.py`) — lazy-expanding nodes with resource-type icons, match highlighting, depth-based indentation, and portal open action
- Full Resources tab (`app/views/resources_view.py`):
  - Independent subscription picker
  - Hierarchical tree: subscription → resource group → resource type → resource
  - Debounced search with auto-expand of matching branches and text highlighting
  - Side filter panel: resource type multi-select, location multi-select (up to 30 per category)
  - Azure Portal deep-link on each resource node (`https://portal.azure.com/#@{tenant}/resource{id}`)
  - Per-tenant+subscription in-memory cache; Ctrl+F to focus search
  - Pubsub subscription for shell-level refresh signals

## [0.3.0] — 2026-06-10

### Added
- PIM service (`app/services/pim.py`) — loads and normalises eligible, active, and pending role assignments; relative and absolute expiry formatting; per-tenant+subscription cache
- Status chip component (`app/components/status_chip.py`) — colour-coded pills for Active / Eligible / PendingApproval / Provisioning / Denied / Failed
- Full Access tab (`app/views/access_view.py`):
  - Subscription dropdown with auto-select of first enabled subscription
  - Tabular role list: Status chip, Role, Resource, Via, Expires (relative + absolute)
  - Left filter rail: Active / Eligible / Pending checkboxes with live counts, Hide duplicates
  - Bottom action bar: Justification field, Duration dropdown (1–8h), selected count, "Select eligible", Activate button
  - Per-row "Activate" quick-action button for eligible roles
  - Full activation flow with in-row Provisioning status and background polling every 10s
  - Pubsub subscription for shell-level refresh signals

## [0.2.0] — 2026-06-10

### Added
- ARM REST client (`app/services/arm.py`) — async httpx client with pagination, token injection, subscriptions, resource groups, resources, PIM eligible/active/pending/activate endpoints
- Full app shell (`app/views/shell.py`) — top app bar with identity presence dot, tenant switcher dropdown, last-updated timestamp, refresh, theme toggle, sign-out; `ft.Tabs` for Access/Resources; slim progress bar for background activity; status bar with subscription count + active tenant
- Tenant switching — re-login via browser SSO if no cached credential, invalidates per-tenant token and data caches, reloads subscriptions
- Ctrl+R keyboard shortcut for refresh
- Tenant picker component (`app/components/tenant_picker.py`)
- Access and Resources tab placeholder views

## [0.1.0] — 2026-06-10

### Added
- Project scaffold: `pyproject.toml`, `.gitignore`, `.gitattributes`
- Design token system (`app/theme.py`) — dark-first, azure-blue accent, 8px spacing grid
- App-wide state singleton (`app/state.py`) — tenant, account, token cache, data caches
- `az_cli.py` — fully async subprocess wrapper: `check_az_installed`, `login`, `logout`, `get_account`, `list_accounts`, `list_tenants`, `get_access_token`
- `auth.py` — token cache with expiry + 5-min refresh buffer, `populate_identity`, `load_tenants_and_subscriptions`, `switch_tenant`
- Landing / sign-in page (`app/views/landing.py`) — centered card, SSO login flow, spinner state, error states (login cancelled, az not installed with install link)
- Toast notification component (`app/components/toast.py`)
- Flet entry point with route-based navigation (`main.py`) — auto-detects existing `az login` session on launch, routes to shell if already signed in
- Stub app shell (`app/views/shell.py`) — placeholder until Phase 2
