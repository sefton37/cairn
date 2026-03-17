# Plan: ReOS View — Phases 5 & 6 Implementation

## Context

`/home/kellogg/dev/Cairn/apps/cairn-tauri/src/reosView.ts` (1048 lines) is a
split-screen view: left dashboard (system vitals), right PTY terminal (xterm.js
backed by Rust portable-pty). The file exports a single factory function
`createReosView()` that owns all state as closures.

Six items remain unimplemented. This plan provides precise, ordered instructions
for each.

---

## Item 1 — Command History (up/down arrows)

### Decision: Do Nothing

The shell process running inside the PTY already has full readline/history
support. When the user presses Up/Down, the keystroke travels through
`term.onData()` → `invoke('pty_write', ...)` → Rust PTY → bash/zsh, and bash
processes it through its own `HISTFILE`-backed history. This is indistinguishable
from a normal terminal.

A second history layer in the frontend would:
- Duplicate history from a different starting point (frontend only sees commands
  typed while this view is open)
- Require intercepting Up/Down before they reach the PTY, breaking readline's
  search/navigation (Ctrl-R, etc.)
- Provide no user-visible benefit

**Recommendation:** Close this item as "not needed — shell readline already
handles it." No code changes.

---

## Item 2 — Context Sidebar

### What to show

The NL proposal pipeline uses `ShellContextGatherer` internally (on the Python
side) but the frontend has no visibility into it. The sidebar should display the
three facts that ground every proposal:

1. **Distro** — already available from `vitals.distro` (populated every 5 s)
2. **Package manager** — NOT in the current `reos/vitals` response; must be added
   OR read from a one-time `reos/context` call
3. **Active service count** — NOT in `reos/vitals`; requires a separate call or
   a vitals extension

The simplest approach: read what is already available from `vitals` and add one
lightweight field. Do not add a new RPC endpoint.

### Backend change — `propose.py`

None required. The vitals endpoint is the right source.

### Backend change — `system.py` (`handle_reos_vitals`)

Add `package_manager` and `active_service_count` to the vitals dict. Both can
be derived cheaply:

- `package_manager`: call `shutil.which("apt")` / `"dnf"` / `"pacman"` —
  identical logic already exists in `ShellContextGatherer._detect_package_manager()`
  and `SteadyStateCollector._detect_package_manager()`. Extract it to a shared
  helper or inline it in `handle_reos_vitals`.
- `active_service_count`: run `systemctl list-units --type=service --state=active
  --no-legend --no-pager 2>/dev/null | wc -l` with a 2-second timeout. If
  systemctl is absent or times out, return `None`.

Add both fields to the fallback dict in the `except` block (both `None`).

File: `/home/kellogg/dev/ReOS/src/reos/rpc_handlers/system.py`

Specific insertion point: after the containers block (line 101), before
`return result`:

```python
# Package manager (for context sidebar)
try:
    import shutil as _shutil
    for _pm in ("apt", "dnf", "pacman", "zypper"):
        if _shutil.which(_pm):
            result["package_manager"] = _pm
            break
    else:
        result["package_manager"] = "unknown"
except Exception:
    result["package_manager"] = None

# Active service count (for context sidebar)
try:
    import subprocess as _sp
    _r = _sp.run(
        ["systemctl", "list-units", "--type=service", "--state=active",
         "--no-legend", "--no-pager"],
        capture_output=True, text=True, timeout=2,
    )
    result["active_service_count"] = len([l for l in _r.stdout.splitlines() if l.strip()])
except Exception:
    result["active_service_count"] = None
```

### TypeScript change — `reosView.ts`

**1. Extend `ReosVitals` interface** (after line 67, before closing brace):

```typescript
package_manager?: string | null;
active_service_count?: number | null;
```

**2. Add module-level state** (after line 209 `reosThinkingWritten`):

```typescript
let lastVitals: ReosVitals | null = null;
```

Update `updateVitals()` to save: add `lastVitals = v;` as the first line of
the function.

**3. Build the sidebar DOM** — insert after `dashboard` is declared (after
line 258) and before `dashHeader` is appended:

Create a collapsed section at the bottom of `dashBody`. Add after the
`containerPanel` is appended to `dashBody` (after line 327):

```typescript
// ── Context Sidebar (NL Proposal Grounding) ──
const { panel: ctxPanel, body: ctxBody } = makePanel('NL Context', '🔍');
ctxPanel.style.display = 'none'; // Hidden until first vitals arrive

const ctxToggle = el('button');
ctxToggle.textContent = 'NL Context ▸';
ctxToggle.style.cssText = `
  margin: 8px 16px;
  padding: 4px 10px;
  font-size: 11px;
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.1);
  border-radius: 4px;
  color: rgba(255,255,255,0.5);
  cursor: pointer;
  flex-shrink: 0;
  text-align: left;
