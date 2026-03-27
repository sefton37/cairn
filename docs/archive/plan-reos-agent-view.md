# Plan: ReOS Agent View — Phased Implementation

**Date:** 2026-03-13
**Status:** Proposed — awaiting approval before any implementation begins

---

## Context

### What exists today

**ReOS** (`/home/kellogg/dev/ReOS/`) is a fully-functional Python backend with:
- 50+ system monitoring and execution functions in `linux_tools.py`
- `ReOSAgent` that translates natural language to command proposals
- `shell_propose.py`: LLM-powered NL to command pipeline with 4-layer sanitization
- `streaming_executor.py`: subprocess-based command runner with polling output model
- `system_index.py` / `SystemIndexer`: SQLite-backed daily system snapshots
- No RPC bridge for Tauri. No PTY support.

**Cairn Tauri app** (`/home/kellogg/dev/Cairn/apps/cairn-tauri/`) has:
- `reosView.ts`: a 62-line placeholder returning a "Coming soon" screen
- A working `cairnView.ts` as the reference implementation pattern
- A JSON-RPC-over-stdio channel: TypeScript -> `kernel_request` Tauri command -> Rust `KernelProcess` -> Python `ui_rpc_server.py`
- The `ui_rpc_server.py` dispatch table (`_SIMPLE_HANDLERS`, `_STRING_PARAM_HANDLERS`, `_INT_PARAM_HANDLERS`) where new `reos/*` methods must be registered
- A session/auth guard: every non-auth RPC call must carry `__session` injected by the Rust layer
- No WebSocket support. No Tauri events in use. No streaming transport.

**Dependency gap:** `cairn/pyproject.toml` does not list `reos` as a dependency. ReOS has no `rpc_handlers/` module.

---

## Architecture Questions — Resolved

### Q1: PTY Location — Python-side vs Rust-side

**Recommendation: Python-side PTY via the `pty` module.**

Rationale:
- The NL interception point must live where ReOS logic lives. A Rust PTY (`portable-pty`) would require bridging NL detection back to Python anyway, adding a round-trip with no gain.
- The existing `kernel.rs` `KernelProcess` architecture is synchronous request/response (one blocking `read_line` per request). A Rust PTY would need a parallel async channel, requiring significant Rust changes.
- Python's `pty` module is in the standard library — no new Python dependency.
- The tradeoff is that Python PTY is slightly less performant for raw terminal throughput, but for a local developer tool that is not a meaningful concern.

The alternative (Rust `portable-pty`) is set aside because: it would require adding a Cargo dependency, restructuring `kernel.rs` to manage a separate child process and event loop, and exporting PTY data over a new channel — all before NL interception is even possible. Complexity is out of proportion to the benefit.

**Correction after further analysis:** The Python PTY approach has a critical flaw — the Python process communicates with Rust via synchronous stdio JSON-RPC. There is no mechanism for the Python process to push PTY output to Rust asynchronously over that channel. This makes Python-side PTY unworkable without a second communication channel (e.g., a Unix socket).

**Revised recommendation: Rust-side PTY via `portable-pty`**, with NL interception at the frontend (see Q2). The Rust layer manages the PTY, emits output as Tauri events, and the NL pipeline in Python is invoked only when the frontend decides to call `reos/propose` before sending to the PTY.

### Q2: NL Interception Point — Frontend vs Shell Hook

**Recommendation: Frontend intercept at the input line, before PTY.**

The terminal input field intercepts Enter. The frontend classifies the input: if it looks like a shell command (starts with a known binary, contains shell operators, etc.), it passes directly to the PTY via `pty_write`. If it looks like natural language, it calls `reos/propose` RPC, shows the proposal UI, and only sends the approved command to the PTY.

This is the same heuristic already implemented in `shell_propose.py`'s `looks_like_command()`. The frontend will apply a fast client-side pre-check; the `reos/propose` endpoint will apply the full Python-side check and LLM call.

The alternative (shell hook inside the PTY) is set aside because: it requires injecting wrapper scripts into the shell environment, managing signals across the PTY boundary, and parsing shell output to find "was that NL or a command?" This is fragile and breaks shell state tracking.

### Q3: Streaming Protocol — How PTY Output Reaches the Frontend

**Recommendation: Tauri event emitter — `tauri::Emitter::emit()` from a background thread.**

