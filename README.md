# BlueBridge

**Azure Navigator** — navigate Azure faster than the portal.

A cross-platform desktop app (Windows / macOS / Linux) built with [Flet](https://flet.dev) that provides instant access to your Azure PIM roles and resources, powered by the Azure CLI for authentication and ARM REST APIs for data.

---

## Features

- **One-click PIM activation** — eligible roles across all subscriptions, bulk-activate with justification and duration, real-time status polling
- **Tenant switching** — switch tenants without re-opening the app; per-tenant token and data cache
- **Resource browser** — hierarchical tree of subscriptions → resource groups → resources with search, filter, and direct Azure Portal deep-links
- **Non-blocking UI** — all data loads in the background; stale data stays visible while fresh data loads

## Prerequisites

- Python 3.11+
- [Azure CLI](https://aka.ms/install-azure-cli) (the `az` command on your PATH)

## Quick start

```bash
# 1. Clone
git clone <repo-url>
cd bluebridge

# 2. Create virtual environment
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# 3. Install
pip install -e .

# 4. Run
python main.py
```

## Development

```bash
pip install -e ".[dev]"

invoke run              # run in dev mode
invoke build            # build for the current OS
invoke build --target windows   # or macos / linux
invoke lint             # ruff check
invoke fmt              # ruff format
invoke clean            # remove build artefacts
invoke --list           # see all tasks
```

## Architecture

See [PLAN.md](PLAN.md) for the full architecture and build plan.

## Changelog

See [CHANGELOG.md](CHANGELOG.md).
