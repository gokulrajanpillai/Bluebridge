# BlueBridge — session handoff (2026-07-18)

Read this first in a new chat to pick up where this session left off. This file is the
continuation doc; update it (don't just append) as work progresses.

## What this session was asked to do

Original ask: review the repo and plan how to make it a "100k star repo." After discussion, the
goal was reframed to **real adoption/credibility**, not vanity stars. Mid-plan, discovery showed
the repo was a **mid-rewrite Go/React app with nothing actually deploying**, so the ask became:
re-analyze, fix deploys, add a test strategy (smoke + E2E), and build an **interactive
BlueBridgeCLI** (Claude-CLI style: login → tenants → resources → roles → multi-apply).

## Ground truth about the repo (verify again — this drifts)

- `main` is the **v2 Go + React rewrite**. The old Streamlit/PyInstaller app is fully removed
  (commit `b338949`). Spec: [`REBUILD_PLAN.md`](../REBUILD_PLAN.md), milestones M1–M6.
- **M1 (skeleton) + M2 (auth)** were already done before this session (localhost Go server,
  launch-token auth, SSE hub, MSAL sign-in, React sign-in screen).
- **M3–M6 are NOT built**: no estate browser, no PIM in the web UI, no resource inspectors. The
  web SPA is sign-in-only today.
- This session added a **third, independent surface**: `bluebridge-cli`, which already delivers
  the full PIM flow end-to-end (tenants → scope → multi-activate roles) via a shared core.

## What was shipped this session (all merged to `main`, CI green, verified — not just written)

**Phase A — unblocked deploys** (the core problem: nothing was actually shipping)
- Root cause 1: no v2 release existed; the [Releases](https://github.com/gokulrajanpillai/Bluebridge/releases) page only had the dead v1 Streamlit builds.
- Root cause 2: Go toolchain drift — `go.mod` requires 1.26.5, CI/release pinned `setup-go` to
  1.22. Fixed: both workflows now use `go-version-file: go.mod`.
- Fixed 13 Dependabot vulnerabilities — all `golang.org/x/crypto@v0.51.0` (transitive), bumped to
  v0.54.0. Verified with `govulncheck` (0 reachable vulnerabilities in code).
- Added `.github/dependabot.yml` (gomod, npm in `web/`, github-actions).
- Added public `GET /healthz` on the server + a CI smoke test that boots the binary and curls it.
- Fixed `.gitignore` (stray local build dirs) after a rebase conflict with the real remote state.

**Phase B — shared core + BlueBridgeCLI + first real release**
- New `internal/azure` package: ARM REST client with pagination (`nextLink`), 429/5xx retry with
  backoff, typed `APIError` with role-hint on 403. Endpoints: `Tenants`, `Subscriptions`,
  `Resources`, `EligibleRoles`, `ActivateRole`, `ActivationStatus`. Auth-agnostic via a `TokenFunc`
  seam — fully testable against `httptest`, no live tenant needed. **~80% coverage.**
- New `internal/auth/tenant_tokens.go`: `TenantTokens`, a per-tenant token provider (lazily builds
  one credential per tenant, shares the persistent cache) implementing the core's `TokenFunc`.
- New `internal/cli` package + `cmd/bluebridge-cli/main.go`: interactive Bubble Tea TUI —
  **login → pick tenant → pick subscription (scope) → multi-select eligible PIM roles (space/`a`
  for all) → justification + duration → activate → live results.** Also non-interactive
  `tenants` / `resources --sub` / `pim list --scope` / `pim activate --scope --role
  --justification` for scripting. Headless E2E via `teatest` (happy path + "empty justification
  must not activate").
- Makefile: `build-cli` target; `dist`/`dist-darwin` now also build `bluebridge-cli` per target.
- `release.yml` rewritten to build+package **both** binaries (server + CLI) for all 6 OS/arch
  combos, uploads them, and the release job's artifact-download pattern matches.
- **Shipped v0.8.0**: verified live at
  https://github.com/gokulrajanpillai/Bluebridge/releases/tag/v0.8.0 — 12 archives (bluebridge +
  bluebridge-cli × windows/darwin/linux × amd64/arm64) + `SHA256SUMS`, not draft, not prerelease.
  CHANGELOG.md has a proper `## [0.8.0]` section (the release workflow's changelog extractor
  depends on that exact heading format — keep using it for future tags).

**Phase D — credibility/governance**
- `SECURITY.md`: full credential-handling trust model (MSAL, no app secret, OS-encrypted token
  cache, per-tenant/per-audience tokens, no telemetry, localhost bearer-token lockdown) + private
  vulnerability reporting instructions.
- `CONTRIBUTING.md`, `.github/ISSUE_TEMPLATE/{bug_report,feature_request,config}.yml`,
  `.github/PULL_REQUEST_TEMPLATE.md`.
- CI coverage gate: `internal/azure` + `internal/server` combined must stay **≥ 70%** (currently
  83.5%). Added as a step in `.github/workflows/ci.yml`'s `go` job.

## Explicitly deferred / not done — and why

- **Phase C (the big one): web SPA milestones M3–M6** — estate browser (tenants → subs → RGs →
  resources via Resource Graph), PIM activation UI, resource inspectors (storage/ACR/ACI
  logs/App Service deployments), Playwright E2E. This is a multi-session build. **Natural next
  step if resuming this thread.**
- **golangci-lint in CI** — skipped; not verified against the existing codebase locally, risk of
  redlining CI on first add. If picked up, dry-run it locally first.
- **Code signing** (Windows Authenticode / macOS notarization) — no certs available. README
  documents the SmartScreen/Gatekeeper warning + SHA256SUMS verification as the interim story.
- **Demo GIF / screenshots** — needs a live Azure tenant to capture; placeholders were discussed
  but not yet added to the README.
- **Marketing/launch** (winget/brew manifests, Show HN, awesome-lists, blog post) — intentionally
  held until Phase C ships something demoable. Don't spend the one launch moment on a
  still-partial product.
- One residual govulncheck advisory, `GO-2026-5932`, has no upstream fix yet but is confirmed
  **not reachable** by the code (safe to ignore, re-check on next dependency bump).

## Environment gotchas (save yourself the rediscovery)

- **Go is not on PATH** in this sandbox. A working Go 1.26.5 toolchain was downloaded into the
  session scratchpad at `.../scratchpad/go`. In a fresh session you'll need to fetch it again:
  `curl -sSL -o go.zip "https://go.dev/dl/go1.26.5.windows-amd64.zip" && unzip -q go.zip`, then
  `export GOROOT=.../go && export PATH="$GOROOT/bin:$PATH"`. `-race` needs cgo, which isn't
  available here — omit `-race` for local runs; CI still uses it.
- **Node is v19 locally** (too old for `web/`'s Vite/oxlint engine requirements — expect
  `EBADENGINE` warnings, harmless). CI uses Node 20 and passes; don't chase local web build
  failures caused by the Node version mismatch.
- **A stale global pre-commit hook** fires on every commit here (leftover from the old Python repo
  — no `.pre-commit-config.yaml` exists anymore). Prefix commits with
  `PRE_COMMIT_ALLOW_NO_CONFIG=1 git commit ...` or it errors out (commit still doesn't happen
  without it).
- **`gh` token lacks `admin:repo_hook`/Dependabot-alerts scope** — `gh api .../dependabot/alerts`
  returns 403. Use `govulncheck` locally instead for vulnerability ground-truth.
- Commit style: **Conventional Commits, no `Co-Authored-By: Claude` line** (explicit user
  instruction this session).
- Always `git pull --rebase origin main` before pushing — this repo has had concurrent remote
  changes mid-session more than once.

## Suggested next steps (in priority order)

1. **Phase C, milestone M3 (estate browser)**: build the web `/api/v1` routes (`/tenants`,
   `/tenants/{id}/subscriptions`, `/resources?scope=...` via Resource Graph per REBUILD_PLAN §5.3)
   on top of the already-tested `internal/azure` core, then the React tree/grid UI. This is the
   highest-leverage next chunk — it turns the web app from sign-in-only into something demoable.
2. Once M3 is usable, revisit **screenshots/demo GIF** for the README (real UI exists then).
3. M4 (PIM web UI) and M5 (resource inspectors) reusing the same core — the CLI already proves the
   core works end-to-end, so this should mostly be UI + wiring, not new Azure logic.
4. Playwright E2E for the web app once M3/M4 exist to test.
5. Only after the web app is demoable: code signing (needs certs — ask user), winget/brew,
   marketing push.

## Reference

- Full session narrative / rationale: see the conversation this file was generated from, or
  `C:\Users\GPow\.claude\projects\g--stash-Bluebridge\memory\project_bluebridge_state.md` (auto
  memory, updated same session — more concise, same facts).
- Spec: [`REBUILD_PLAN.md`](../REBUILD_PLAN.md).
- Latest release: https://github.com/gokulrajanpillai/Bluebridge/releases/tag/v0.8.0
