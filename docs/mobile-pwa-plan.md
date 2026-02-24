# Plan: Progressive Web App Mobile Chat Interface

## Context

### What Exists Today

Talking Rock currently has one user-facing interface: a Tauri desktop application
(`apps/reos-tauri/`) that runs on the Linux PC. It communicates with the Python
backend via **JSON-RPC 2.0 over stdio** — the Tauri Rust process spawns the Python
kernel as a child process and pipes JSON back and forth.

There are two separate Python servers in this project:

**1. `reos.app` (FastAPI / HTTP, port 8010)**
Defined in `src/reos/app.py`. Has exactly six endpoints: `GET /`, `GET /health`,
`POST /events`, `GET /reflections`, `GET /time`, `GET /ollama/health`,
`GET /tools`. This is a thin metadata and observability API. It does NOT expose
chat, CAIRN, The Play, memory, agents, approvals, or any user-facing feature.

**2. `reos.ui_rpc_server` (JSON-RPC 2.0 over stdio)**
Defined in `src/reos/ui_rpc_server.py` (approximately 2,600 lines). This is where
everything lives: `chat/respond`, `cairn/chat_async`, `cairn/chat_status`,
`consciousness/poll`, `consciousness/start`, `play/acts/*`, `play/scenes/*`,
`memory/*`, `approval/*`, `health/*`, and approximately 80 other methods. The
Tauri app communicates exclusively with this server.

### Why Change Is Needed

The user wants to access the full Talking Rock feature set (CAIRN, ReOS, RIVA) from
a phone via a PWA served over Tailscale. This requires:

1. Exposing the full RPC method surface over a network protocol (not stdio)
2. Replacing Polkit authentication (requires a native Linux GUI dialog) with
   something a browser can complete
3. Creating a mobile-first HTML/CSS/JS chat interface
4. Installing Tailscale on both the PC and phone for encrypted private networking
5. Serving the PWA static assets from the FastAPI app

### Key Constraints Discovered During Research

- `REOS_HOST` defaults to `127.0.0.1` (`src/reos/settings.py` line 36). The server
  must be rebound to `0.0.0.0` to accept Tailscale connections.
- Authentication currently calls `authenticate_polkit()` in `src/reos/auth.py`,
  which runs `pkcheck` via subprocess. This shows a native GUI dialog and cannot
  work from a remote browser.
- The CAIRN async chat pattern uses `cairn/chat_async` then `cairn/chat_status`
  and `consciousness/poll` in a polling loop. This is already designed for polling,
  which maps well to Server-Sent Events.
- Ollama streaming (`chat_stream()` in `src/reos/providers/ollama.py`) is a
  synchronous generator. Surfacing true token streaming to the PWA requires
  wrapping this in an async FastAPI endpoint.
- The session model in `src/reos/auth.py` (`Session`, `SessionStore`) already
  produces 256-bit CSPRNG tokens and validates them on every RPC call. This token
  model is reusable over HTTP if Polkit is replaced with PAM-based login.
- RIVA is frozen at the infrastructure level (CLAUDE.md: "intent verification layer
  incomplete") but its RPC surface (code mode planning, execution) still exists in
  the stdio server and should be available in the PWA.

---

## Approach Options

### Approach A: HTTP Bridge — New FastAPI Endpoints Wrapping the Stdio RPC Logic (Recommended)

Add a new FastAPI router to `src/reos/app.py` that exposes the same RPC methods
as the stdio server, but over HTTP POST (JSON-RPC 2.0 body). The existing handler
functions in `src/reos/rpc_handlers/` are plain Python — they take a `Database`
and kwargs and return dicts. They can be called directly from FastAPI route handlers
without any modification.

The PWA sends `POST /rpc` with a JSON-RPC 2.0 body. FastAPI parses it, validates
the session token from an `Authorization: Bearer` header, calls the appropriate
handler function, and returns the JSON-RPC 2.0 response.

Authentication is handled by a new `POST /auth/login` HTTP endpoint that accepts
a JSON body containing username and password, validates via PAM (`python-pam` is
already in `pyproject.toml`), and returns a session token using the existing
`SessionStore`.

For CAIRN's streaming consciousness events, a `GET /rpc/events` Server-Sent Events
endpoint is added. The PWA starts a chat via `cairn/chat_async`, then opens an SSE
stream that delivers `consciousness/poll` events and the final `cairn/chat_status`
result.

Static PWA assets (HTML, JS, CSS, manifest, service worker) are served from
FastAPI via `StaticFiles` mounted at `/app`.

**Trade-offs:**
- Complexity: Medium. Requires new HTTP auth flow, new FastAPI router, SSE endpoint,
  and the PWA frontend. No changes to existing stdio server or Tauri app.
- Risk: Low. Handler functions are already well-tested. The HTTP layer is thin glue.
- Reversibility: High. The stdio server is untouched. The PWA can be removed without
  affecting the desktop app.
- Pattern alignment: The existing `src/reos/app.py` is already FastAPI. This is the
  natural extension point. `python-pam` is already declared as a dependency.
- Tailscale fit: FastAPI listens on a single port. Tailscale exposes that port.

### Approach B: WebSocket Bridge — Full JSON-RPC 2.0 over WebSocket

Add a `/ws` WebSocket endpoint to the FastAPI app. The PWA connects over WebSocket
and sends the same JSON-RPC 2.0 messages the Tauri app sends. The FastAPI server
dispatches them through `_handle_jsonrpc_request()` (after importing it from
`ui_rpc_server.py`). Authentication happens once at connect time.

**Trade-offs:**
- Complexity: Higher. WebSocket reconnection on mobile (network switching between
  WiFi and cell, screen lock, app backgrounding) is fragile. Mobile browsers
  aggressively kill idle WebSocket connections. The existing polling architecture
  (`cairn/chat_async` plus `cairn/chat_status`) is already HTTP-shaped.
- Risk: Medium. Importing `_handle_jsonrpc_request` from `ui_rpc_server.py` imports
  the entire 2,600-line module including all threading state (`_active_cairn_chats`,
  `_handoff_state`), creating shared global state between what was meant to be a
  single-tenant stdio process and the multi-request HTTP server.
- Reversibility: Medium. Would require careful isolation to avoid cross-contaminating
  stdio and HTTP sessions.

### Approach C: Reverse Proxy Through Existing Stdio Server

Wrap the entire stdio server in a process-level HTTP reverse proxy — an HTTP server
that receives requests, serializes them to JSON-RPC, writes to the stdio process's
stdin, reads its stdout, and returns the response.

**Trade-offs:**
- Complexity: Highest. The stdio server is inherently single-threaded (one request
  at a time). Concurrent HTTP requests from the PWA (SSE stream plus health poll)
  would deadlock in the stdio pipe.
- Risk: High. The stdio server's threading model (`_cairn_chat_lock`,
  `_active_cairn_chats`, `threading.Thread`) assumes a single consumer feeding it
  sequentially. An HTTP reverse proxy feeding it concurrently would require the
  stdio server to be redesigned.