The existing JSON-RPC channel is synchronous and blocking: Rust holds the kernel's stdout `BufReader` and reads one line per request. It cannot also stream PTY output on the same channel.

The solution: when the PTY subprocess is running, a dedicated Rust thread reads PTY output chunks and emits them as Tauri events (`app_handle.emit("reos://pty-output", chunk_as_string)`). The frontend listens with `listen("reos://pty-output", handler)` from `@tauri-apps/api/event`.

This requires:
- Storing an `AppHandle` in app state (standard Tauri 2.x pattern via `tauri::Manager::app_handle()`)
- A separate `PtyState` managed in Rust alongside the existing `KernelState`
- A Rust thread that owns the PTY master fd and emits events

The alternatives considered:
- **Polling via JSON-RPC**: Each poll would call `reos/pty_poll` -> Python reads from PTY -> returns lines. But the PTY is now Rust-side, so this would be a Rust-to-Rust poll which is unnecessary. And even for a Python-side PTY, polling introduces up to 100ms latency and blocks the JSON-RPC channel during reads.
- **WebSocket from Python**: Would require adding a network listener to the Python process, contradicting the local-only, stdio-based design principle established in `ui_rpc_server.py`'s header comment.

Tauri events are the correct solution: they are the intended mechanism for push-to-frontend communication in Tauri 2.x, they don't require a network listener, and they don't block the JSON-RPC channel.

### Q4: Dashboard Data Source — Direct `linux_tools` calls vs `SystemIndexer` cache

**Recommendation: Direct `linux_tools` calls via RPC for live dashboard data; `SystemIndexer` snapshots for the NL context only.**

The dashboard polls every 5 seconds for CPU/RAM/disk/network vitals. These values change continuously; serving them from a daily snapshot would be wrong. The `linux_tools.py` functions (`get_system_info()`, which returns `SystemInfo` with `cpu_percent`, `memory_used_mb`, `disk_used_gb`, etc.) already call `psutil` directly — they are cheap, fast, and designed for this use case.

The `SystemIndexer` daily snapshot is still useful for the NL pipeline (giving the LLM rich context about packages, services, container state) but is not the right source for live vitals.

### Q5: Terminal Emulator Frontend — xterm.js vs custom rendering

**Recommendation: xterm.js.**

xterm.js handles ANSI escape codes, color output, cursor movement, scrollback, and selection — all things that real terminal programs emit. A custom renderer would need to re-implement this from scratch and would break immediately with programs that use ncurses, color output, or progress bars.

xterm.js is an npm-installable library. The Cairn Tauri frontend uses a TypeScript build pipeline (Vite). Adding xterm.js as an npm dependency is straightforward.

The alternative (custom rendering) is set aside: it is months of work to get right and will still be wrong for half of real terminal programs.

---

## Approaches Considered

### Approach A (Recommended): Phased — PTY via Tauri events, NL intercept at frontend

Build in six independent phases. Dashboard first (establishes RPC plumbing), PTY second (establishes streaming), NL intercept third, polish thereafter. Each phase ships something visible.

- Complexity: Medium overall; high only in Phase 2 (PTY Rust plumbing)
- Reversibility: High — each phase is additive
- Alignment: Follows existing patterns (JSON-RPC for request/response, new event channel for streaming)
- Risk: Highest in Phase 2 (new Rust code for PTY management)

### Approach B: Polling-only PTY (no Tauri events)

Frontend polls `reos/pty_poll` every 100ms. Simpler Rust layer (no `AppHandle` event emission), but:
- Introduces perceptible latency for interactive terminal programs
- Not suitable for interactive programs that update in place (vim, htop)
- The polling requests would compete with dashboard polling on the same JSON-RPC channel

Set aside because the user experience cost is high and the simplicity gain is modest. Could be used as a fallback for a proof-of-concept only.

### Approach C: Separate PTY sidecar process

A separate Rust or Python sidecar manages the PTY and communicates via WebSocket or Unix socket.

Set aside because: introduces a third process to manage, a new network surface, and deployment complexity. The Talking Rock philosophy is minimal footprint. This is over-engineered for a local developer tool.

---

## Implementation Phases

---

### Phase 1: Dashboard Foundation

