# BlueBridge

**Azure companion tool** — browse your tenants, subscriptions, resource groups, and resources,
and manage PIM role activations, from a single local app.

BlueBridge is a single static binary (Go) that embeds a React SPA and serves it on `localhost`,
opening your default browser. There is nothing else to install — no Python, no Azure CLI, no
.NET runtime.

> **Status:** under active rewrite. See [REBUILD_PLAN.md](REBUILD_PLAN.md) for the full
> specification and milestone plan. The previous Streamlit/PyInstaller implementation has been
> removed; see [CHANGELOG.md](CHANGELOG.md) for history.

---

## Quick start

> **Heads up:** the binaries currently on the [Releases](../../releases) page are the **legacy
> v1 (Streamlit)** builds. The v2 Go rewrite has not been released yet — until the first v2 tag,
> run it from source (see [Development](#development) below). This notice will be removed when v2
> ships.

Once a v2 binary is available, download it for your OS/arch and run it:

```bash
./bluebridge
```

Your browser opens automatically to the sign-in screen. Sign in with your Microsoft account —
BlueBridge never stores your password; tokens are cached encrypted via OS-native facilities.

### CLI flags

| Flag | Description |
|---|---|
| `--port <n>` | Port to listen on (default: pick a free port) |
| `--no-browser` | Don't open the system browser automatically |
| `--tenant <id>` | Sign in to a specific tenant on start |
| `--verbose` | Mirror logs to stderr in addition to the log file |
| `--version` | Print version and exit |

---

## BlueBridgeCLI

Prefer the terminal? `bluebridge-cli` is an interactive client for the most common task —
activating PIM roles — without opening a browser:

```
$ bluebridge-cli
🌉 BlueBridge  you@contoso.com

Select a tenant
▸ [ ] Contoso        11111111-1111-1111-1111-111111111111
  [ ] Fabrikam       22222222-2222-2222-2222-222222222222

↑/↓ move · enter select · q quit
```

The flow is: **sign in → pick a tenant → pick a subscription (scope) → multi-select eligible
roles (`space` to toggle, `a` for all) → enter a justification and duration → activate and watch
the results**.

It also supports non-interactive subcommands for scripting and CI:

```bash
bluebridge-cli tenants
bluebridge-cli resources --sub <subscriptionId>
bluebridge-cli pim list --scope /subscriptions/<id>
bluebridge-cli pim activate --scope /subscriptions/<id> --role Contributor --justification "on-call"
```

Sign-in flags: `--tenant <id>`, `--device-code` (headless/SSH), `--az-cli` (reuse an existing
`az login`).

---

## Development

Requires Go 1.26+ and Node 20+.

```bash
make build     # builds web/ then the Go server binary → ./bluebridge
make build-cli # builds the CLI → ./bluebridge-cli
make run       # build and run
make test    # go test ./... + web build
make lint    # go vet + web lint
make dist    # cross-compile all release targets into dist/
```

Project layout:

```
cmd/bluebridge/     # CLI entrypoint
internal/
  server/           # localhost HTTP server, launch-token auth, SPA serving
  cache/            # generic TTL / stale-while-revalidate cache
  logging/          # rotating file logger
web/                # React + TypeScript SPA (Vite), embedded via web/webui.go
```

---

## Changelog

See [CHANGELOG.md](CHANGELOG.md).
