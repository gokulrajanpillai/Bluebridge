# Contributing to BlueBridge

Thanks for your interest! BlueBridge is a Go backend + React/TypeScript SPA, plus an interactive
Go CLI, all sharing one Azure service core. This guide gets you productive quickly.

## Prerequisites

- **Go 1.26+** (the version is pinned in [`go.mod`](go.mod); CI reads it from there)
- **Node 20+** (for the web SPA)
- Optionally the **Azure CLI** if you want to sign in with an existing `az login`

## Layout

```
cmd/bluebridge/        # local web server + browser launcher
cmd/bluebridge-cli/    # interactive terminal client (Bubble Tea)
internal/
  azure/               # shared ARM + PIM service core (tenants, subs, resources, roles)
  auth/                # MSAL credential chain + per-tenant token provider
  server/              # localhost HTTP server, launch-token middleware, SSE hub, /healthz
  cache/  logging/     # TTL cache; rotating file logger
web/                   # React + TypeScript SPA (Vite), embedded via web/webui.go
```

See [REBUILD_PLAN.md](REBUILD_PLAN.md) for the full architecture and milestone spec.

## Build, test, lint

```bash
make build       # web build + Go server binary  -> ./bluebridge
make build-cli   # Go CLI binary                  -> ./bluebridge-cli
make run         # build and run the web app
make test        # go test ./...  +  web build
make lint        # go vet ./...   +  web lint
make dist        # cross-compile all release targets into dist/
```

Run a single package's tests while iterating:

```bash
go test ./internal/azure/ -cover
go test ./internal/cli/ -run TestInteractive -v
```

## Testing expectations

- New code in `internal/azure` and `internal/server` should keep coverage **at or above 70%**
  (CI enforces this). Test ARM interactions against `httptest`, not a live tenant.
- CLI flow changes should be exercised with a `teatest` interaction test (see
  `internal/cli/interactive_test.go`).
- Never commit real tenant IDs, tokens, or subscription IDs in fixtures — use obvious fakes.

## Commit & PR conventions

- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/): e.g.
  `feat(cli): ...`, `fix(server): ...`, `docs: ...`, `ci: ...`.
- Keep PRs focused. Ensure `make lint` and `make test` pass before opening one.
- CI (`go vet`, `go test -race`, web lint/build, a full build smoke, and coverage) must be green.

## Security

Do not file public issues for vulnerabilities — see [SECURITY.md](SECURITY.md) for private
reporting.