**What it delivers:** Left half of the ReOS view populates with live system vitals — CPU, RAM, disk, network, hostname, distro, uptime. Right half remains a terminal placeholder. The view is no longer a stub.

**Architecture decisions:**
- Add `reos` as an editable dependency in Cairn's `pyproject.toml`
- Create `src/reos/rpc_handlers/system.py` in ReOS — mirrors the pattern in `src/cairn/rpc_handlers/` using the `@rpc_handler` decorator
- Register `reos/vitals` and `reos/system_info` in Cairn's `ui_rpc_server.py` dispatch table
- Frontend polls every 5 seconds via `kernelRequest("reos/vitals", {})` and updates DOM in place
- Use `psutil.cpu_percent(interval=0)` (non-blocking) not `interval=1` (blocks 1 second)

**Files affected:**

| File | Action |
|------|--------|
| `/home/kellogg/dev/Cairn/pyproject.toml` | Add `reos` editable dependency |
| `/home/kellogg/dev/ReOS/src/reos/rpc_handlers/__init__.py` | Create |
| `/home/kellogg/dev/ReOS/src/reos/rpc_handlers/system.py` | Create: `handle_reos_vitals`, `handle_reos_system_info` |
| `/home/kellogg/dev/Cairn/src/cairn/ui_rpc_server.py` | Import and register `reos/*` handlers in `_SIMPLE_HANDLERS` |
| `/home/kellogg/dev/Cairn/apps/cairn-tauri/src/reosView.ts` | Replace stub with split-screen layout; left pane polls vitals |
| `/home/kellogg/dev/Cairn/apps/cairn-tauri/src/types.ts` | Add `ReosVitalsResult`, `ReosSystemInfoResult` types |

**Dependencies on prior phases:** None. This is the foundation.

**Complexity:** Small