- Reversibility: Low.

**Approach A is recommended.** It is the only approach that does not touch the stdio
server, uses already-tested handler functions directly, and maps naturally to mobile
HTTP semantics.

---

## Recommended Approach: HTTP Bridge

### Architecture Overview

```
Phone (Tailscale IP)
  |
  |  HTTPS (Tailscale WireGuard + TLS from tailscale cert)
  |
  v
Linux PC (Tailscale daemon running)
  |
  +-- Port 8010 (REOS_HOST=0.0.0.0)
  |    FastAPI (src/reos/app.py)
  |    |
  |    +-- GET  /app/*         -> StaticFiles (PWA assets)
  |    +-- POST /auth/login    -> PAM login, returns session bearer
  |    +-- POST /auth/refresh  -> Extend session lifetime
  |    +-- POST /auth/logout   -> Invalidate session
  |    +-- POST /rpc           -> JSON-RPC 2.0 dispatcher (~80 methods)
  |    +-- GET  /rpc/events    -> SSE stream (consciousness events)
  |
  +-- stdio pipe (unchanged)
       Tauri desktop app <-> ui_rpc_server.py (unchanged)

Ollama (localhost:11434, never exposed to network)
```

### Authentication Design

Polkit is unusable from a remote browser. Replacement:

- `POST /auth/login` accepts a JSON body with `username` and `password` fields
- The handler calls `pam.pam().authenticate(username, supplied_password)` from
  the `python-pam` library, already declared in `pyproject.toml`
- On success, creates a `Session` using the existing session creation path in
  `src/reos/auth.py`, generating a 256-bit CSPRNG bearer string stored in
  `_session_store`
- Returns a JSON response containing `session_token` (the bearer value) and
  `username`
- All subsequent requests carry `Authorization: Bearer <value>` in the header
- A FastAPI dependency `require_auth()` validates the bearer via
  `auth.validate_session(bearer_value)` on every protected endpoint
- Session idle timeout is already 15 minutes (`SESSION_IDLE_TIMEOUT_SECONDS` in
  `src/reos/auth.py` line 36). The PWA refreshes the session via `POST /auth/refresh`

**Security note:** PAM verifies the Linux user password via the same underlying
mechanism Polkit uses. No new password infrastructure is introduced.

### RPC Dispatch Design

The PWA sends requests in this format:

```
POST /rpc
Content-Type: application/json
Authorization: Bearer <bearer-value>

{"jsonrpc": "2.0", "id": 1, "method": "chat/respond",
 "params": {"text": "what is next today?", "conversation_id": null}}
```

The FastAPI route processes this in four steps:
1. Validates the bearer value via the `require_auth()` dependency
2. Parses the JSON-RPC 2.0 body
3. Creates a `db = get_db()` instance
4. Dispatches to the same handler function that the stdio server calls

The dispatcher is implemented in a new `src/reos/http_rpc.py` module that imports
handler functions directly from `src/reos/rpc_handlers/` — the same functions
used by the stdio server. No handler is modified.

Two methods are explicitly refused by the HTTP dispatcher (they are Tauri/desktop-
specific):
- `system/open-terminal` — opens xterm on the PC desktop, meaningless remotely
- `debug/log` — frontend debugging only

All `auth/*` methods are refused in the `POST /rpc` endpoint with an error message
directing the client to use the dedicated `POST /auth/login` endpoint instead.

### Consciousness Streaming Design

The CAIRN async pattern is already polling-shaped. The SSE endpoint wraps it:

```
GET /rpc/events?text=...&conversation_id=...
Accept: text/event-stream
Authorization: Bearer <bearer-value>
```

The SSE endpoint:
1. Calls `handle_cairn_chat_async(db, text=..., conversation_id=...)` to start
   processing in a background thread
