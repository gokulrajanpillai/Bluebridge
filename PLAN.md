# BlueBridge — Azure Navigator Desktop App

A contemporary, elegant, OS-agnostic desktop application built with **Flet (Python)** that helps users navigate Azure content faster than the portal, powered by **az CLI** for authentication and direct **ARM REST** calls for data.

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────┐
│  Flet UI (Python)                           │
│  ┌──────────┐ ┌──────────┐ ┌─────────────┐  │
│  │ Landing/ │ │ Access   │ │ Resources   │  │
│  │ Login    │ │ Tab      │ │ Tab         │  │
│  └──────────┘ └──────────┘ └─────────────┘  │
├─────────────────────────────────────────────┤
│  Service layer (async, cached)              │
│  auth_service · pim_service · arm_service   │
├─────────────────────────────────────────────┤
│  az CLI subprocess wrapper + ARM REST calls │
│  (az login / az account / az rest)          │
└─────────────────────────────────────────────┘
```

### Key decisions

- **Auth via az CLI, data via ARM REST.** `az login` opens the system browser for SSO; `az account get-access-token` mints tokens. All list/read/write operations call ARM REST directly with `httpx` using the cached token — ~10x faster than shelling out to `az` per call, and parallelizable. `az rest` remains the fallback for awkward endpoints.
- **Fully async.** All subprocess and HTTP work runs via `asyncio`; the UI thread is never blocked. Background refresh updates the UI subtly (no full-page spinners after first load — stale data stays visible while fresh data loads, then swaps in).
- **Tenant switching is first-class.** The app tracks the active tenant, supports `az login --tenant <id>`, and re-scopes tokens, subscriptions, and caches on switch.
- **PIM activation handles all states**, including `PendingApproval`, `Provisioning`, `Denied`, and `Failed` — with background polling until terminal state.

### Project layout

```
bluebridge/
├── main.py                  # flet entry point, routing
├── app/
│   ├── theme.py             # colors, typography, spacing tokens
│   ├── state.py             # app-wide state (tenant, account, caches)
│   ├── services/
│   │   ├── az_cli.py        # async subprocess wrapper (login, token, account)
│   │   ├── auth.py          # token cache, refresh, tenant management
│   │   ├── arm.py           # httpx client for ARM REST (subs, RGs, resources)
│   │   └── pim.py           # PIM eligible/active assignments + activation + polling
│   ├── views/
│   │   ├── landing.py       # SSO login page
│   │   ├── shell.py         # app bar + tenant switcher + tab container
│   │   ├── access_view.py   # subscriptions dropdown + role table + activation bar
│   │   └── resources_view.py# hierarchical tree + search/filter
│   └── components/
│       ├── data_table.py    # reusable styled table
│       ├── status_chip.py   # Eligible/Active/Pending/Denied pills
│       ├── tree_node.py     # lazy expandable resource node
│       ├── tenant_picker.py # tenant dropdown in app bar
│       └── toast.py         # snackbar notifications
├── assets/                  # icons, logo, fonts (Inter)
└── pyproject.toml
```

---

## 2. Phase 1 — Foundation & Auth (landing page)

1. **Scaffold**: `flet create`, window defaults (1280×820, min size), load theme.
2. **`az_cli.py`** — async subprocess wrapper (`asyncio.create_subprocess_exec`, never blocking):
   - `check_az_installed()` → friendly error screen with install link if missing
   - `login(tenant: str | None)` → runs `az login [--tenant X]` (opens system browser for SSO), parses JSON result
   - `get_token(resource, tenant)` → cached per-tenant with expiry check and silent refresh
   - `get_account()` / `list_accounts()` / `list_tenants()` → identity, subscriptions, available tenants
3. **Landing view**: centered card — logo, app name, prominent "Sign in with Microsoft" button, subtle gradient background. Click → spinner + "Complete sign-in in your browser…", await `az login`, route to shell. Handle: already-logged-in on launch (skip to shell via `az account show`), login cancelled, az not installed.
4. **Routing**: `page.route` based — `/login`, `/app`.

---

## 3. Phase 2 — App Shell & Tenant Switching

- Top app bar: app icon + name, signed-in identity with presence dot; right side: "Updated HH:MM:SS", Refresh, Sign out, Dark/Light toggle.
- **Tenant switcher** in the app bar: dropdown of tenants from `az account tenant list` (fallback: distinct tenants across `az account list`). On switch:
  1. If no cached credential for that tenant → run `az login --tenant <id>` (browser SSO).
  2. Invalidate token + data caches for old tenant scope.
  3. Reload subscriptions, reset selected subscription, refresh both tabs in background.
  4. Tenant shown next to identity; persisted as last-used in settings.
- `ft.Tabs` (or custom segmented control) for **Access** / **Resources**.
- Status bar at bottom: row counts, auto-refresh countdown.
- Global state object: tenant, account, tokens, selected subscription, caches.

---

## 4. Phase 3 — Access Tab (PIM)

1. **Subscription dropdown** — `GET /subscriptions` (ARM), shows `name — id`, persists last selection per tenant.
2. **PIM data** (ARM PIM APIs):
   - Eligible: `roleEligibilityScheduleInstances?$filter=asTarget()`
   - Active: `roleAssignmentScheduleInstances?$filter=asTarget()`
   - Pending requests: `roleAssignmentScheduleRequests?$filter=asRequestor()` — to surface approval-pending activations
   - Resolve role definition names + scope display names; "Via: Group" from `memberType`.
3. **Table**: checkbox column, Status chip, Role, Resource, Via, Expires (relative `in 475h 48m` + absolute), Auto-renew toggle.
4. **Left filter rail**: Active/Eligible/Pending checkboxes with counts, "Hide duplicates", shortcuts legend (click status → select, click Renew → toggle, right-click → deactivate).
5. **Bottom action bar**: Justification field, Duration dropdown (1–8h), selected count, Select All, prominent **Activate** button → `PUT roleAssignmentScheduleRequests` per selected role.
6. **Activation state machine** (per request, non-blocking):

   ```
   Submitted → Provisioning → Provisioned (Active)        ✅ green chip
             → PendingApproval → Approved → Provisioned   🟡 amber chip while pending
                               → Denied                   🔴 red chip + reason
             → Failed (e.g. justification policy, MFA)    🔴 red chip + actionable error
   ```

   - After submit, each row enters an in-flight state with a subtle progress indicator.
   - A background `asyncio` poller checks request status every ~10s until terminal, updating only the affected rows (no table reload, no UI block).
   - Approval-pending rows persist across refreshes (re-derived from `asRequestor()` query) so state survives restarts.
   - Toast per terminal transition (activated / denied / failed with reason).
7. **Refresh behavior**: auto-refresh timer (default 1h, configurable) + manual Refresh. All refreshes are background tasks — current data stays on screen, a slim progress bar under the app bar indicates activity, rows diff-update in place.

---

## 5. Phase 4 — Resources Tab

1. **Data**: per selected subscription — `GET /resourcegroups` + `GET /resources` (paginated, parallel per sub). Hierarchy: **Subscription → Resource Group → Resource type → Resource**.
2. **Tree UI**: lazy-expanding nodes, resource-type icons (storage, key vault, app service, SQL, …), counts on group nodes.
3. **Search**: debounced text field filtering the whole tree — auto-expands matching branches, highlights matched text.
4. **Filters**: resource type multi-select, location, tag key/value.
5. **Row actions**: **Open in Azure Portal** (deep-link `https://portal.azure.com/#@{tenant}/resource{resourceId}` — the "navigate faster" killer feature), copy resource ID, copy name.
6. In-memory cache with TTL per tenant+subscription; skeleton loaders on first load, silent background refresh afterwards.