**Risks:**
- `psutil.cpu_percent(interval=1)` blocks the RPC thread for 1 second. Use `interval=0`. The first call returns 0.0 — document this in the handler.
- The `@rpc_handler` decorator is defined in `cairn.rpc_handlers._base`. Importing it from ReOS creates a dependency on Cairn's internal module. This works since Cairn is installed in the same venv, but it is architecturally unclean. The implementer should decide: (a) import from cairn directly, (b) duplicate the decorator in ReOS, or (c) move it to `trcore`. Option (c) is cleanest long-term.
- ReOS handlers receive a `db: Database` (Cairn's database) as their first param from the dispatch table. Vitals handlers don't need it — they can accept and ignore it. Document the convention.

---

### Phase 2: PTY Terminal — Rust Plumbing

**What it delivers:** Right half of the ReOS view is a real xterm.js terminal. The user can type shell commands, press Enter, and see real output. `cd` persists. Environment variables work. Color output and cursor control work. No natural language support yet — plain command passthrough only.

**Architecture decisions:**
- Add `PtyState` to Tauri app state: `Arc<Mutex<Option<PtyProcess>>>`
- `PtyProcess` owns: the spawned shell `Child`, its master fd for writing, and a `JoinHandle` for the reader thread
- The reader thread loops: reads chunks from the PTY master fd, emits `app_handle.emit("reos://pty-output", chunk)`
- New Tauri command `pty_start(session_token, shell)`: validates session, spawns `/bin/bash` (or `$SHELL`) under a PTY via `portable-pty`
- New Tauri command `pty_write(session_token, data)`: validates session, writes bytes to PTY master
- New Tauri command `pty_resize(session_token, cols, rows)`: sends window size change
- New Tauri command `pty_stop(session_token)`: terminates the shell gracefully
- Frontend: attaches xterm.js to the right pane; listens for `reos://pty-output` events and writes to terminal; on user input, calls `pty_write`

**Files affected:**

| File | Action |
|------|--------|
| `/home/kellogg/dev/Cairn/apps/cairn-tauri/src-tauri/Cargo.toml` | Add `portable-pty` |
| `/home/kellogg/dev/Cairn/apps/cairn-tauri/src-tauri/src/pty.rs` | Create: `PtyProcess`, `PtyState`, reader thread, event emission |
| `/home/kellogg/dev/Cairn/apps/cairn-tauri/src-tauri/src/main.rs` | Add `PtyState` to `.manage()`; register `pty_start`, `pty_write`, `pty_resize`, `pty_stop` |
| `/home/kellogg/dev/Cairn/apps/cairn-tauri/src/reosView.ts` | Add xterm.js terminal in right pane; wire PTY commands and events |
| `package.json` (Tauri frontend) | Add `@xterm/xterm`, `@xterm/addon-fit` |

**Dependencies on prior phases:** Phase 1 (split-screen layout established).

**Complexity:** Large — new Rust module, PTY Unix system programming, cross-process event emission.

**Risks:**
- PTY fd leaks on crash. Mitigate: implement `Drop` for `PtyProcess` that kills the child and closes the master fd.
- The Tauri `AppHandle` must be stored in state or cloned into the reader thread. Tauri 2.x supports `app_handle.clone()` for this purpose. Verify the `tauri::Emitter` trait is in scope in the reader thread context.
- `portable-pty` is a well-established crate (MIT license, maintained by Wez Furlong) but adds a Cargo dependency. Evaluate at Phase 2 start; fallback is `libc::openpty` directly with more manual setup code.
- xterm.js may conflict with the Tauri webview's Content Security Policy. Check `tauri.conf.json` for CSP settings before integrating xterm.js.
- Tauri 2.x may require events to be declared in `tauri.conf.json` capabilities. Verify whether `reos://pty-output` and `reos://pty-closed` need explicit capability declarations.
- Shell startup inherits the Tauri process environment, including `CAIRN_PYTHON` and `PATH`. This is correct. Verify with `env` as the first command in the terminal.
- `pty_stop` must be called when the user navigates away from the ReOS view. The agent bar's `onSwitchAgent` callback is the hook point in `main.ts`.

---

### Phase 3: Natural Language Interception

**What it delivers:** The terminal input line gains NL detection. When the user types a natural language phrase and presses Enter, the frontend calls `reos/propose` instead of sending to the PTY. The response is shown as a proposal card above the terminal: the proposed command, an explanation, and Approve / Edit / Reject buttons. Approving sends the command to the PTY.

**Architecture decisions:**
- New RPC endpoint `reos/propose` in `reos/rpc_handlers/propose.py` — thin wrapper over `shell_propose.propose_command()`
- The frontend applies a fast pre-check: if the input starts with `/`, `./`, `~`, or contains `|`, `>`, `<`, `&&`, `||`, `;`, `$`, it is treated as a shell command and goes directly to the PTY. Otherwise it goes to `reos/propose`.
- A keyboard shortcut (Shift+Enter) bypasses NL detection and always sends raw to PTY.
- The proposal card is rendered as a floating overlay above the terminal input (not a separate pane), so it does not disrupt the terminal scroll position.
- If the LLM takes more than 3 seconds, a spinner is shown and the terminal input is disabled until the response arrives.
- "Edit" drops the proposed command into the terminal input for the user to modify before sending.

**Files affected:**

| File | Action |
|------|--------|
| `/home/kellogg/dev/ReOS/src/reos/rpc_handlers/propose.py` | Create: `handle_reos_propose` wrapping `propose_command` |
| `/home/kellogg/dev/Cairn/src/cairn/ui_rpc_server.py` | Register `reos/propose` |
| `/home/kellogg/dev/Cairn/apps/cairn-tauri/src/reosView.ts` | Add NL detection, proposal card UI, Approve/Edit/Reject flow |
| `/home/kellogg/dev/Cairn/apps/cairn-tauri/src/types.ts` | Add `ReosProposeResult` type |

**Dependencies on prior phases:** Phase 2 (PTY exists to receive approved commands).

**Complexity:** Medium — the Python pipeline already exists in `shell_propose.py`; the work is the frontend UX and the intercept logic.

**Risks:**
- LLM latency: `propose_command` calls Ollama synchronously on the RPC thread. This blocks the JSON-RPC server for the duration of the LLM call (same pattern as `chat/respond` in the CAIRN view). Dashboard polling is stalled during proposal generation. Accept in Phase 3; mitigate later with async RPC if it becomes a pain point.
- False positives in NL detection (treating commands as NL). The Shift+Enter escape hatch mitigates this.
- `propose_command` calls `trcore.db.get_db()` internally. Verify this initializes to `~/.talkingrock/talkingrock.db` (the shared database path), not a stale or conflicting path, when invoked from within Cairn's RPC server context.

---

### Phase 4: Dashboard Depth

**What it delivers:** The left dashboard pane gains depth: services panel (systemd), top processes, network interfaces, and container status (if Docker or Podman is present). Each panel is independently collapsible. The dashboard becomes genuinely useful for system awareness.

**Architecture decisions:**
- New RPC endpoints: `reos/services`, `reos/processes`, `reos/network`
- These call `linux_tools.list_services()`, `linux_tools.list_processes()`, `linux_tools.get_network_interfaces()` respectively
- Server-side cap: process list limited to top 20 by CPU% before sending
- Services panel polls every 30 seconds; processes every 5 seconds; network every 10 seconds
- Container panel is conditional: shown only if `docker` or `podman` is on PATH; fails open with an empty list and a status field
- Panel collapse state stored in `localStorage` keyed by panel name

**Files affected:**

| File | Action |
|------|--------|
| `/home/kellogg/dev/ReOS/src/reos/rpc_handlers/system.py` | Add `handle_reos_services`, `handle_reos_processes`, `handle_reos_network` |
| `/home/kellogg/dev/Cairn/src/cairn/ui_rpc_server.py` | Register the new `reos/*` handlers |
| `/home/kellogg/dev/Cairn/apps/cairn-tauri/src/reosView.ts` | Add services, processes, network, containers panels |
| `/home/kellogg/dev/Cairn/apps/cairn-tauri/src/types.ts` | Add result types for each new endpoint |

**Dependencies on prior phases:** Phase 1 (dashboard layout established). Can be developed in parallel with Phase 3.

**Complexity:** Medium — Python data is already in `linux_tools.py`; the work is frontend panel rendering and multiple polling timers.

**Risks:**
- `linux_tools.list_services()` calls `systemctl` as a subprocess. If systemd is not running, this will fail. Verify error handling returns an empty list with a descriptive status field rather than raising.
- Process list can be large. Cap at 20 server-side — do not send hundreds of entries to the frontend.
- Container detection: `docker ps` requires the docker daemon and the user in the `docker` group. Return empty list with `{"status": "docker_unavailable"}` on failure.

---

### Phase 5: Command History and ReOS Context

**What it delivers:** Command history navigable with up/down arrows in the terminal input. A context sidebar shows what system state the NL proposals are based on (distro, package manager, active service count).

**Architecture decisions:**
- History stored in-memory in the frontend (array of strings). Up/down arrows cycle through it.
- No persistence at this phase — history resets when the view is destroyed.
- Context sidebar: calls `reos/system_info` (from Phase 1) and formats it as a "what ReOS knows" summary. Collapsed by default.

**Files affected:**

| File | Action |
|------|--------|
| `/home/kellogg/dev/Cairn/apps/cairn-tauri/src/reosView.ts` | Add command history (in-memory), context sidebar toggle |

**Dependencies on prior phases:** Phases 1, 2, 3.

**Complexity:** Small.

**Risks:** Low. Keep Phase 5 minimal: in-memory history only, no persistence, no search. Persistent history with FTS is a future feature.

---

### Phase 6: Polish and Safety UX

**What it delivers:** The view reaches production quality. Risky-command warnings are surfaced as visual badges on proposal cards. The terminal font size is adjustable. The dashboard can be hidden to give the terminal full width. PTY process death shows a reconnect prompt.

**Architecture decisions:**
- Risky command flag: `ReosProposeResult` includes `is_risky: bool` derived from `is_safe_command()` in `shell_propose.py`. The frontend shows a red warning badge if `is_risky` is true.
- Font size preference: stored in `localStorage`, applied to xterm.js `Terminal` options at creation time.
- Dashboard toggle: a button in the view header that hides/shows the left pane; stored in `localStorage`.
- PTY death: the Rust reader thread detects EOF on the PTY master fd and emits `reos://pty-closed`. The frontend shows a "Terminal closed. Restart?" prompt with a button that calls `pty_start`.

**Files affected:**

| File | Action |
|------|--------|
| `/home/kellogg/dev/ReOS/src/reos/rpc_handlers/propose.py` | Extend `ReosProposeResult` to include `is_risky: bool` |
| `/home/kellogg/dev/Cairn/apps/cairn-tauri/src-tauri/src/pty.rs` | Emit `reos://pty-closed` on PTY EOF |
| `/home/kellogg/dev/Cairn/apps/cairn-tauri/src/reosView.ts` | Safety badges, font size control, dashboard toggle, PTY death handling |

**Dependencies on prior phases:** All prior phases.

**Complexity:** Small.

**Risks:** Low. The main risk is over-engineering: keep the audit display simple (last 20 entries, no filtering).

---

## Files Affected — Complete List

### New Files to Create

```
ReOS repo:
  src/reos/rpc_handlers/__init__.py
  src/reos/rpc_handlers/system.py
  src/reos/rpc_handlers/propose.py

Cairn Tauri:
  apps/cairn-tauri/src-tauri/src/pty.rs
```

### Files to Modify

```
Cairn repo:
  pyproject.toml                                — add reos dependency
  src/cairn/ui_rpc_server.py                    — import and register reos/* handlers
  apps/cairn-tauri/src/reosView.ts              — replace stub entirely
  apps/cairn-tauri/src/types.ts                 — add reos result types
  apps/cairn-tauri/src-tauri/src/main.rs        — add PtyState, pty_* commands
  apps/cairn-tauri/src-tauri/Cargo.toml         — add portable-pty
  apps/cairn-tauri/package.json                 — add @xterm/xterm, @xterm/addon-fit
```

### Files to Leave Untouched

```
ReOS repo:
  src/reos/linux_tools.py         — consumed as-is by rpc_handlers/system.py
  src/reos/shell_propose.py       — consumed as-is by rpc_handlers/propose.py
  src/reos/streaming_executor.py  — not used in Phases 1-3; candidate for later phases
  src/reos/agent.py               — not used in this plan; standalone shell tool

Cairn Tauri:
  apps/cairn-tauri/src-tauri/src/kernel.rs    — untouched
  apps/cairn-tauri/src/cairnView.ts           — reference only, not modified
```

---

## Risks and Mitigations — Cross-Cutting

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| `psutil.cpu_percent(interval=1)` blocks RPC thread | High | Medium | Use `interval=0`; document that first call returns 0.0 |
| PTY fd leak on Tauri crash | Medium | Low | Implement `Drop` for `PtyProcess` to kill child and close master fd |
| LLM call during `reos/propose` blocks RPC for 5-30 seconds | High | Medium | Accept in Phase 3; revisit if dashboard polling starvation is noticed in practice |
| `portable-pty` build complexity or platform incompatibility | Low | High | Evaluate at Phase 2 start; fallback is `libc::openpty` directly |
| ReOS handlers importing from `cairn.rpc_handlers._base` creates eventual circular dependency | Medium | Medium | Move the `@rpc_handler` decorator to `trcore` as the clean long-term solution |
| xterm.js conflicts with Tauri webview CSP | Medium | Medium | Audit `tauri.conf.json` CSP before Phase 2; adjust unsafe-eval/unsafe-inline if needed |
| Shell launched by PTY inherits wrong environment | Low | Low | Test with `env` as first command; `CAIRN_PYTHON` being visible is expected and fine |
| `propose_command` initializes ReOS DB to wrong path when invoked through Cairn | Medium | Low | Verify `trcore.db.get_db()` resolves to `~/.talkingrock/talkingrock.db` in both contexts |
| Tauri 2.x requires event capabilities declaration for `reos://pty-output` | Medium | Medium | Check `tauri.conf.json` capabilities before emitting custom events |

---

## Testing Strategy

### Phase 1
- Unit test `handle_reos_vitals`: mock `psutil` and assert the returned dict has expected keys (`cpu_percent`, `memory_used_mb`, `disk_used_gb`, etc.)
- Integration test: start `ui_rpc_server` in a subprocess, send `reos/vitals` JSON-RPC request, assert well-formed response
- Manual: navigate to ReOS view, verify dashboard updates every 5 seconds

### Phase 2
- Unit test `PtyProcess::new()` spawns a shell (verify child PID exists in `ps`)
- Unit test `pty_write` with `echo hello\n`, assert `reos://pty-output` event contains "hello"
- Unit test `pty_stop` terminates the child process
- Manual: type `cd /tmp; pwd`, verify working directory persists; run `ls --color=auto`, verify ANSI colors render

### Phase 3
- Unit test `handle_reos_propose` with NL input: mock LLM provider, assert returned command and explanation match expected format
- Manual: type "show running processes", verify proposal shows `ps aux` or equivalent; click Approve, verify command runs in terminal
- Manual: type `ls -la`, verify it bypasses NL detection and goes directly to PTY

### Phase 4
- Unit test `handle_reos_services`, `handle_reos_processes`, `handle_reos_network`: mock `linux_tools` function calls
- Manual: verify services panel shows known services; verify processes panel shows top consumers

### Phase 5
- Manual: run 5 commands, press up arrow, verify history cycles correctly through all 5

### Phase 6
- Manual: propose a risky command (e.g., "delete all log files in /"), verify red warning badge appears on proposal card
- Manual: exit bash in the terminal pane, verify `reos://pty-closed` reconnect prompt appears

---

## Implementation Ordering

```
Phase 1  (Dashboard Foundation)   — Start here. Validates RPC plumbing.
Phase 2  (PTY Rust Plumbing)      — Highest risk; isolate to its own PR.
Phase 3  (NL Interception)        — Depends on Phase 2.
Phase 4  (Dashboard Depth)        — Can be done in parallel with Phase 3.
Phase 5  (History and Context)    — After Phases 1-3 are stable.
Phase 6  (Polish and Safety UX)   — Final pass before declaring complete.
```

Phases 3 and 4 can be developed in parallel since they touch different halves of the view.

---

## Definition of Done

- [ ] `reosView.ts` stub is fully replaced with a working split-screen layout
- [ ] Dashboard polls and updates CPU, RAM, disk, network vitals every 5 seconds
- [ ] xterm.js terminal renders real PTY output with ANSI colors
- [ ] `cd` command persists working directory across subsequent commands
- [ ] Natural language input is intercepted and sent to `reos/propose`
- [ ] Proposal card shows command, explanation, and Approve/Edit/Reject buttons
- [ ] Approved commands execute in the PTY
- [ ] Dashboard left pane shows services, top processes, network interfaces
- [ ] Command history navigable with up/down arrows
- [ ] Risky command proposals show a visual warning badge
- [ ] PTY process death shows a reconnect prompt
- [ ] Navigating away from ReOS view stops the PTY shell process
- [ ] All new Python handlers have unit tests
- [ ] All new Rust commands have integration tests
- [ ] `cairn/pyproject.toml` lists `reos` as a dependency
- [ ] No new lint errors in either repo
- [ ] Dark theme consistent with existing Cairn UI throughout

---

## Confidence Assessment

**High confidence:** Phase 1 (dashboard RPC) — the pattern is established; `linux_tools.py` has exactly the functions needed; the RPC dispatch table is well-understood.

**High confidence:** Phase 3 (NL interception) — `shell_propose.py` already has the full pipeline; the RPC wrapper is thin; the frontend intercept is a straightforward input handler.

**Medium confidence:** Phase 2 (PTY Rust plumbing) — Tauri events are the right channel, but `portable-pty` integration and the reader thread implementation require care around fd lifecycle, signal handling, and event emission from background threads. Budget extra time here. This is the highest-risk phase.

**Medium confidence:** Phase 4 (dashboard depth) — Python side is straightforward; uncertainty is in edge cases (systemd not running, docker not installed, large process lists).

---

## Unknowns Requiring Validation Before Phase 2

1. **`portable-pty` with Tauri 2.x**: Run a minimal compile test before committing to this crate. Verify it links cleanly against the Tauri 2 build environment.

2. **Tauri event capability declarations**: Check whether Tauri 2.x requires `reos://pty-output` and `reos://pty-closed` to be declared in `tauri.conf.json` before they can be emitted or received.

3. **xterm.js CSP**: Inspect the current `tauri.conf.json` Content Security Policy. xterm.js uses dynamic style injection which may require `style-src 'unsafe-inline'`. Determine whether this is already permitted or requires a policy amendment.

4. **`@rpc_handler` import from ReOS**: Decide at Phase 1 whether to: (a) import `@rpc_handler` from `cairn.rpc_handlers._base` directly, (b) duplicate the decorator in ReOS, or (c) move it to `trcore`. Document the decision as an ADR if option (c) is chosen.

5. **`trcore.db.get_db()` path resolution**: Before Phase 3, verify that `propose_command()` resolves the database to `~/.talkingrock/talkingrock.db` when invoked from within the Cairn RPC server context. If it uses a different path, the LLM provider initialization may fail silently.
