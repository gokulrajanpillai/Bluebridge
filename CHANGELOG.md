# Changelog

All notable changes to BlueBridge are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased]

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
