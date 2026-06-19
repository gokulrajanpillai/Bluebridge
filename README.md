# BlueBridge

**Azure PIM Access Manager** — activate roles, browse resources, and inspect activity from a single browser tab.

BlueBridge is a cross-platform desktop application (Windows / macOS / Linux) built with [Streamlit](https://streamlit.io) and packaged as a standalone executable via PyInstaller. It authenticates through the [Azure CLI](https://aka.ms/install-azure-cli) and talks directly to ARM REST APIs, giving you faster access to the things you do most in the Azure Portal.

---

## Features

### Access (PIM)
- View all **Eligible**, **Active**, and **Pending** role assignments across every subscription in your tenant
- **Bulk-activate** multiple eligible roles at once — shared justification, configurable duration (1–8 h), parallel submission via `ThreadPoolExecutor`
- Live per-role activation status (`Provisioning → Active / Denied / Failed`) via `st.status`
- Active tab auto-refreshes every 60 s; Pending tab every 30 s

### Resources
- Full resource inventory across all subscriptions — name, type, resource group, location, Azure Portal deep-link
- Searchable and filterable by resource group, type, and location
- **Inline resource detail panel** — click any resource to expand:
  - **Activity Log** — 24 h history, auto-refreshes every 30 s, plain-text export
  - **Storage** (Storage Accounts) — browse containers and virtual directories, preview blob metadata, one-click download
  - **Registry** (Container Registry) — list repos and tags, copy `docker pull` command
  - **Container Logs** (Container Instances) — fetch stdout/stderr with configurable tail, plain-text export
  - **Deployments** (App Service) — deployment history with status icons
  - Permission-denied errors surface actionable role hints instead of raw HTTP 403s

### General
- Authenticates via `az login` — browser SSO, no credentials stored by BlueBridge
- Tenant switcher — change tenants without restarting
- Per-tenant token cache with automatic refresh 5 min before expiry
- Packaged as a single executable: `launcher.py` starts the Streamlit server and opens your browser automatically

---

## Prerequisites

- Python 3.10+
- [Azure CLI](https://aka.ms/install-azure-cli) (`az` on your PATH, signed in via `az login`)

---

## Quick start

```bash
# 1. Clone
git clone <repo-url>
cd bluebridge

# 2. Create and activate a virtual environment
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# 3. Install
pip install -e .

# 4. Run
streamlit run app.py
# or via the launcher (auto-opens browser):
python launcher.py
```

---

## Building a standalone executable

```bash
pip install -e ".[build]"

# Current platform
python build.py

# Specific target
python build.py windows
python build.py macos
python build.py linux
```

Output is a single portable executable at `build/<platform>/BlueBridge[.exe]` — no supporting folder needed.

---

## Development

```bash
pip install -e ".[dev]"

ruff check .          # lint
ruff format .         # format
mypy app.py           # type check
```

---

## Changelog

See [CHANGELOG.md](CHANGELOG.md).