2. Enters a polling loop (250ms interval) calling `handle_consciousness_poll`
3. Emits each new consciousness event as an SSE message of type `consciousness`
4. When `handle_cairn_chat_status` returns `complete`, emits the final result as
   an SSE message of type `result`, then emits an empty `done` event and closes
5. If chat returns `error`, emits an SSE message of type `error` and closes

The PWA uses the `EventSource` API for this endpoint. For all other methods (Play
CRUD, health status, surfacing), the PWA uses regular `POST /rpc` fetches.

### PWA Frontend Design

A single-page HTML/CSS/JS application with no build step (vanilla JS ES modules,
served directly). PWA requirements:

- `manifest.json` — name, icons, `display: "standalone"`, `theme_color`
- `service-worker.js` — caches the app shell (HTML, CSS, JS, manifest) for offline
  display; chat and RPC requests always go to network
- `index.html`, `app.js`, `app.css`

Mobile-first layout:

```
+---------------------------+
|  Talking Rock      [menu] |
+---------------------------+
|  [CAIRN]  [ReOS]  [RIVA]  |  <- Agent tabs
+---------------------------+
|  CAIRN surfaced items     |  <- Collapsible, shows on load
|  - Meeting at 3pm         |
|  - Call Amy               |
+---------------------------+
|  [chat messages scroll]   |
+---------------------------+
|  +----------------------+ |
|  | Type a message...    | |  <- Sticky bottom bar
|  |                  [>] | |
|  +----------------------+ |
+---------------------------+
```

Consciousness/thinking steps appear in a slide-up drawer while CAIRN processes.

---

## Implementation Steps

### Step 0: Verify Prerequisites

Before any code is written, confirm:
- Tailscale is installed on the PC: `tailscale status`
- Tailscale app is available for the phone (iOS App Store or Google Play)
- `python-pam` is importable in the project environment: `python -c "import pam"`
- Port 8010 is not already bound to all interfaces: `ss -tlnp | grep 8010`
- `aiofiles` is available (required by `StaticFiles`): `python -c "import aiofiles"`

### Step 1: Tailscale Setup (PC)

```bash
# Install Tailscale
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up

# Record the Tailscale IP
tailscale ip -4

# Record the MagicDNS hostname (needed for TLS cert)
tailscale status --json | python3 -c \
  'import json,sys; d=json.load(sys.stdin); print(d["Self"]["DNSName"])'

# Obtain TLS certificate for HTTPS (required for service worker)
# Substitute your actual MagicDNS hostname below
sudo tailscale cert YOUR-HOSTNAME.ts.net

# Adjust key file permissions so reos user can read it
sudo chmod 640 /var/lib/tailscale/certs/YOUR-HOSTNAME.ts.net.key
sudo chown root:kellogg /var/lib/tailscale/certs/YOUR-HOSTNAME.ts.net.key

# Firewall: restrict port 8010 to Tailscale interface only
sudo ufw allow in on tailscale0 to any port 8010
sudo ufw deny 8010
sudo ufw reload
```

**Phone:** Install Tailscale, sign in with the same account, enable the VPN. The
phone will receive a Tailscale IP and can reach the PC's Tailscale hostname.

### Step 2: Add SSL Arguments to the `reos` CLI

**File to modify:** `src/reos/__main__.py`

Add two optional arguments to the `argparse` parser (after the existing arguments):

```python
parser.add_argument(
    "--ssl-certfile",
    default=None,
    help="Path to TLS certificate file (enables HTTPS)",
)
parser.add_argument(
    "--ssl-keyfile",
    default=None,
    help="Path to TLS private key file (enables HTTPS)",
)
```

Pass them through to `uvicorn.run()`:

```python
uvicorn.run(
    "reos.app:app",
    host=args.host,
    port=args.port,
    reload=not args.no_reload,
    log_level=args.log_level.lower(),
    ssl_certfile=args.ssl_certfile,   # new
    ssl_keyfile=args.ssl_keyfile,     # new
)
```

Uvicorn 0.30+ (already in the declared dependency range) accepts these keyword
arguments natively.

### Step 3: Extract Session Creation in `auth.py`

**File to modify:** `src/reos/auth.py`

Before implementing `http_auth.py`, read `auth.py` completely to understand where
`_session_store.insert()` is called and whether that path is separable from
`authenticate_polkit()`.

If the session creation logic is only reachable through the Polkit path, add a new
standalone function to `auth.py`:

```python
def create_session_from_pam(username: str, credential: str) -> dict[str, Any]:
    """Create a session after PAM verification.

    This is the HTTP/PWA auth path. Unlike authenticate_polkit() which shows
    a native GUI dialog, this path uses python-pam directly — the same
    underlying PAM stack, different invocation mechanism.

    Called by http_auth.py. Never called by the Tauri path.

    Returns dict with 'success', and on success also 'session_token' and
    'username'.
    """
    import pam as pam_lib
    p = pam_lib.pam()
    if not p.authenticate(username, credential):
        logger.warning("PAM auth failed for %s: %s", username, p.reason)
        return {"success": False, "error": "Authentication failed"}

    bearer_value = secrets.token_hex(32)
    session = Session(
        token=bearer_value,
        username=username,
        created_at=datetime.now(timezone.utc),
        last_activity=datetime.now(timezone.utc),
        key_material=_derive_key(username, credential),
    )
    _session_store.insert(session)
    logger.info("PAM session created for %s", username)
    return {"success": True, "session_token": bearer_value, "username": username}
```

