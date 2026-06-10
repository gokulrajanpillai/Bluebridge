# Changelog

All notable changes to BlueBridge are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased]

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
