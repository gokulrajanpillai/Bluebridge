# Security Policy

BlueBridge signs you in to Azure and acts on your behalf. Trust is the whole point of the tool,
so this document is specific about what it does — and does not — do with your credentials.

## How BlueBridge handles your credentials

- **No passwords, ever.** Sign-in uses Microsoft's own MSAL libraries (`azidentity`) via the
  interactive browser flow, a device code, or an existing Azure CLI login. BlueBridge never sees,
  handles, or stores your password.
- **No app registration, no secret.** It authenticates as the well-known public Azure CLI client
  (`04b07795-8ddb-461a-bbee-02f9e1bf7b46`), so there is no client secret anywhere and you do not
  need to register an Entra application.
- **Tokens are cached by the OS, encrypted.** The persistent token cache is provided by MSAL and
  backed by OS-native secret storage — DPAPI on Windows, Keychain on macOS, and the kernel keyring
  on Linux. BlueBridge does not write raw tokens to disk itself.
- **Tokens are requested per tenant and per audience**, and only for the scopes a given action
  needs (ARM, Storage, or ACR).
- **No telemetry.** BlueBridge makes no network calls other than to Azure endpoints and, for the
  web app, `127.0.0.1`. It phones no home.
- **Logs contain no secrets.** Structured logs are written to a rotating file in your OS config
  directory and never include tokens.

### The local web server is locked down

The `bluebridge` web app runs a server **bound to `127.0.0.1`** on an ephemeral port. At launch it
generates a random bearer token, passes it to the browser in the URL fragment, and **rejects every
`/api/v1` request that does not present it**. Static assets are public; the `/healthz` liveness
probe is intentionally public and returns no sensitive data. This prevents other local processes
or a drive-by web page from driving the API.

## Supported versions

BlueBridge is pre-1.0 and under active development. Only the latest released version receives
security fixes.

| Version | Supported |
|---|---|
| latest release | ✅ |
| older / legacy v1 (Streamlit) | ❌ |

## Reporting a vulnerability

**Please do not open a public issue for security problems.**

Report privately via GitHub's [private vulnerability reporting](../../security/advisories/new)
("Report a vulnerability" under the Security tab). Include:

- affected version / commit,
- a description and, ideally, a minimal reproduction,
- the impact you foresee.

You can expect an acknowledgement within a few days. Please allow a reasonable window for a fix
before any public disclosure.

## Dependency hygiene

Dependencies are monitored by Dependabot (Go modules, npm, and GitHub Actions) and by
`govulncheck` guidance in development. Advisory-flagged dependencies are bumped promptly.