Adapt the function body to match the actual internals of `auth.py` — this is a
sketch. The implementer must read `_derive_key()` and the `Session` constructor
to match exact signatures. Do NOT invent new session infrastructure — reuse exactly
what the Polkit path uses.

### Step 4: HTTP Auth Handler

**New file:** `src/reos/rpc_handlers/http_auth.py`

This thin module delegates to `auth.create_session_from_pam()` and wraps rate
limiting from the existing security module:

```python
from reos import auth
from reos.security import check_rate_limit, audit_log, AuditEventType, RateLimitExceeded

def http_login(*, username: str, credential: str) -> dict:
    try:
        check_rate_limit("auth")
    except RateLimitExceeded as e:
        audit_log(AuditEventType.RATE_LIMIT_EXCEEDED, {"category": "auth", "username": username})
        return {"success": False, "error": str(e)}

    result = auth.create_session_from_pam(username, credential)
    if result.get("success"):
        audit_log(AuditEventType.AUTH_LOGIN_SUCCESS, {"username": username})
    else:
        audit_log(AuditEventType.AUTH_LOGIN_FAILED, {"username": username})
    return result
```

### Step 5: HTTP RPC Dispatcher

**New file:** `src/reos/http_rpc.py`

This is a FastAPI `APIRouter`. Structure overview:

```python
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from reos import auth
from reos.db import get_db

# Import all needed handler functions from rpc_handlers/ subpackage
# (Do NOT import from ui_rpc_server.py)
from reos.rpc_handlers.chat import handle_chat_respond, handle_chat_clear
from reos.rpc_handlers.consciousness import (
    handle_cairn_chat_async, handle_cairn_chat_status,
    handle_consciousness_poll, handle_consciousness_start,
)
# ... continue importing all handlers needed for mobile feature set

router = APIRouter()
_bearer = HTTPBearer()


async def require_auth(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
) -> str:
    """FastAPI dependency: validates bearer value, returns it if valid."""
    bearer_val = creds.credentials
    if not auth.validate_session(bearer_val):
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    auth.refresh_session(bearer_val)
    return bearer_val
```

The `POST /rpc` handler reads the JSON-RPC body, extracts `method` and `params`,
and dispatches using the same lookup tables as the stdio server (`_SIMPLE_HANDLERS`,
`_STRING_PARAM_HANDLERS`, `_INT_PARAM_HANDLERS`), but defined locally in this
file against the imported handler functions.

The `GET /rpc/events` handler uses `StreamingResponse` with `asyncio.to_thread()`
to run the polling loop without blocking the event loop:

```python
@router.get("/rpc/events")
async def rpc_events(
    text: str,
    conversation_id: str | None = None,
    extended_thinking: bool = False,
    bearer_val: str = Depends(require_auth),
):
    db = get_db()

    async def stream():
        import asyncio, json
        # Start CAIRN async chat
        result = await asyncio.to_thread(
            handle_cairn_chat_async, db,
            text=text, conversation_id=conversation_id,
            extended_thinking=extended_thinking,
        )
        chat_id = result["chat_id"]
        since_idx = 0

        while True:
            await asyncio.sleep(0.25)
            poll = await asyncio.to_thread(
                handle_consciousness_poll, db, since_index=since_idx
            )
            for ev in poll["events"]:
                yield f"event: consciousness\ndata: {json.dumps(ev)}\n\n"
            since_idx = poll["next_index"]

            status = await asyncio.to_thread(
                handle_cairn_chat_status, db, chat_id=chat_id
            )
            if status["status"] == "complete":
                yield f"event: result\ndata: {json.dumps(status.get('result', {}))}\n\n"
                yield "event: done\ndata: {}\n\n"
                break
            elif status["status"] == "error":
                err = {"error": status.get("error", "unknown")}
                yield f"event: error\ndata: {json.dumps(err)}\n\n"
                break

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

### Step 6: Mount PWA in FastAPI App

**File to modify:** `src/reos/app.py`

Add after the existing imports and app definition:

```python
from fastapi.staticfiles import StaticFiles
from reos.http_rpc import router as rpc_router

# HTTP RPC routes (auth, RPC dispatch, SSE)
app.include_router(rpc_router)