---

## 6. Phase 5 — Polish ("screams professionalism")

- **Theme** (`theme.py`): design tokens, dark-first — near-black navy surfaces (`#0d1117` / `#161b22`), single azure-blue accent (`#3b82f6`), green reserved for success/Activate, amber for pending, 8px spacing grid. Light theme variant.
- **Typography**: bundle Inter via `page.fonts`; sizes 12/13 table, 14 body, 20 titles.
- **Micro-interactions**: row hover states, animated tab transitions (`AnimatedSwitcher`), skeleton shimmer, toasts for every action result, slim top progress bar for background refreshes.
- **Empty/error states**: designed, not blank — "No eligible roles in this subscription" with icon.
- **Keyboard**: Ctrl+F focus search, Ctrl+R refresh, right-click context menus.

---

## 7. Phase 6 — Packaging & Hardening

- `flet build windows` (and macos/linux) → standalone app with icon.
- App never writes tokens to disk (az CLI manages its own cache).
- Structured logging to local file; global exception handler → error toast.
- Settings file (`%APPDATA%/BlueBridge/settings.json`): theme, last tenant, last subscription per tenant, refresh interval.

---

## 8. Build Order & Effort

| Step | Deliverable | Effort |
|---|---|---|
| 1 | Scaffold + theme + landing page with working `az login` | ~1 day |
| 2 | Shell, tabs, tenant switcher, subscription dropdown | ~1 day |
| 3 | Access tab read-only (eligible/active/pending lists) | ~1–2 days |
| 4 | PIM activation flow + state polling | ~1–1.5 days |
| 5 | Resources tree + search/filter + portal deep-links | ~2 days |
| 6 | Polish, theming, packaging | ~1–2 days |

---

## 9. Confirmed Requirements

- ✅ PIM activation handles all states incl. approval-pending, with background polling
- ✅ All refreshes are subtle and non-blocking (diff-update rows, slim progress indicator, stale-while-revalidate)
- ✅ Tenant switching supported (per-tenant login, token, and cache scoping)
- ✅ No mobile target; Windows/macOS/Linux desktop only
- ✅ Pure Python stack (Flet)
