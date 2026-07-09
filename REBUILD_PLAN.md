# BlueBridge v2 — Rebuild Specification

> **How to use this document:** This is a complete, self-contained specification for rebuilding
> BlueBridge from scratch. Give it to an implementation agent (LLM or human) verbatim. It defines
> the product, architecture, tech stack, API contracts, UI/UX, packaging, testing, and acceptance
> criteria. Where the spec says MUST/SHOULD, treat it as a requirement, not a suggestion.

---

## 1. Product summary

BlueBridge is a **zero-install-friction Azure companion tool** for engineers. It lets a signed-in
user:

1. **Browse their Azure estate** — tenants → subscriptions → resource groups → resources — faster
   than the Azure Portal, with search, filters, and Portal deep-links.
2. **Manage PIM (Privileged Identity Management) role activations** — view eligible/active/pending
   role assignments across all subscriptions, bulk-activate with justification and duration, and
   watch activation status live.
3. **Inspect resources inline** — activity logs, blob storage browsing, container registry repos/
   tags, container logs, app service deployments — without opening the Portal.

### Why a rebuild

The previous version (Streamlit + PyInstaller `--onefile`) failed structurally:

- Frozen Streamlit binaries were huge (~200 MB), slow to start (onefile self-extraction), fragile
  (repeated hidden-import build breaks), and flagged by SmartScreen/Gatekeeper/AV.
- It required Azure CLI to be separately installed and logged in — not actually standalone.
- Streamlit's full-script rerun model produced state bugs (index-keyed checkboxes), slow
  interactions, and aggressive polling that re-fetched all PIM data for all tenants every 30–60 s.
- Tables were simulated with columns; no sorting, virtualization, or hierarchy navigation.

### Non-negotiable product requirements

- **R1 — Platform agnostic:** one artifact per OS (Windows x64/arm64, macOS universal or
  x64+arm64, Linux x64/arm64), no runtime prerequisites (no Python, no Azure CLI, no .NET).
- **R2 — Works on first run:** download → run → sign in with Microsoft → see data. Under 5 seconds
  from launch to sign-in screen.
- **R3 — Estate browsing:** first-class tenant / subscription / resource group / resource
  navigation (new capability, detailed in §6).
- **R4 — PIM parity:** everything the old app did for PIM (eligible/active/pending, bulk
  activation, live status) must still work.
- **R5 — Professional UX:** real data tables, real navigation, designed empty/error/loading
  states. Detailed in §7.

---

## 2. Architecture decision

**Chosen architecture: a single static Go binary that embeds a React SPA and serves it on
localhost, opening the user's default browser.**

```
┌──────────────────────────────────────────────────────┐
│  BlueBridge binary (Go, ~15–25 MB, static)           │
│                                                      │
│  ┌────────────────┐      ┌─────────────────────────┐ │
│  │ embed.FS       │      │ REST API (/api/v1/...)  │ │
│  │ React SPA      │◄────►│ chi or stdlib mux       │ │
│  │ (built assets) │      └───────────┬─────────────┘ │
│  └────────────────┘                  │               │
│                          ┌───────────▼─────────────┐ │
│                          │ Service layer           │ │
│                          │ auth · graph · arm ·    │ │
│                          │ pim · storage · acr ·   │ │
│                          │ logs                    │ │
│                          └───────────┬─────────────┘ │
│                          ┌───────────▼─────────────┐ │
│                          │ azidentity (MSAL)       │ │
│                          │ + net/http ARM client   │ │
│                          └─────────────────────────┘ │
└──────────────────────────────┬───────────────────────┘
                               │ HTTPS
             Azure ARM · Azure Resource Graph · Entra ID
```

### Why this and not the alternatives

