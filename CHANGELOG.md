# Changelog

All notable changes to BlueBridge are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased]

### Added
- `tasks.py` — invoke-based task runner: `run`, `web`, `build`, `build-all`, `lint`, `fmt`, `clean`, `install`
- `invoke` added to `[dev]` extras in `pyproject.toml`
- `.devcontainer/` — VS Code devcontainer with Python 3.12, Azure CLI, ruff/pylance extensions, port 8550 forwarded for `invoke web`, and host `~/.azure` credential cache mounted so you stay logged in
- `.github/workflows/release.yml` — on push of a `v*` tag: builds Windows/macOS/Linux executables in parallel via `flet build`, zips/tars platform artefacts, extracts the matching CHANGELOG entry, and publishes a GitHub Release with all three binaries attached
- `.github/workflows/ci.yml` — runs pre-commit on every push and pull request
- `.pre-commit-config.yaml` — pre-commit hooks: file hygiene (`pre-commit-hooks`), secret scanning (`gitleaks`), lint + format (`ruff`), type checking (`mypy`), security SAST (`bandit`), advanced SAST (`semgrep` with python/secrets/bandit rulesets), conventional commit messages (`commitizen`)
- `pyproject.toml` — ruff rule set expanded (bugbear, comprehensions, simplify, security, annotations), mypy and bandit config sections added; `pre-commit`, `mypy`, `bandit[toml]`, `semgrep` added to dev extras
- `tasks.py` — `invoke install` now installs pre-commit hooks automatically; added `invoke hooks` and `invoke hooks-update`

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