# Serve PWA static assets at /app
# html=True: serves index.html for unrecognized paths (SPA navigation)
app.mount(
    "/app",
    StaticFiles(directory="apps/pwa", html=True),
    name="pwa",
)
```

If `aiofiles` is not installed, add `aiofiles>=23.0.0,<25.0.0` to `pyproject.toml`
dependencies before this step.

### Step 7: Create PWA Static Assets

**New directory:** `apps/pwa/`

No build step. Files served directly.

**`apps/pwa/manifest.json`**
```json
{
  "name": "Talking Rock",
  "short_name": "TalkingRock",
  "description": "Local-first AI assistant",
  "start_url": "/app/",
  "display": "standalone",
  "background_color": "#1a1a2e",
  "theme_color": "#4a90e2",
  "icons": [
    {"src": "/app/icons/icon-192.png", "sizes": "192x192", "type": "image/png"},
    {"src": "/app/icons/icon-512.png", "sizes": "512x512", "type": "image/png"}
  ]
}
```

**`apps/pwa/service-worker.js`**

The service worker handles:
- Install event: fetch and cache `index.html`, `app.js`, `app.css`, `manifest.json`,
  icon files into a versioned cache (e.g., `tr-shell-v1`)
- Fetch event: cache-first strategy for app shell URLs; network-only strategy for
  `/rpc`, `/auth/*`, and `/rpc/events`

**`apps/pwa/index.html`**

Minimal HTML5 document with:
- `<link rel="manifest" href="/app/manifest.json">`
- `<meta name="theme-color" content="#4a90e2">`
- `<meta name="viewport" content="width=device-width, initial-scale=1">`
- `<script type="module" src="/app/app.js"></script>`
- Inline service worker registration before the module script

**`apps/pwa/app.js`** — key components (ES modules, no bundler):

- `AuthManager`: handles the login form submission (`POST /auth/login`), stores
  the returned bearer value in `sessionStorage` (not `localStorage`), injects
  `Authorization` headers into all fetch calls, handles 401 by showing the login
  form again
- `AgentSelector`: three-tab strip (CAIRN / ReOS / RIVA) that sets `agent_type`
  for outgoing chat requests
- `ChatView`: renders message history, handles the input bar, initiates chat via
  the SSE endpoint for CAIRN or `POST /rpc` `chat/respond` for ReOS/RIVA
- `CairnSurface`: calls `POST /rpc` with `cairn/attention` on load and after each
  response, renders surfaced items in the collapsible header panel
- `ConsciousnessPane`: slide-up drawer populated by `consciousness` SSE events;
  hides after `done` event received
- `ConversationManager`: tracks `conversation_id` in `sessionStorage`, provides
  conversation resume from history

**`apps/pwa/app.css`** — mobile-first:

- CSS custom properties for colors and spacing
- Flexbox layout with sticky bottom input bar (`position: sticky; bottom: 0`)
- Agent tab strip with horizontal overflow
- Chat bubble layout with role-based alignment
- Consciousness drawer with CSS `transform: translateY` transition

**Icons:** Two PNG files at 192x192 and 512x512 pixels. A simple geometric icon
or the Talking Rock wordmark. These are required for the PWA to install correctly
on phones. They can be created with any image editor and do not need to be elaborate.

### Step 8: Add Conversation History RPC Methods

The database method already exists at `src/reos/db.py` line 744
(`db.iter_conversations(limit)`). Add two new handler functions:

**File to modify:** `src/reos/rpc_handlers/chat.py`

```python
def handle_conversations_list(db: Database, *, limit: int = 20) -> dict[str, Any]:
    """List recent conversations for the PWA conversation picker.

    Returns conversations sorted by most recent activity first.
    """
    rows = db.iter_conversations(limit=limit)
    return {"conversations": rows}


def handle_conversation_messages(
    db: Database,
    *,
    conversation_id: str,
    limit: int = 50,
) -> dict[str, Any]:
    """Get messages for a conversation to restore chat history in the PWA."""
    rows = db.get_messages(conversation_id=conversation_id, limit=limit)
    return {"messages": rows, "conversation_id": conversation_id}
```

Register these in `src/reos/http_rpc.py` in the RPC dispatch table. Optionally
also register in `src/reos/ui_rpc_server.py` for desktop parity — this is a
separate decision and not required for the PWA.

### Step 9: Production Startup Script

**New file:** `scripts/start-pwa.sh`

```bash
#!/usr/bin/env bash
# Start Talking Rock with PWA support over Tailscale HTTPS.
# Run this instead of 'reos' when you want mobile access.
set -euo pipefail

CERT_DIR="/var/lib/tailscale/certs"
HOSTNAME="$(tailscale status --json | \
  python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["Self"]["DNSName"].rstrip("."))')"

exec reos \
    --host 0.0.0.0 \
    --port 8010 \
    --no-reload \
    --ssl-certfile "${CERT_DIR}/${HOSTNAME}.crt" \
    --ssl-keyfile "${CERT_DIR}/${HOSTNAME}.key"
```

**Optional systemd user unit** for auto-start on login:

`~/.config/systemd/user/talking-rock-pwa.service`:
```ini
[Unit]
Description=Talking Rock PWA Server
After=network.target tailscaled.service

[Service]
Type=simple
ExecStart=/home/kellogg/dev/Talking Rock/scripts/start-pwa.sh
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
```

Enable: `systemctl --user enable --now talking-rock-pwa`

---

## Files Affected

### New Files to Create

| File | Purpose |
|------|---------|
| `src/reos/rpc_handlers/http_auth.py` | PAM-based HTTP login handler |
| `src/reos/http_rpc.py` | FastAPI router: POST /rpc, GET /rpc/events, auth endpoints |
| `apps/pwa/index.html` | PWA app shell HTML |
| `apps/pwa/app.js` | Chat UI logic (ES modules, no bundler) |
| `apps/pwa/app.css` | Mobile-first styles |
| `apps/pwa/manifest.json` | PWA install manifest |
| `apps/pwa/service-worker.js` | App shell caching service worker |
| `apps/pwa/icons/icon-192.png` | PWA icon (192x192 px) |
| `apps/pwa/icons/icon-512.png` | PWA icon (512x512 px) |
| `scripts/start-pwa.sh` | Startup script with Tailscale HTTPS |

### Files to Modify

| File | Change |
|------|--------|
| `src/reos/app.py` | Mount HTTP RPC router; mount StaticFiles at `/app` |
| `src/reos/__main__.py` | Add `--ssl-certfile` and `--ssl-keyfile` CLI arguments |
| `src/reos/auth.py` | Add `create_session_from_pam()` as standalone callable |
| `src/reos/rpc_handlers/chat.py` | Add `handle_conversations_list`, `handle_conversation_messages` |

### Files NOT Modified

| File | Reason |
|------|--------|
| `src/reos/ui_rpc_server.py` | Stdio server for Tauri is completely untouched |
| `apps/reos-tauri/` | Desktop app is completely untouched |
| All existing `rpc_handlers/*.py` (except `chat.py`) | Called, not modified |
| `src/reos/providers/` | Ollama integration unchanged |
| `src/reos/cairn/` | CAIRN pipeline unchanged |

---

## Risks and Mitigations

### Risk 1: Session Creation Path in `auth.py` Entangles Polkit

**Risk:** The `login()` function in `auth.py` calls `authenticate_polkit()` (line
128). The session creation step (inserting into `_session_store`) may not be
separable from the Polkit invocation.

**Evidence:** Must read `auth.py` completely before implementing. The path from
`login()` to `_session_store.insert()` needs to be traced.

**Mitigation:** Add `create_session_from_pam()` to `auth.py` as described in
Step 3. Keep all session management in `auth.py`. The HTTP auth handler in
`http_auth.py` only calls this new function — it never directly touches
`_session_store` or `Session`.

### Risk 2: Shared `_session_store` Between HTTP and Stdio Contexts

**Risk:** If both FastAPI and Tauri import `auth.py`, they share the module-level
`_session_store` singleton.

**Assessment:** This is acceptable. The stdio server validates sessions via the
Rust layer injecting `__session` into params (line 705 in `ui_rpc_server.py`),
not by calling `auth.validate_session()` directly. There is no cross-contamination.

**Mitigation:** Document this shared store in a comment in `http_auth.py` and in
`auth.py`.

### Risk 3: Handler Concurrency Under HTTP

**Risk:** Handler functions were designed for a single-threaded stdio server. Under
FastAPI, multiple concurrent requests could call the same handlers.

**Assessment:** The `_cairn_chat_lock` threading lock already protects
`_active_cairn_chats`. Uvicorn runs sync handlers in a thread pool. The existing
thread safety is sufficient.

**Mitigation:** Use `asyncio.to_thread()` when calling sync handlers from async
FastAPI routes to avoid blocking the event loop.

### Risk 4: Polkit Accidentally Triggered from HTTP Context

**Risk:** If the HTTP dispatcher routes any call to the Polkit authentication path,
`pkcheck` would be called from an HTTP context with no display, hanging indefinitely.

**Mitigation:** The `POST /rpc` endpoint explicitly refuses all `auth/*` method
names with an instructive error message. This is enforced structurally in
`http_rpc.py` — there is no code path from `POST /rpc` to any auth handler.

### Risk 5: Service Worker Requires HTTPS

**Risk:** Service Workers only register on HTTPS (or localhost). Without HTTPS, the
PWA cannot be installed to the home screen and offline caching does not work.

**Mitigation:** Use `tailscale cert` to obtain a TLS certificate (Step 1). This
certificate is trusted by devices with the Tailscale app installed, which the phone
will have. Start uvicorn with `--ssl-certfile` and `--ssl-keyfile` (Step 2).

**Fallback:** If HTTPS is deferred, basic chat over HTTP still works. The service
worker will not register, but the web UI loads and functions. HTTPS should be
completed before declaring the PWA production-ready.

### Risk 6: `aiofiles` Missing

**Risk:** `StaticFiles` in FastAPI requires `aiofiles` which is not currently in
`pyproject.toml`.

**Mitigation:** Verify with `python -c "import aiofiles"` in the project
environment. If missing, add `aiofiles>=23.0.0,<25.0.0` to `pyproject.toml`
dependencies before Step 6.

### Risk 7: Mobile Browser Kills EventSource on Backgrounding

**Risk:** Mobile browsers (especially iOS Safari) terminate EventSource connections
when the app is backgrounded. The consciousness stream may be cut off mid-processing.

**Mitigation:**
- Add `Last-Event-ID` support: the SSE endpoint includes an ID on each event.
  When the client reconnects, it sends the last event ID and the server resumes
  from that point.
- All events carry full payloads, not diffs. A reconnected stream can resume cleanly.
- `app.js` implements a polling fallback: if `EventSource` fails, fall back to
  polling `cairn/chat_status` via `POST /rpc` every 1 second. The same data is
  available through both paths.

---

## Tailscale Setup (Detailed)

### On the Linux PC

```bash
# Install
curl -fsSL https://tailscale.com/install.sh | sh

# Connect to your Tailscale network
sudo tailscale up

# Record your Tailscale IP (stable across reboots)
tailscale ip -4

# Record your MagicDNS hostname (needed for TLS certificate)
tailscale status --json | python3 -c \
  'import json,sys; d=json.load(sys.stdin); print(d["Self"]["DNSName"])'

# Obtain TLS certificate
# Replace YOUR-HOSTNAME.ts.net with your actual hostname from the command above
sudo tailscale cert YOUR-HOSTNAME.ts.net

# Make cert readable by reos (key file must stay restricted)
sudo chmod 640 /var/lib/tailscale/certs/YOUR-HOSTNAME.ts.net.key
sudo chown root:kellogg /var/lib/tailscale/certs/YOUR-HOSTNAME.ts.net.key
sudo chmod 644 /var/lib/tailscale/certs/YOUR-HOSTNAME.ts.net.crt

# Firewall: Tailscale interface only for port 8010
sudo ufw allow in on tailscale0 to any port 8010
sudo ufw deny 8010
sudo ufw reload

# Verify firewall rules
sudo ufw status verbose | grep 8010

# Test HTTPS works (from the PC itself)
curl https://YOUR-HOSTNAME.ts.net:8010/health
```

### On the Phone

1. Install Tailscale from the iOS App Store or Google Play
2. Sign in with the same Tailscale account used on the PC
3. Enable Tailscale VPN (the app manages the connection)
4. Open a mobile browser and navigate to:
   `https://YOUR-HOSTNAME.ts.net:8010/app/`
5. Log in with your Linux username and password
6. Tap "Add to Home Screen" to install the PWA

### Restricting Access with Tailscale ACLs (Recommended)

By default, all devices on the same Tailscale account can reach each other. To
restrict the ReOS server to only the phone:

1. Log into the Tailscale admin console at https://login.tailscale.com/admin/acls
2. Add an ACL rule allowing only the phone's Tailscale node to reach port 8010 on
   the PC. Tailscale ACLs support node-level targeting by tag or IP.
3. This prevents any future device added to the Tailscale network from accessing
   the ReOS server without an explicit ACL change.

---

## Security Considerations

### New Attack Surface

| Threat | Mitigation |
|--------|-----------|
| Unauthorized access from other Tailscale devices | Tailscale ACLs restrict to phone's node only |
| Brute-force login attempts | PAM locks accounts per system policy; `check_rate_limit("auth")` from `src/reos/security.py` applied in `POST /auth/login` |
| Session bearer interception | Tailscale WireGuard encryption plus TLS in transit; bearer stored in `sessionStorage` not `localStorage` |
| CSRF | Not applicable — `Authorization` header with bearer cannot be forged by cross-origin pages |
| Prompt injection via chat | Already mitigated by `detect_prompt_injection()` in `src/reos/security.py` |
| Remote command execution | Approval system unchanged — user must explicitly approve on phone |
| Phone lost or stolen | Revoke phone's Tailscale node from admin console; invalidates all access |

### What Is Not Exposed

- Ollama (port 11434) stays on `127.0.0.1` — never accessible from the network
- The stdio RPC server remains a local subprocess of Tauri only
- `~/.reos-data/` filesystem — all access goes through the Python process
- System commands still go through the approval queue — the phone user must
  explicitly tap "approve"

### Bearer Storage in the PWA

- Bearer value stored in `sessionStorage` — cleared when the PWA/tab is closed
- If the user installs the PWA to home screen: `sessionStorage` persists for the
  PWA instance, cleared when the PWA is force-quit
- Session idle timeout is 15 minutes (`SESSION_IDLE_TIMEOUT_SECONDS` in `auth.py`)
- Consideration: a separate `REOS_HTTP_SESSION_TIMEOUT_SECONDS` environment variable
  can be added to `settings.py` to allow a shorter timeout for remote HTTP sessions
  versus the local desktop sessions

---

## Testing Strategy

### Unit Tests

**New file:** `tests/test_http_rpc.py`

Use FastAPI's `TestClient`. Mock `pam.pam()` to avoid requiring a real Linux user
account in CI (real PAM authentication requires an actual system account and
interactive setup that is not available in automated test environments).

Test cases to implement:

```
1. POST /auth/login with valid mocked PAM -> 200, response body has session_token key
2. POST /auth/login with invalid mocked PAM -> 200, response body has success=False
3. POST /rpc without Authorization header -> 403 (HTTPBearer enforcement)
4. POST /rpc with expired bearer -> 401
5. POST /rpc with valid bearer, method="health/status" -> dispatches to handler
6. POST /rpc with method="auth/login" -> error message directing to /auth/login
7. POST /rpc with method="system/open-terminal" -> not-supported error
8. GET /rpc/events returns Content-Type: text/event-stream
9. POST /auth/login rate-limited after N failed attempts
10. GET /app/ returns 200 with HTML content-type
11. GET /app/manifest.json returns 200 with correct JSON structure
```

**New file:** `tests/test_http_auth.py`

```
1. http_login() with mocked PAM success returns dict with session_token key
2. http_login() with mocked PAM failure returns dict with success=False
3. Session created by http_login is retrievable via auth.validate_session()
4. Session created by http_login expires after idle timeout
5. Rate limiting triggers after 5 rapid failed calls
```

### Integration Tests (Manual, from Phone)

Before declaring done, perform these checks with a real phone on Tailscale:

1. Open `https://YOUR-HOSTNAME.ts.net:8010/health` in mobile browser — returns JSON
2. Navigate to `/app/` — login form appears
3. Enter correct Linux credentials — dashboard appears with CAIRN surfaced items
4. Type a CAIRN question — response arrives, consciousness drawer animates
5. Switch to ReOS tab — send a safe system query — response arrives
6. Switch to RIVA tab — tab is present and routes to RIVA agent
7. Ask ReOS to do something needing approval — approval prompt appears on phone
8. Tap "Add to Home Screen" — icon appears on home screen — opening it shows
   standalone mode (no browser chrome)
9. Enable airplane mode — open PWA — login form or cached UI shell appears (not
   a blank page or browser error)
10. Wait 15 minutes idle — next chat request returns 401 — login form appears
11. Enter wrong credentials 6 times rapidly — further attempts are rate-limited

### Regression Tests

Run the full existing test suite before and after all changes:

```bash
pytest tests/ -v --cov=reos
# Must pass with coverage >= 45%
```

Pay particular attention to:
- `tests/test_cairn_intent_engine.py` — CAIRN pipeline must be unchanged
- `tests/test_rpc_handlers_base.py` — RPC base class must be unchanged
- `tests/test_play.py` — Play CRUD must be unchanged

---

## Definition of Done

- [ ] Tailscale running on PC and phone; PC Tailscale hostname reachable from phone
      browser (verified by loading `/health` endpoint in mobile browser)
- [ ] `ufw` rules verified: port 8010 accessible from `tailscale0` interface, denied
      from other interfaces
- [ ] TLS certificate obtained via `tailscale cert` and uvicorn serving HTTPS
      (verified by `curl https://...` without `-k` flag)
- [ ] `POST /auth/login` validates via PAM and returns a response containing a
      session bearer value
- [ ] `POST /rpc` dispatches at minimum: `chat/respond`, `cairn/chat_async`,
      `cairn/chat_status`, `consciousness/poll`, `consciousness/start`,
      `consciousness/snapshot`, `cairn/attention`, `play/acts/list`,
      `play/scenes/list_all`, `health/status`, `conversations/list`, `chat/clear`
- [ ] `GET /rpc/events` returns `Content-Type: text/event-stream` and delivers
      `consciousness` events followed by a `result` event and a `done` event
- [ ] PWA `manifest.json` passes Chrome DevTools Lighthouse Manifest audit
      (all required fields present, icons load correctly)
- [ ] Service worker registers and caches the app shell (verified via browser
      DevTools Application > Service Workers and Cache Storage)
- [ ] PWA can be installed to phone home screen and opens in standalone mode
      (no browser address bar visible)
- [ ] Offline: opening PWA in airplane mode shows the UI shell — no blank page
- [ ] CAIRN chat works end-to-end from the phone: message sent, response received,
      consciousness events visible in the drawer
- [ ] RIVA tab is present and routes to `agent_type="riva"` in chat dispatch
- [ ] ReOS tab is present and routes to `agent_type="reos"` in chat dispatch
- [ ] Approval flow works remotely: system command shows approval UI on phone
- [ ] Rate limiting on `POST /auth/login` active (tested with 6 rapid bad logins)
- [ ] Existing pytest suite passes with coverage >= 45%
- [ ] `src/reos/ui_rpc_server.py` is unmodified (confirmed via `git diff`)
- [ ] `apps/reos-tauri/` is unmodified (confirmed via `git diff`)
- [ ] `scripts/start-pwa.sh` is executable (`chmod +x`) and works end-to-end

---

## Unknowns and Assumptions Requiring Validation

**1. `auth.create_session_from_pam()` does not yet exist.**
The session creation path in `auth.py` is entangled with Polkit. Read `auth.py`
completely before implementing Step 3. The implementer must trace the exact path
from `login()` to `_session_store.insert()` and extract it cleanly.

**2. `aiofiles` availability.**
`StaticFiles` requires `aiofiles`. Not currently in `pyproject.toml`. Verify with
`python -c "import aiofiles"` before Step 6.

**3. Tailscale cert file permissions.**
`sudo tailscale cert` writes files owned by root. The `reos` process runs as the
user, not root. Verify the key file is readable by the user after the permission
changes in Step 1. If the user cannot read the key file, uvicorn will fail to start
with HTTPS.

**4. PAM stack behavior.**
`pam.pam().authenticate()` behavior depends on the system PAM configuration.
Some systems run `pam_faillock` which locks accounts after N failures — this is
desirable but affects how integration tests for rate limiting should be written
(test the application layer, not the PAM layer).

**5. Exact RPC method name for CAIRN surfacing.**
From `ui_rpc_server.py` line 443, `_SIMPLE_HANDLERS` maps `"cairn/attention"` to
`_handle_cairn_attention`. Confirm against `src/reos/rpc_handlers/system.py` that
this handler returns surfaced items in a format the PWA can render.

**6. `conversations/list` not in desktop app.**
`db.iter_conversations()` exists but is not currently exposed as an RPC method in
`ui_rpc_server.py`. The PWA plan adds it only to `http_rpc.py`. If the desktop
Tauri app should also support conversation history browsing, that is a separate
task beyond this plan's scope.

---

## Confidence Assessment

**Recommended approach confidence: High (8 out of 10)**

The core risk factors all have clear solutions using existing infrastructure:
- Authentication: `python-pam` is already declared; session infrastructure is
  reusable once `create_session_from_pam()` is extracted
- RPC dispatch: Handler functions are already decoupled from the transport layer
  and can be called from FastAPI routes directly
- Static file serving: FastAPI `StaticFiles` is a standard pattern
- Consciousness streaming: SSE with `asyncio.to_thread()` maps cleanly to the
  existing polling design

The main unknowns are:
- Exact shape of `auth.py`'s session creation path (1-2 hours of reading)
- Tailscale cert file permissions (5 minutes to check)

Neither is a blocker. Both have clear fallback paths.

The approach is purely additive. The stdio server and Tauri app are completely
untouched. Rollback requires reverting `src/reos/app.py` and deleting `apps/pwa/`
and `src/reos/http_rpc.py`.