`;
let ctxExpanded = false;
ctxToggle.addEventListener('click', () => {
  ctxExpanded = !ctxExpanded;
  ctxPanel.style.display = ctxExpanded ? '' : 'none';
  ctxToggle.textContent = ctxExpanded ? 'NL Context ▾' : 'NL Context ▸';
  if (ctxExpanded) updateCtxPanel();
});

function updateCtxPanel(): void {
  if (!lastVitals) return;
  ctxBody.innerHTML = '';
  ctxBody.appendChild(makeStatRow('Distro', lastVitals.distro || 'unknown'));
  ctxBody.appendChild(makeStatRow(
    'Package Mgr', lastVitals.package_manager || 'unknown'));
  ctxBody.appendChild(makeStatRow(
    'Active Services',
    lastVitals.active_service_count != null
      ? String(lastVitals.active_service_count)
      : '—'));
}

dashboard.appendChild(ctxToggle);  // goes after dashBody, inside dashboard
```

Wait — placement matters. `ctxToggle` and `ctxPanel` need to be appended to
`dashboard` AFTER `dashBody`. Check `dashboard.appendChild(dashHeader)` (line
329) and `dashboard.appendChild(dashBody)` (line 330) — append them after both.

Replace line 330 block with:
```typescript
dashboard.appendChild(dashHeader);
dashboard.appendChild(dashBody);
dashboard.appendChild(ctxToggle);
dashboard.appendChild(ctxPanel);
```

Also call `updateCtxPanel()` at the end of `updateVitals()` when `ctxExpanded`
is true: add at line 540 (before `dashStatus.textContent = ...` line):

```typescript
if (ctxExpanded) updateCtxPanel();
```

**Implementation scope:** ~40 lines TypeScript, ~20 lines Python.

---

## Item 3 — Risky-Command Badges

### Backend change — `propose.py`

The return dict of `handle_reos_propose` must include `is_risky: bool` and
`risk_reason: str | None`.

`extract_conversational_response()` in `shell_propose.py` already calls
`is_safe_command()` but discards the result beyond blocking. Instead of
propagating `is_risky` through the entire call stack, the simplest approach is
to re-run `is_safe_command()` in `handle_reos_propose` on the returned command
(which is available at that point):

In `propose.py`, after the `propose_command_with_meta()` call succeeds (line 43),
before `return {...}` (line 97):

```python
# Risky-command check
is_risky = False
risk_reason: str | None = None
if command:
    from reos.shell_propose import is_safe_command
    _safe, _reason = is_safe_command(command)
    if not _safe:
        # Command was already blocked inside extract_conversational_response,
        # so this branch shouldn't normally fire. But guard it anyway.
        is_risky = True
        risk_reason = _reason
    else:
        # Soft-risky patterns: commands that are safe but warrant a warning
        _SOFT_RISKY = [
            (r"\bsudo\b", "Requires elevated privileges"),
            (r"\brm\b.*-[rRf]", "Recursive or forced delete"),
            (r"\bdd\b", "Low-level disk operation"),
            (r"\bchmod\b.*777", "Makes files world-writable"),
            (r"\bcurl\b.*\|\s*(?:bash|sh)\b", "Pipes remote content to shell"),
            (r"\bwget\b.*\|\s*(?:bash|sh)\b", "Pipes remote content to shell"),
            (r"\bsystemctl\b.*(stop|disable|mask)", "Modifies service state"),
            (r"\bapt\b.*(?:remove|purge)", "Removes packages"),
        ]
        import re as _re
        for _pat, _msg in _SOFT_RISKY:
            if _re.search(_pat, command, _re.IGNORECASE):
                is_risky = True
                risk_reason = _msg
                break
```

Add `is_risky` and `risk_reason` to both the success return dict and the failure
return dict (set both `False` / `None` on failure).

Update the success `return` block (line 97):

```python
return {
    "message": message,
    "command": command,
    "success": True,
    "model_name": model_name,
    "latency_ms": latency_ms,
    "is_risky": is_risky,
    "risk_reason": risk_reason,
}
```

Update the failure return (line 69):

```python
return {"message": str(exc), "command": None, "success": False,
        "model_name": None, "latency_ms": None,
        "is_risky": False, "risk_reason": None}
```

### TypeScript change — `reosView.ts`