| Option | Verdict |
|---|---|
| **Go binary + embedded SPA (chosen)** | `go build` produces a truly static single file per OS/arch; cross-compiles from any machine; starts in <1 s; no runtime deps; auth via MSAL libraries removes the Azure CLI prerequisite. |
| Python (any framework) + PyInstaller | Rejected — this is the failure mode being escaped. Python freezing is inherently fragile. |
| Electron | Rejected — 150 MB+ artifacts, heavy memory, needs installers per platform. |
| Tauri 2 | Viable, but adds Rust toolchain + WebView runtime variance (WebView2 on Win, WebKitGTK on Linux) and code-signing pressure. The browser-serving Go approach sidesteps all of it. |
| Hosted web app (SPA + Entra app registration) | The best long-term answer for a team **if** someone can create an Entra app registration and grant admin consent. Kept as a documented future path (§12) — the SPA built here is deliberately reusable for it. |

### Key architectural rules

- **A1 — Auth is native, not shelled out.** Use the Azure SDK for Go's `azidentity` package.
  Credential chain, in order:
  1. `InteractiveBrowserCredential` — opens system browser, localhost redirect, PKCE. Use the
     well-known Azure CLI public client ID (`04b07795-8ddb-461a-bbee-02f9e1bf7b46`) so **no tenant
     app registration is required**.
  2. `DeviceCodeCredential` fallback (headless / SSH / browser-launch failure) — show the code and
     verification URL in the UI.
  3. Optional "reuse Azure CLI login" (`AzureCLICredential`) if `az` happens to be present — a
     convenience, never a requirement.
  - Enable MSAL **persistent token cache** (`azidentity/cache`) so sign-in survives restarts.
    Tokens are cached encrypted via OS facilities (DPAPI / Keychain / kernel keyring). Never write
    raw tokens to disk yourself.
  - **Known constraint:** the Keychain accessor backing `azidentity/cache` on macOS
    (`microsoft-authentication-extensions-for-go/cache`) is built with `//go:build darwin && cgo`
    — it requires cgo. Linux (kernel keyring) and Windows (DPAPI) accessors do not. This means
    darwin binaries cannot be cross-compiled `CGO_ENABLED=0` from Linux like the other four
    targets; they must build natively on a macOS runner with `CGO_ENABLED=1` (see `make
    dist-darwin` and the `build-darwin` job in `release.yml`). Confirmed by building all six
    targets locally.
  - Tokens are always requested **per tenant** (authority `https://login.microsoftonline.com/{tenantId}`)
    and per audience (ARM `https://management.azure.com/.default`, Storage
    `https://storage.azure.com/.default`, ACR via its OAuth2 exchange).
- **A2 — Localhost server is locked down.** Bind to `127.0.0.1` on an ephemeral port. Generate a
  random session token at startup, put it in the launch URL fragment; the SPA presents it on every
  API call (`Authorization: Bearer <local-token>`); reject all requests without it. Set
  `Access-Control-Allow-Origin` to the app's own origin only. This prevents other local processes
  or drive-by web pages from driving the API.
- **A3 — All Azure I/O is concurrent and cached.** Fan out per-subscription calls with bounded
  concurrency (errgroup, limit ~8). Cache responses in-memory with TTL (tenants/subscriptions
  15 min, resources 5 min, PIM 60 s) and serve **stale-while-revalidate**: return cached data
  instantly, refresh in background, push updates to the client.
- **A4 — Server pushes, client doesn't poll blindly.** Use SSE (`/api/v1/events`) to push
  PIM-activation status changes and cache-refresh notifications. The client re-fetches only what
  changed. Never re-fetch the world on a timer.
- **A5 — Errors are typed end-to-end.** Every API error response is
  `{ "error": { "code": string, "message": string, "azureCode": string?, "roleHint": string? } }`.
  Map ARM 403s to actionable hints (e.g. `AuthorizationFailed` on a storage list →
  "You need the 'Storage Blob Data Reader' role on this account").

---

## 3. Tech stack (exact)

