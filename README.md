# MemCortex

A personal memory system with a UI you can actually look at.

MemCortex keeps everything an agent learns — conversations, files, documents,
agent lineage — in a place you own, and shows it to you as a **brain**: a
segmented map of what has been stored, grouped by subject, with live telemetry
from whichever agent is running.

This repository is the **client**: the dashboard and the desktop widgets. The
backend it talks to (Postgres, Qdrant, Supermemory, Ollama, identity) lives in
a separate repository.

```
┌─────────────────────────┐        ┌──────────────────────────────┐
│  MemCortex client       │  HTTPS │  MemCortex backend           │
│  dashboard + widgets    │ ─────► │  brain-ui · identity ·       │
│  bin/memcortex-client   │        │  Postgres · Qdrant · …       │
└─────────────────────────┘        └──────────────────────────────┘
```

## Quick start

```bash
git clone https://github.com/Ajeetesh-Ranjan/memcortex.git
cd memcortex
docker compose up -d
open http://127.0.0.1:8090
```

You need a MemCortex backend running and reachable. Point at it with
`MEMCORTEX_BACKEND`:

```bash
# backend on the Docker host (the default)
MEMCORTEX_BACKEND=http://host.docker.internal:8080 docker compose up -d

# backend on another machine -- use TLS
MEMCORTEX_BACKEND=https://memory.example.com docker compose up -d
```

Running from source instead, no container:

```bash
python3 bin/memcortex-client.py --backend http://127.0.0.1:8080 --port 8090
```

No dependencies. Python 3.10+ standard library only — no `pip install`, no
lockfile to drift, nothing to audit but this repository.

## Why the client is a proxy, not a copy of the API

The dashboard calls relative `/api/...` paths, so it does not need to know
where the backend lives. The client serves the page and forwards `/api/*`
upstream, which means:

- **no frontend change** was needed to split the app out
- **the identity session cookie keeps working**, because the browser only ever
  talks to one origin — no CORS, no third-party cookie blocking
- **the client holds no secrets**; it authenticates nothing and stores nothing

## Security

This process sits in front of an authenticated API, so it is built to be
boring:

| Property | How |
|---|---|
| Loopback by default | Binds `127.0.0.1`; warns loudly if asked to bind otherwise |
| Header allowlist | Only `Cookie`, `Authorization`, `Content-Type` and a few negotiation headers are relayed — hop-by-hop headers are dropped, not forwarded |
| No credential logging | Method, path, status, duration. Never header values, even at debug verbosity |
| Redirects refused | A backend answering `302` cannot bounce your browser to another host |
| No path walking | Unknown paths return 404 rather than touching the filesystem |
| Hardened responses | CSP, `nosniff`, `X-Frame-Options: DENY`, `no-referrer`, `no-store` |
| Non-root, read-only, no capabilities | In the container |

**Before publishing this anywhere**, put TLS in front of it. The dashboard is
unauthenticated and the API it proxies is not; over plain HTTP your session
cookie is readable by anything on the path.

## Desktop widgets

`widgets/` holds the bar and tray widgets, each talking to the same API:

| Widget | Platform |
|---|---|
| `omarchy-bar-widget` | Hyprland / Omarchy (QML panel) |
| `waybar` | Waybar modules |
| `menubar` | macOS, Windows, Linux |
| `python` | Generic system tray |
| `brain3d` | Browser-based 3D brain |

See [`widgets/README.md`](widgets/README.md) for per-widget install steps.

## Tests

```bash
python3 tests/test_client.py            # needs a running backend
python3 tests/test_client.py --backend http://127.0.0.1:8080
```

Current result — 7/7:

```
test_dashboard_is_served .......................................... ok
test_dashboard_carries_hardening_headers .......................... ok
test_unauthenticated_api_call_is_refused ........................... ok
test_authenticated_call_keeps_its_compartment ..................... ok
test_unknown_path_is_not_a_directory .............................. ok
test_backend_redirect_is_not_followed .............................. ok
test_logs_contain_no_credential .................................... ok
Ran 7 tests in 1.1s — OK
```

These assert properties, not just absence of crashes. The suite was checked
against a deliberately broken build: removing `Cookie` from the header
allowlist makes `test_authenticated_call_keeps_its_compartment` fail with
`AssertionError: 201 != 401`, so the credential-forwarding guarantee is
genuinely covered rather than vacuously true.

## Relationship to the backend

The dashboard (`dashboard/index.html`) and `widgets/` are published here and
also in the backend repository, because the backend serves the dashboard as
part of the full stack. **The backend repository is the source of truth for
both.** If you are changing either, change it there and run its
`bin/sync-to-memcortex.sh`.

This repository ships the client only. Backend changes — identity,
compartments, ingestion, the API surface — land in the backend repository and
are not duplicated here.

## Status

Client-side work is complete and tested. Not yet done:

- Signed releases and auto-update for the native widgets
- Dark/light theme toggle in the dashboard
- Offline mode when the backend is unreachable

## License

MIT. See [LICENSE](LICENSE).