**1. Extend the `result` type** in `requestResponse()` (the `raw as {...}` cast,
line 814):

```typescript
const result = raw as {
  message?: string;
  command?: string | null;
  success?: boolean;
  model_name?: string;
  latency_ms?: number;
  is_risky?: boolean;
  risk_reason?: string | null;
};
```

**2. Pass `is_risky` / `risk_reason` to `writeReosResponse()`.**

Change `writeReosResponse` signature (line 723):

```typescript
function writeReosResponse(
  message: string,
  command: string | null,
  isRisky: boolean = false,
  riskReason: string | null = null,
): void {
```

Change the call site in `requestResponse()` (line 840):

```typescript
writeReosResponse(
  result.message,
  result.command ?? null,
  result.is_risky ?? false,
  result.risk_reason ?? null,
);
```

**3. Render the warning in `writeReosResponse()`.**

In the `if (command)` branch (after line 735, before writing the "Suggested:"
line):

```typescript
if (isRisky && riskReason) {
  // Red warning badge — ANSI bold red
  term.write(`       \x1b[1;31m⚠ ${riskReason}\x1b[0m\r\n`);
}
```

Insert this block before `term.write('\r\n       \x1b[1mSuggested:\x1b[0m ...')`.

**Implementation scope:** ~30 lines TypeScript, ~40 lines Python.

---

## Item 4 — Font Size Control

### State

Add two variables after line 209:

```typescript
const FONT_SIZE_KEY = 'reos-term-font-size';
const FONT_SIZE_MIN = 10;
const FONT_SIZE_MAX = 24;
let currentFontSize: number = (() => {
  const stored = localStorage.getItem(FONT_SIZE_KEY);
  return stored ? Math.max(FONT_SIZE_MIN, Math.min(FONT_SIZE_MAX, parseInt(stored, 10))) : 14;
})();
```

### DOM — add controls to `termHeader`

After `termHeader.appendChild(termStatus)` (line 372), before
`terminalPane.appendChild(termHeader)` (line 384):

```typescript
const fontControls = el('div');
fontControls.style.cssText = `
  display: flex; align-items: center; gap: 4px; margin-left: auto;
`;

function makeFontBtn(label: string, delta: number): HTMLElement {
  const btn = el('button');
  btn.textContent = label;
  btn.style.cssText = `
    width: 22px; height: 22px;
    background: rgba(255,255,255,0.06);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 4px;
    color: rgba(255,255,255,0.6);
    font-size: 14px; line-height: 1;
    cursor: pointer; padding: 0;
    display: flex; align-items: center; justify-content: center;
  `;
  btn.addEventListener('click', () => {
    currentFontSize = Math.max(FONT_SIZE_MIN, Math.min(FONT_SIZE_MAX, currentFontSize + delta));
    localStorage.setItem(FONT_SIZE_KEY, String(currentFontSize));
    if (term) {
      term.options.fontSize = currentFontSize;
      fitAddon?.fit();
    }
  });
  return btn;
}

fontControls.appendChild(makeFontBtn('−', -1));
fontControls.appendChild(makeFontBtn('+', 1));
termHeader.appendChild(fontControls);
```

### Terminal creation

In `startTerminal()`, change the hardcoded `fontSize: 14` (line 900) to:

```typescript
fontSize: currentFontSize,
```

### Notes on `term.options.fontSize`

xterm.js `Terminal.options` is a live setter in xterm.js v5+. Setting
`term.options.fontSize = N` triggers an immediate re-render without needing to
dispose and recreate the terminal. `fitAddon.fit()` must be called after to
recalculate rows/cols for the new cell size.

**Implementation scope:** ~35 lines TypeScript, 0 Python.

---

## Item 5 — Dashboard Hide/Show Toggle

### State

Add after the font size constants:

```typescript
const DASH_HIDDEN_KEY = 'reos-dash-hidden';
let dashHidden: boolean = localStorage.getItem(DASH_HIDDEN_KEY) === '1';
```

### DOM changes

**1. Add a toggle button to `termHeader`.**

After `fontControls` is appended to `termHeader`, append one more button:

```typescript
const dashToggleBtn = el('button');
dashToggleBtn.style.cssText = `
  width: 22px; height: 22px;
  background: rgba(255,255,255,0.06);
  border: 1px solid rgba(255,255,255,0.1);
  border-radius: 4px;
  color: rgba(255,255,255,0.6);
  font-size: 12px; line-height: 1;
  cursor: pointer; padding: 0;
  display: flex; align-items: center; justify-content: center;
  margin-left: 4px;
`;

function applyDashState(): void {
  if (dashHidden) {
    dashboard.style.display = 'none';
    dashToggleBtn.textContent = '◧';
    dashToggleBtn.title = 'Show dashboard';
  } else {
    dashboard.style.display = '';
    dashToggleBtn.textContent = '▣';
    dashToggleBtn.title = 'Hide dashboard';
  }
  // Let xterm.js refit after layout change
  requestAnimationFrame(() => {
    fitAddon?.fit();
  });
}

dashToggleBtn.addEventListener('click', () => {
  dashHidden = !dashHidden;
  localStorage.setItem(DASH_HIDDEN_KEY, dashHidden ? '1' : '0');
  applyDashState();
});

termHeader.appendChild(dashToggleBtn);
```

**2. Apply initial state** — call `applyDashState()` once immediately after
`container.appendChild(terminalPane)` (line 388):

```typescript
applyDashState();
```

### Why `requestAnimationFrame` for fit

`dashboard.style.display = 'none'` changes layout synchronously but the browser
may not have committed the new geometry before `fitAddon.fit()` reads
`clientWidth`. A single `requestAnimationFrame` defers fit until after paint.

**Implementation scope:** ~35 lines TypeScript, 0 Python.

---

## Item 6 — PTY Reconnect Button

### DOM

The reconnect button must be a real DOM element (not ANSI in the terminal)
because it needs to be clickable after the terminal session is gone. Mount it
inside `terminalPane`, overlaid at the bottom — or appended to `termHeader`.

The simplest approach is to append a hidden button to `termHeader` that becomes
visible when the PTY closes:

After `termHeader.appendChild(dashToggleBtn)` (still in the header block):

```typescript
const reconnectBtn = el('button');
reconnectBtn.textContent = '↺ Restart';
reconnectBtn.style.cssText = `
  display: none;
  padding: 3px 10px;
  background: rgba(239,68,68,0.15);
  border: 1px solid rgba(239,68,68,0.4);
  border-radius: 4px;
  color: rgba(239,68,68,0.9);
  font-size: 11px;
  cursor: pointer;
  margin-left: 8px;
`;
reconnectBtn.addEventListener('click', () => {
  reconnectBtn.style.display = 'none';
  termStatus.textContent = 'Connecting\u2026';
  termStatus.style.color = 'rgba(255,255,255,0.4)';
  startTerminal();
});
termHeader.appendChild(reconnectBtn);
```

### Show button on PTY close

Find the `reos://pty-closed` listener (line 937):

```typescript
pendingListenClosed = listen<{ reason: string }>('reos://pty-closed', (event) => {
  term?.write(`\r\n\x1b[31m[PTY closed: ${event.payload.reason}]\x1b[0m\r\n`);
  termStatus.textContent = 'Closed';
  termStatus.style.color = 'rgba(239,68,68,0.8)';
});
```

Add one line showing the button:

```typescript
pendingListenClosed = listen<{ reason: string }>('reos://pty-closed', (event) => {
  term?.write(`\r\n\x1b[31m[PTY closed: ${event.payload.reason}]\x1b[0m\r\n`);
  termStatus.textContent = 'Closed';
  termStatus.style.color = 'rgba(239,68,68,0.8)';
  reconnectBtn.style.display = '';          // ← add this line
});
```

### Hide button when a new session starts

`startTerminal()` has an early-return guard (`if (terminalActive) return;`).
The reconnect button's click handler calls `startTerminal()` after resetting
`terminalActive = false` (via `teardownTerminalResources()` which fires on close),
so the re-entry path works correctly already.

But `terminalActive` is NOT reset by the closed event — it is still `true` when
`pty-closed` fires (the Rust PTY exited but the JS side hasn't torn down). That
means clicking "Restart" after a close will hit the `if (terminalActive) return;`
guard and do nothing.

Fix: in the `reos://pty-closed` listener, also call `teardownTerminalResources()`
so the state is clean for a restart. Update the listener:

```typescript
pendingListenClosed = listen<{ reason: string }>('reos://pty-closed', (event) => {
  term?.write(`\r\n\x1b[31m[PTY closed: ${event.payload.reason}]\x1b[0m\r\n`);
  termStatus.textContent = 'Closed';
  termStatus.style.color = 'rgba(239,68,68,0.8)';
  reconnectBtn.style.display = '';
  // Teardown JS resources so startTerminal() can re-run cleanly.
  // Use setTimeout to let the write above render before disposing xterm.
  setTimeout(() => teardownTerminalResources(), 100);
});
```

`teardownTerminalResources()` already resets `terminalActive = false`,
disposes xterm, and clears listeners — everything needed for a clean restart.
The 100 ms delay lets the "PTY closed" error message render before xterm is
disposed.

**Implementation scope:** ~20 lines TypeScript, 0 Python.

---

## Implementation Order

Dependencies between items:

- Items 4, 5, and 6 are fully independent of each other and of items 2 and 3.
- Item 3 (risky badges) requires both a Python backend change and a TypeScript
  front-end change, but neither depends on items 2, 4, 5, or 6.
- Item 2 (context sidebar) requires the Python vitals extension before the
  frontend can display the data, but the frontend panel can be built first
  with placeholder values.

**Recommended order:**

1. **Item 4** (font size) — pure TypeScript, self-contained, 5 minutes.
2. **Item 6** (reconnect button) — pure TypeScript, self-contained, 5 minutes.
3. **Item 5** (dashboard toggle) — pure TypeScript, self-contained, 10 minutes.
4. **Item 3 backend** (risky badges in `propose.py`) — Python only, 10 minutes.
5. **Item 3 frontend** (`writeReosResponse` changes) — TypeScript, 5 minutes.
6. **Item 2 backend** (vitals extension in `system.py`) — Python only, 10 minutes.
7. **Item 2 frontend** (context sidebar panel) — TypeScript, 15 minutes.

---

## Files Affected

| File | Change |
|------|--------|
| `/home/kellogg/dev/Cairn/apps/cairn-tauri/src/reosView.ts` | Items 2, 3, 4, 5, 6 |
| `/home/kellogg/dev/ReOS/src/reos/rpc_handlers/propose.py` | Item 3 |
| `/home/kellogg/dev/ReOS/src/reos/rpc_handlers/system.py` | Item 2 |

---

## Risks & Mitigations

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| `term.options.fontSize = N` not available in the xterm.js version in use | Low | xterm.js v5+ supports live option mutation. Verify version in `package.json`; fallback is dispose + recreate terminal (acceptable UX cost). |
| `teardownTerminalResources()` called from pty-closed listener while still inside xterm write operation | Low | The `setTimeout(..., 100)` defers teardown past the current event loop tick. |
| `systemctl` not available on the host (e.g., container without systemd) | Medium | The try/except in `system.py` sets `active_service_count = None`; frontend renders `—`. |
| `shutil.which` for package manager detection in vitals runs on every 5-second poll | Low | Three `shutil.which` calls per poll is negligible. Cache in a module-level variable if it becomes measurable. |
| Dashboard toggle leaving terminal with wrong size (fitAddon sees pre-toggle width) | Low | `requestAnimationFrame` deferred `fitAddon.fit()` in `applyDashState()` resolves this. |
| Soft-risky regex patterns in `propose.py` generating false positives (e.g., `rm` flagging `rm -i`) | Medium | Accept some false positives — a red badge is not a block, just a warning. Refine patterns if user complaints emerge. |

---

## Testing Strategy

No automated tests are recommended for these items. They are all UI/UX changes
(DOM controls, ANSI rendering, localStorage persistence). Manual verification
checklist:

- **Item 2:** Open ReOS view, expand "NL Context" toggle. Confirm distro, package
  manager, and service count match what `uname -a`, `which apt`, and
  `systemctl list-units` report on the host.
- **Item 3:** Trigger a NL proposal that produces a `sudo` command. Confirm the
  red `⚠ Requires elevated privileges` line appears before "Suggested:". Trigger
  a safe command. Confirm no warning.
- **Item 4:** Click `+` three times. Confirm font grows. Reload view (navigate
  away and back). Confirm font size persists.
- **Item 5:** Click dashboard toggle. Confirm terminal expands to full width.
  Reload. Confirm hidden state persists.
- **Item 6:** Kill the PTY (e.g., `exit` in the terminal). Confirm "↺ Restart"
  button appears in the header. Click it. Confirm new shell starts and button
  disappears.

---

## Definition of Done

- [ ] Item 1: Closed as "not needed" with explanation in code comments (optional)
- [ ] Item 2: `NL Context` collapsible section shows distro, package manager,
      service count sourced from `reos/vitals`
- [ ] Item 3: `propose.py` returns `is_risky` + `risk_reason`; `⚠` line renders
      in terminal before risky commands
- [ ] Item 4: Font +/- buttons in terminal header; size persists across view
      navigation
- [ ] Item 5: Dashboard hide/show toggle; terminal expands; state persists
- [ ] Item 6: "↺ Restart" DOM button appears on PTY close; clicking it calls
      `startTerminal()` and succeeds