**Backend (Go 1.22+):**
- `net/http` with `chi` router (or stdlib `http.ServeMux` — implementer's choice, keep it thin)
- `github.com/Azure/azure-sdk-for-go/sdk/azidentity` (+ `azidentity/cache`) for auth
- Plain `net/http` client for ARM/Graph REST (do **not** pull in per-service management SDKs; the
  REST surface used is small and versioned explicitly — see §5)
- `golang.org/x/sync/errgroup` for bounded fan-out
- `log/slog` structured logging → stderr + rotating file in the OS config dir
  (`%APPDATA%/BlueBridge/`, `~/Library/Application Support/BlueBridge/`, `~/.config/bluebridge/`)

**Frontend (TypeScript, built with Vite, embedded via `go:embed`):**
- React 18 + TypeScript strict
- **Fluent UI React v9** (`@fluentui/react-components`) — gives the app a native-to-Azure look and
  ships accessible components (DataGrid, Tree, Toast, Skeleton) out of the box
- TanStack Query for all data fetching (caching, retries, invalidation on SSE events)
- TanStack Table (rendered with Fluent DataGrid primitives) or Fluent DataGrid directly — must
  support sorting, column filtering, and **virtualized rows** (10k+ rows must scroll smoothly)
- React Router (routes mirror the resource hierarchy — see §7)
- `@azure/arm-*` packages: none. The SPA never talks to Azure — only to the local API.

**Repository layout:**

```
bluebridge/
├── cmd/bluebridge/main.go        # flag parsing, server bootstrap, browser open
├── internal/
│   ├── server/                   # http server, routes, SSE hub, local-token middleware
│   ├── auth/                     # credential chain, per-tenant token broker, sign-out
│   ├── azure/
│   │   ├── arm.go                # generic ARM REST client: GET/POST/PUT, paging, retry, throttle
│   │   ├── tenants.go            # GET /tenants
│   │   ├── subscriptions.go      # GET /subscriptions, /locations
│   │   ├── resourcegraph.go      # POST providers/Microsoft.ResourceGraph/resources
│   │   ├── pim.go                # role eligibility/assignment schedule APIs + activation
│   │   ├── monitor.go            # activity logs
│   │   ├── storage.go            # blob data-plane (containers, blobs, download)
│   │   ├── acr.go                # registry data-plane (token exchange, repos, tags)
│   │   └── appservice.go         # deployments (kudu/ARM)
│   └── cache/                    # generic TTL + stale-while-revalidate cache
├── web/                          # Vite + React app (built to web/dist, go:embed'd)
├── Makefile                      # build web → embed → go build matrix
└── .github/workflows/            # ci.yml (lint+test), release.yml (matrix build + release)
```

---

## 4. Local API contract (`/api/v1`)

All responses JSON. All list endpoints support `?refresh=true` to bypass cache. Errors per A5.

| Method & path | Purpose |
|---|---|
| `GET  /auth/status` | `{ signedIn, account: {username, name, homeTenantId}, method }` |
| `POST /auth/login` | Body `{ tenantId?, method?: "browser"\|"devicecode"\|"azurecli" }`. For device code, streams the user code via SSE event `auth.devicecode`. |
| `POST /auth/logout` | Clears MSAL cache + all server caches. |
| `GET  /tenants` | All tenants the identity can access (§5.1), with `displayName`, `tenantId`, `defaultDomain`, `signedIn` (whether we hold a token for it). |
| `GET  /tenants/{tid}/subscriptions` | Subscriptions in that tenant: id, name, state, quotaId/offer type. |
| `GET  /subscriptions/{sid}/resourcegroups` | RGs: name, location, tags, provisioning state, resource count (count from Resource Graph). |
| `GET  /resources?scope=...` | Resource Graph query (§5.3). Query params: `tenantId`, `subscriptionIds` (csv), `resourceGroup`, `type`, `location`, `search`, `tagKey`, `tagValue`, `skip`, `top` (server-side paging, default top=200). Returns rows + facet counts (types, locations, RGs) for filter UI. |
| `GET  /resources/{base64(resourceId)}` | Single resource: full ARM GET (latest stable api-version per provider, resolved via providers cache). |
| `GET  /pim/assignments?tenantId=` | `{ eligible: [], active: [], pending: [] }` across all subs in the tenant, aggregated server-side (§5.4). |
| `POST /pim/activate` | Body `{ items: [{scope, roleDefinitionId, principalId}], justification, durationHours }`. Returns request IDs immediately; server polls each request every 10 s until terminal and pushes `pim.status` SSE events. |
| `GET  /resources/{id}/activity?hours=24` | Activity log events (§5.5). |
| `GET  /storage/{account}/containers` · `GET .../blobs?prefix=&marker=` · `GET .../blob?name=` (download stream) | Blob browsing (§5.6). |
| `GET  /acr/{registry}/repositories` · `GET .../tags?repo=` | ACR (§5.7). |
| `GET  /containergroups/{id}/logs?container=&tail=` | ACI logs. |
| `GET  /webapps/{id}/deployments` | App Service deployment history. |
| `GET  /events` | SSE stream: `auth.devicecode`, `pim.status`, `cache.updated`, `error`. |

---

## 5. Azure API reference (implement exactly these)

Use explicit `api-version` on every call. Handle `nextLink` pagination everywhere. Respect
`Retry-After` on 429; retry 5xx with exponential backoff (max 3).

### 5.1 Tenants
`GET https://management.azure.com/tenants?api-version=2022-12-01` — works with any ARM token;
returns every tenant the identity belongs to (id, displayName, defaultDomain, tenantCategory).

### 5.2 Subscriptions & resource groups
- `GET /subscriptions?api-version=2022-12-01` (token scoped to the target tenant).
- `GET /subscriptions/{sid}/resourcegroups?api-version=2022-12-01`.

### 5.3 Resources — use **Azure Resource Graph**, not per-sub `/resources`
`POST https://management.azure.com/providers/Microsoft.ResourceGraph/resources?api-version=2022-10-01`

Body: KQL query over the `resources` table, e.g.

```kusto
resources
| where subscriptionId in ({subs})
| where name contains '{search}'            // only when search set
| project id, name, type, resourceGroup, location, subscriptionId, tags, kind, sku
| order by name asc
```

with `options: { "$skip": N, "$top": 200, "resultFormat": "objectArray" }` and paging via
`$skipToken`. Facet counts via a second query using `summarize count() by type` (and location,
resourceGroup). Resource Graph is one call for **all** subscriptions, supports server-side search/
filter/sort, and is dramatically faster than fanning out ARM `/resources` per subscription. Fall
back to per-subscription `GET /subscriptions/{sid}/resources?api-version=2021-04-01` only if
Resource Graph returns 403 (rare; it needs only reader on any scope).

### 5.4 PIM (Azure resource roles)
All under the target scope (`/subscriptions/{sid}` or narrower), api-version `2020-10-01`:
- Eligible: `GET {scope}/providers/Microsoft.Authorization/roleEligibilityScheduleInstances?$filter=asTarget()`
- Active: `GET {scope}/providers/Microsoft.Authorization/roleAssignmentScheduleInstances?$filter=asTarget()`
- Pending requests: `GET {scope}/providers/Microsoft.Authorization/roleAssignmentScheduleRequests?$filter=asRequestor()`
- Activate: `PUT {scope}/providers/Microsoft.Authorization/roleAssignmentScheduleRequests/{guid}`
  with `requestType: "SelfActivate"`, `justification`, `scheduleInfo.expiration =
  {type: "AfterDuration", duration: "PT{n}H"}`, `principalId`, `roleDefinitionId`.
- Poll request status via GET on the same URL; terminal states: `Provisioned`, `Denied`, `Failed`,
  `Canceled`; in-flight: `PendingApproval`, `PendingProvisioning`, `Provisioning`, `Granted`.
- Expand `roleDefinition` display names via `$expand=roleDefinition($select=displayName)` where
  supported, else resolve through `GET {scope}/providers/Microsoft.Authorization/roleDefinitions`.
- **Policy limits:** fetch the role management policy max duration where cheap; otherwise offer
  1–8 h and surface `RoleAssignmentRequestPolicyValidationFailed` errors verbatim with the policy
  message.

### 5.5 Activity log
`GET /subscriptions/{sid}/providers/Microsoft.Insights/eventtypes/management/values?api-version=2015-04-01&$filter=eventTimestamp ge '{iso}' and resourceUri eq '{resourceId}'`
— project timestamp, level, operationName, status, caller, description.

### 5.6 Storage data plane
Token audience `https://storage.azure.com/.default`.
- List containers: `GET https://{account}.blob.core.windows.net/?comp=list` (XML)
- List blobs hierarchically: `GET .../{container}?restype=container&comp=list&delimiter=/&prefix={p}&marker={m}`
- Download: `GET .../{container}/{blob}` — **stream** to the client (proxy the body; do not buffer
  whole blobs in memory). `x-ms-version: 2021-08-06`.

### 5.7 ACR data plane
1. Resolve `loginServer` via ARM (`Microsoft.ContainerRegistry/registries`, api-version 2023-01-01-preview or latest stable).
2. Exchange ARM token: `POST https://{loginServer}/oauth2/exchange` (`grant_type=access_token`,
   `service={loginServer}`, `access_token={armToken}`) → refresh token → `POST /oauth2/token` for a
   scoped access token (`scope=registry:catalog:*` or `repository:{repo}:metadata_read`).
3. `GET /acr/v1/_catalog` (repos), `GET /acr/v1/{repo}/_tags` (tags). Handle pagination via `Link`
   headers.

### 5.8 ACI logs & App Service deployments
- ACI: `GET {containerGroupId}/containers/{name}/logs?api-version=2023-05-01&tail={n}`
- App Service: `GET {siteId}/deployments?api-version=2023-01-01` (status, author, message, active).

---

## 6. New capability: estate browser (tenants → subscriptions → RGs → resources)

This is the headline addition. Requirements:

- **Left navigation tree** (Fluent Tree, lazy-loaded): Tenants → Subscriptions → Resource Groups.
  Each node shows a count badge (subscriptions per tenant, RGs per subscription, resources per
  RG — counts from Resource Graph `summarize`). Selecting any node scopes the main content pane.
- **Main content pane** = a real DataGrid of resources at the selected scope with columns: type
  icon + name (link to detail), type (friendly name, e.g. "Virtual machine" not
  `microsoft.compute/virtualmachines`), resource group, location, subscription, tags (chips,
  overflow +N). Column sort, global search box (server-side via Resource Graph `contains`), filter
  dropdowns (type, location, RG) populated from facet counts and showing counts, e.g.
  "Storage account (34)".
- **Scope breadcrumb** at the top: `Contoso (tenant) / Prod-Sub / rg-payments` — each segment
  clickable; matches the URL route `/t/{tenantId}/s/{subId}/rg/{rgName}`.
- **Tenant page** (when a tenant node is selected): tenant metadata card (name, ID, default
  domain) + subscriptions table (name, ID, state, offer) — subscription rows navigate into scope.
- **Subscription page**: subscription metadata + RG table (name, location, resource count, tags).
- **Resource detail** (route `/t/../s/../r/{base64 id}`): overview card (name, type, RG, location,
  status/provisioningState, tags, resource ID with copy button, "Open in Azure Portal" —
  `https://portal.azure.com/#@{tenantId}/resource{resourceId}`), plus contextual tabs:
  Activity Log (all types) · Storage / Registry / Container Logs / Deployments (per type, as in
  v1). JSON tab showing the raw ARM resource document (collapsible tree viewer).
- Every list handles: loading (skeleton rows), empty ("No resources in this scope" with icon),
  error (typed message + retry button + role hint when 403), and partial failure (banner:
  "2 of 14 subscriptions failed to load — details").

---

## 7. UX specification

### Navigation shell
- **Left rail** (collapsible, 280 px): product mark, then two sections — **Access** (PIM) and
  **Explorer** (estate tree from §6). Bottom: signed-in identity (avatar initials, UPN, home
  tenant) with menu: switch/add tenant, reuse-az-cli toggle, sign out.
- **Top bar**: scope breadcrumb, global search (`Ctrl/Cmd+K` command palette: fuzzy search across
  resource names, subscriptions, RGs; enter → navigate), refresh button with last-updated
  timestamp, theme toggle (light/dark/system — Fluent `webLightTheme`/`webDarkTheme`).
- **URLs are state**: every screen is a route; deep links work after refresh.

### Access (PIM) screens
- Three tabs with count badges: **Eligible / Active / Pending**.
- Eligible tab: DataGrid with checkbox column (selection keyed by stable
  `scope+roleDefinitionId+principalId`, never row index), Role, Scope (friendly: subscription or
  resource name, tooltip = full scope path), Tenant, End of eligibility. Sticky footer action bar
  appears when ≥1 selected: justification input (required, remembers last-used per session),
  duration select (1–8 h), "Activate N roles" primary button.
- Activation UX: rows enter in-flight state (spinner chip) individually; SSE-driven transitions to
  `Active ✓` (green chip), `Pending approval` (amber), `Denied`/`Failed` (red chip + reason
  popover). Toast per terminal transition. No page reload at any point.
- Active tab: Role, Scope, Tenant, Expires (relative + absolute tooltip), and a **Deactivate**
  action (PUT with `requestType: "SelfDeactivate"`) with confirm dialog.
- Pending tab: request time, role, scope, status, and cancel action where allowed.
- Data freshness: PIM lists auto-refresh via server cache (60 s TTL, stale-while-revalidate) —
  visible as a subtle "Updated 12 s ago" caption, never a spinner over existing data.

### Design language
- Fluent v9 defaults; 8 px spacing grid; Segoe UI/system font stack (Fluent default).
- Resource type icons: use a curated SVG set for the ~40 common types (inline SVGs styled to
  match Fluent), generic cube icon fallback. **No emoji anywhere.**
- Status colors: eligible = brand blue, active/success = green, pending = amber, denied/error =
  red — applied via Fluent Badge/`Tag` components, consistent across PIM and resource states.
- All tables virtualized; target 60 fps scroll with 10k rows.
- Accessibility: keyboard navigable throughout, visible focus rings, ARIA labels on icon buttons,
  color never the sole status carrier (icons + text accompany).

---

## 8. Cross-cutting requirements

- **Performance budgets:** binary ≤ 30 MB; cold start to sign-in screen ≤ 5 s (target < 2 s);
  tenants+subscriptions loaded ≤ 3 s after auth; resource list first page ≤ 2 s per Resource Graph
  call; UI interactions never block on network (optimistic/cached rendering).
- **Resilience:** per-subscription failures are isolated (partial results + warning banner, never
  a blank screen); 429 throttling honored globally via a shared limiter.
- **Security:** localhost binding + per-launch bearer token (A2); MSAL encrypted token cache; no
  secrets in logs; no telemetry.
- **Logging:** slog JSON to file with rotation (10 MB × 3); `--verbose` flag mirrors to stderr.
- **CLI flags:** `--port`, `--no-browser`, `--tenant <id>`, `--verbose`, `--version`.

---

## 9. Packaging & release (CI)

- `Makefile`: `make web` (vite build) → `make build` (go build with `-ldflags "-s -w -X
  main.version=$VERSION"`) → `make dist` (matrix).
- GitHub Actions `release.yml` on tag `v*`:
  - Build web once, upload as artifact.
  - Matrix `GOOS/GOARCH`: windows/amd64, windows/arm64, darwin/amd64, darwin/arm64, linux/amd64,
    linux/arm64 — all cross-compiled from ubuntu-latest (CGO_ENABLED=0).
  - Artifacts: `bluebridge-{version}-{os}-{arch}[.exe]`, zipped, plus SHA256SUMS. macOS: `lipo`
    the two arches into a universal binary if convenient, else ship both.
  - Code signing hooks left as optional documented steps (signtool / codesign+notarytool) — the
    release must not fail when signing secrets are absent.
- `ci.yml` on PR: `go vet`, `golangci-lint`, `go test ./...`, `npm run lint`, `npm run typecheck`,
  `npm test`, and a full `make build` smoke check.

---

## 10. Testing requirements

- **Go:** unit tests for every `internal/azure/*` client against `httptest` fixtures (recorded
  JSON for tenants, subs, Resource Graph pages, PIM instances, activation responses incl.
  `PendingApproval` and policy-failure bodies); pagination, 429-retry, and token-audience tests;
  cache TTL/stale-while-revalidate tests; localhost-token middleware tests (reject missing/wrong
  token).
- **Frontend:** vitest + React Testing Library for the PIM selection/activation flow (stable-key
  selection survives list reorder), estate tree lazy loading, and error/empty states. MSW to mock
  the local API.
- **E2E (Playwright):** against the real binary with a mock-Azure `httptest` server injected via a
  hidden `--arm-endpoint` flag: sign-in (mock), browse tenant → sub → RG → resource, activate a
  role and watch SSE-driven status change, download a blob.
- Coverage gate: 70 % on `internal/azure` and `internal/server`.

---

## 11. Milestones (each independently shippable & demoable)

1. **M1 — Skeleton:** repo layout, Makefile, CI; Go server serving embedded "hello" SPA; browser
   auto-open; localhost token handshake. *Demo: run binary on all 3 OSes.*
2. **M2 — Auth:** azidentity chain (browser → device code → optional az CLI), persistent cache,
   sign-in/out UI, `/auth/*` endpoints. *Demo: sign in, restart, still signed in.*
3. **M3 — Estate read path:** tenants, subscriptions, RGs, Resource Graph resources + facets;
   left tree, breadcrumb, resources grid with search/filter/sort; resource detail overview + JSON
   + Portal deep-link. *Demo: browse a real tenant end-to-end.*
4. **M4 — PIM:** eligible/active/pending aggregation, bulk activation, SSE status pushes,
   deactivate, cancel. *Demo: bulk-activate two roles, watch live states.*
5. **M5 — Resource inspectors:** activity log, storage browser (with streamed download), ACR,
   ACI logs, App Service deployments — each with role-hint 403 handling.
6. **M6 — Polish & release:** command palette, keyboard shortcuts, themes, empty/error state
   sweep, accessibility pass, performance budget verification, release pipeline producing all six
   artifacts + checksums, README rewrite.

---

## 12. Documented future path (do not build now)

The SPA and API layer are deliberately separable: with an Entra **app registration** (SPA
platform, delegated `user_impersonation` on ARM) the same frontend can run as a hosted static web
app using MSAL.js in-browser (ARM supports CORS), with a thin hosted API for storage/ACR data-plane
proxying. Keep the frontend's data-access behind a single client module so this swap stays cheap.

---

## 13. Acceptance criteria (final review checklist)

- [ ] One double-clickable artifact per OS/arch runs with **no** prerequisites installed.
- [ ] Fresh machine → signed in and seeing tenants in under 60 s (excluding MFA time).
- [ ] Sign-in survives app restart; sign-out fully clears cached tokens.
- [ ] Tenants, subscriptions, resource groups, and resources are all browsable, searchable,
      sortable, and deep-linkable; counts and facets are accurate.
- [ ] A user with 5k+ resources gets a first page in ≤ 2 s and smooth scrolling.
- [ ] PIM bulk activation works incl. approval-pending and policy-rejection paths, with live
      per-row status and no full-page reloads.
- [ ] Every 403 in the UI shows a role hint, not a raw HTTP error.
- [ ] Partial subscription failures degrade gracefully (banner + partial data).
- [ ] All CI checks green; E2E suite passes against the mock ARM server on all three OSes.
