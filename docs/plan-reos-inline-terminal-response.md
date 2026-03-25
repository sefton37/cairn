# Plan: ReOS Inline Terminal Response System

## Context

The current ReOS natural language pipeline works end-to-end but surfaces responses through a floating overlay card (`proposalCard`) positioned absolutely over the terminal. The overlay contains a command block, explanation text, and three buttons (Run / Edit / Dismiss).

This design violates the operating philosophy: ReOS is a participant in the conversation, not a modal popup. The terminal is the context. ReOS should speak inside it, not over it.

### What exists today

**Frontend** (`apps/cairn-tauri/src/reosView.ts`):
- `scanForCommandNotFound()` — regex detection on PTY output chunks. Working correctly, unchanged.
- `extractUserInput()` — recovers the full typed line from recent echoed output. Working, unchanged.
- `requestProposal()` — calls `reos/propose` RPC, stores result, invokes `showProposal()`.
- Proposal card overlay: `proposalCard`, `proposalSpinner`, `proposalCommand`, `proposalExplanation`, `proposalButtons` (btnApprove / btnEdit / btnDismiss). All removed in this plan.
- Telemetry: `recordEvent()`, fire-and-forget, covers the full trace pipeline.

**Backend** (`src/reos/shell_propose.py`):
- `propose_command_with_meta()` — two-attempt LLM pipeline with context gathering, command extraction, and safety validation. Returns `(command, explanation, model_name, latency_ms, attempt_count)`.
- `STANDARD_PROMPT` — terse two-line output format. Replaced in this plan.
- `CONSTRAINED_PROMPT` — fallback single-line extraction. Replaced in this plan.

**RPC handler** (`src/reos/rpc_handlers/propose.py`):
- `handle_reos_propose()` — wraps `propose_command_with_meta()`, returns `{command, explanation, success, model_name, latency_ms}`. Extended but not renamed in this plan.

**RPC dispatch** (`src/cairn/ui_rpc_server.py`):
- `reos/propose` registered as a `_STRING_PARAM_HANDLERS` entry with a single `natural_language` param.

**Telemetry** (`src/reos/telemetry.py`):
- Append-only SQLite DB at `~/.talkingrock/reos_telemetry.db`. Schema unchanged.
- Event pipeline: `pty_line` -> `error_detected` -> `proposal_requested` -> `proposal_generated` -> `user_action`.

---

## Desired Outcome

When the shell cannot execute user input:

1. Detection fires (unchanged).
2. ReOS calls the backend (unchanged RPC path).
3. LLM generates a conversational, paragraph-style response with an optional command.
4. ReOS writes the response directly into the xterm.js terminal using ANSI escape codes.
5. If a command was proposed, ReOS appends a `Run? [Y/n]` prompt and enters keystroke-intercept mode.
6. Y or Enter writes the command to the PTY, exits intercept mode.
7. n or Escape exits intercept mode, shell resumes normally.
8. If no command was proposed (purely conversational response), ReOS writes the message and immediately returns control to the shell.

---

## Key Design Questions Resolved

### Q1: Writing styled text into xterm.js without going through the PTY

`term.write(data)` writes directly to xterm.js's renderer and does not touch the PTY. It accepts raw bytes or strings. ANSI escape sequences in the string are interpreted by xterm.js as styling, exactly as if they came from the PTY output stream. The PTY event listener in `startTerminal()` already calls `term.write(event.payload.data)` — the same mechanism is used for PTY-closed error messages: `term?.write('\r\n\x1b[31m[PTY closed: ...]\x1b[0m\r\n')`.

This is the precedent. Direct `term.write()` calls for ReOS responses follow the same established pattern.

**ANSI escape codes for this plan** (verified against xterm.js theme palette):
- `\x1b[38;2;88;166;255m` — RGB blue for `[ReOS]` prefix (matches the `cursor: '#58a6ff'` theme color)
- `\x1b[0m` — reset all attributes
- `\x1b[2m` — dim (for the explanation body text)
- `\x1b[1m` — bold (for the command line)
- `\x1b[38;2;62;185;80m` — RGB green for `Run?` prompt (matches `green: '#3fb950'` in theme)
- All lines must use `\r\n` line endings (CRLF) because xterm.js is in raw terminal mode.

**Spinner**: Write a `[ReOS] thinking...` line, then overwrite it using cursor-up + erase-line escapes (`\x1b[1A\x1b[2K`) once the response arrives.

### Q2: Temporarily intercepting keystrokes for Y/n

xterm.js fires `term.onData(handler)` for every keystroke. The current handler unconditionally sends everything to the PTY via `pty_write`. To intercept:

1. Add a module-level flag `reosInterceptMode: boolean` and a `reosInterceptCommand: string` in the closure.
2. Wrap the existing `term.onData` handler with a conditional: if `reosInterceptMode`, route the keystroke to the intercept handler instead of the PTY.
3. The intercept handler:
   - `y` / `Y` / Enter (`\r`) -> write the command + `\n` to PTY, write `y\r\n` to `term.write()` so the user sees their input echoed, exit intercept mode.
   - `n` / `N` / Escape (`\x1b`) -> write `n\r\n` to `term.write()` (echo dismissal), exit intercept mode.
   - All other keystrokes are swallowed (Y/n prompt is single-character, no buffer needed).
4. Exit intercept mode clears both flags and resets `reosInterceptCommand`.

This is deliberately minimal. No separate event listener is added; no `removeEventListener` gymnastics required. The `reosInterceptMode` guard in the existing `onData` handler is the entire mechanism.

**Terminal state preservation**: xterm.js continues receiving PTY output normally during intercept mode (the output listener is untouched). If the PTY produces output during the brief intercept window (unlikely but possible), it scrolls in as normal. This is acceptable — the terminal is not blocked.

### Q3: The new LLM prompt

The current `STANDARD_PROMPT` instructs the LLM to produce exactly two lines. That format is correct for machine parsing but wrong for the conversational experience. The new prompt must produce:
- A paragraph explaining what the user likely wants and what the recommended approach is.
- A clearly delimited command line (when applicable).
- Acknowledgment that no command applies (when input is truly conversational).

The response must remain structured so the frontend can split message from command. The format uses a sentinel line rather than trying to parse prose.

The constraint is that `extract_command()` — a sophisticated sanitizer — already handles LLM slop (markdown fences, backticks, prefixes). The new approach keeps the sentinel-based parsing but in a conversational wrapper.

### Q4: New RPC endpoint vs. modify existing `reos/propose`

**Decision: modify `reos/propose` in-place, not a new endpoint.**

Rationale:
- The dispatch registration in `ui_rpc_server.py` uses a `_STRING_PARAM_HANDLERS` pattern with a single `natural_language` param. This fits the new behavior identically.
- The return contract expands from `{command, explanation, success, model_name, latency_ms}` to `{message, command, success, model_name, latency_ms}`. The `explanation` field is renamed `message` to reflect the conversational nature; `command` becomes nullable.
- No telemetry schema changes are required — `proposal_generated` already stores whatever fields are passed.
- A new `reos/respond` endpoint would require registering a new handler, updating the dispatch table, and duplicating all the fallback/retry/telemetry logic. There is no benefit.

The frontend field change: `result.explanation` becomes `result.message`. The frontend reads both fields only in `requestProposal()` and `recordEvent('proposal_generated', ...)`.

---

## Approach (Recommended): Inline Write with Intercept Mode

### Summary
Modify the LLM prompt to be conversational. Expand the response structure to include a `message` field. Replace the proposal card DOM elements with direct `term.write()` calls using ANSI escape codes. Intercept Y/n via a mode flag in the existing `onData` handler.

### Why this wins
- Minimal mechanical change to the detection/RPC/telemetry pipeline.
- No new DOM elements required.
- Follows the established `term.write()` precedent already in the codebase (PTY-closed message uses ANSI escapes directly).
- Intercept mode is a 10-line addition to the existing `onData` handler, not a new event listener.
- The `edit` button disappears naturally — inline mode has no edit affordance, which is the correct behavior (the user can always retype or press Up arrow in the shell after dismissal).

---

## Alternatives Considered

### Alternative A: Inject text into PTY stream (write to PTY, not term)

Write the ReOS response by sending it to the PTY process. The PTY echoes it back and the shell renders it.

**Rejected**: The shell would interpret ReOS text as input. Even with shell escaping it would break prompt state, disrupt readline, and potentially trigger shell builtins. Writing directly to `term.write()` is the correct path for out-of-band messages.

### Alternative B: New xterm.js overlay using addons (e.g., SearchAddon canvas)

Render the proposal in a separate xterm.js canvas layer or WebGL overlay that sits on top of the terminal visually but is not actually injected into terminal state.

**Rejected**: This replicates the modal overlay problem — same UX, different rendering path. It also requires xterm.js addon infrastructure not currently in use. The inline write approach is simpler and philosophically correct.

### Alternative C: Keep overlay, style it to look more terminal-native

Restyle the existing card to look like terminal output (monospace, dark background, minimal chrome).

**Rejected**: This is lipstick on the fundamental problem. The overlay is still a DOM element floating above the terminal, not a participant in it. The overlay also covers terminal content that the user may want to read while deciding.

---

## Implementation Steps

### Step 1 — Backend: New conversational prompt in `shell_propose.py`

Replace `STANDARD_PROMPT` and `CONSTRAINED_PROMPT` with the following. The extraction logic in `extract_command()` requires no changes — it already handles messy LLM output. The new prompt uses a `COMMAND:` sentinel that the extractor can strip.

**New `CONVERSATIONAL_PROMPT`** (replaces `STANDARD_PROMPT`):

```
You are ReOS, a natural language assistant embedded in a Linux terminal.
The user typed something the shell did not recognize. Help them.

FORMAT YOUR RESPONSE IN TWO PARTS:

First, write 1-3 sentences explaining what the user likely wants and what
tool or approach to use. Be direct. No markdown. Under 60 words.

Second, if a specific runnable shell command applies, write exactly:
COMMAND: <the full shell command here>

If no specific command applies (greeting, question with no shell equivalent,
etc.), omit the COMMAND line entirely.

RULES:
- No markdown formatting (no backticks, no asterisks, no hash symbols)
- COMMAND line contains ONLY the bare command, nothing else
- Use sudo when root privileges are required
- Never suggest dangerous commands (rm -rf /, dd to block devices, etc.)

EXAMPLES:

Input: show running processes
It looks like you want to see what is running. Use ps for a snapshot or htop for a live interactive view — htop is more readable for humans.
COMMAND: ps aux --sort=-%cpu | head -20

Input: install vim
You want to install the Vim text editor from the Ubuntu package repositories.
COMMAND: sudo apt install vim

Input: hello
Hello. I am ReOS. Type Linux commands here, or describe what you want to do in plain English and I will suggest the right command.

Input: what is my ip address
To see your machine's network addresses, ip addr lists all interfaces with their IPs. Use curl ifconfig.me if you want your public internet IP.
COMMAND: ip addr show

Input: list running services
This shows all systemd services that are currently active on your system.
COMMAND: systemctl list-units --type=service --state=running
```

**New `CONSTRAINED_FALLBACK_PROMPT`** (replaces `CONSTRAINED_PROMPT` — used only when the conversational prompt fails to produce a parseable command):

```
Output exactly one line: COMMAND: <shell command>
If no command applies, output: COMMAND: NONE

Task: {intent}
```

**Parsing the new format**: The existing `extract_command()` function already handles the `COMMAND:` prefix via its prefix-stripping loop. The `message` field is extracted by taking everything before the first `COMMAND:` sentinel line, stripping any `MESSAGE:` prefix if present. This parsing happens in a new `extract_conversational_response()` function in `shell_propose.py`.

### Step 2 — Backend: Update `shell_propose.py` logic and return type

In `propose_command_with_meta()`:

1. Replace `STANDARD_PROMPT` usage with `CONVERSATIONAL_PROMPT`.
2. Replace `CONSTRAINED_PROMPT` usage with `CONSTRAINED_FALLBACK_PROMPT`.
3. Add `extract_conversational_response(raw: str) -> tuple[str, str | None]` that splits the LLM response on the `COMMAND:` sentinel, returning `(message, command_or_None)`. Cap message at 500 characters to prevent runaway LLM output bloating the terminal.
4. Update the return type: `propose_command_with_meta()` now returns `(message, command, model_name, latency_ms, attempt_count)` where `command` is `""` when not applicable.
5. Safety check: `is_safe_command()` only runs when `command` is non-empty. Unchanged.
6. The `looks_like_command()` check remains as-is — it guards the constrained fallback path only.

### Step 3 — Backend: Update `rpc_handlers/propose.py`

1. Unpack the new `propose_command_with_meta()` return (now includes `message`).
2. Change response dict: rename `explanation` -> `message`. Add `command` as nullable (`str | None`). Keep `success`, `model_name`, `latency_ms`.
3. Update `proposal_generated` telemetry payload: add `message` field, keep `command` (empty string when null), keep `failure_reason` logic.
4. New response contract:
   ```python
   {
       "message": str,          # Conversational response text (always present)
       "command": str | None,   # Shell command, or None if not applicable
       "success": bool,         # True when message was generated (even without command)
       "model_name": str | None,
       "latency_ms": int | None,
   }
   ```
   Note: `success` is now `True` when the LLM generates a message, even if no command is proposed. It is `False` only on LLM failure.

### Step 4 — Frontend: Remove proposal card DOM elements from `reosView.ts`

Remove from the DOM construction block (lines 379-502):
- `proposalCard` and all child elements (`proposalHeader`, `proposalCommand`, `proposalExplanation`, `proposalButtons`, `btnApprove`, `btnEdit`, `btnDismiss`)
- `proposalSpinner`
- The two `terminalPane.appendChild()` calls for these elements

Remove all button event listeners (`btnApprove`, `btnEdit`, `btnDismiss` click handlers, lines 887-937).

Remove the `showProposal()` function (lines 869-876) and `hideProposal()` function (lines 879-884).

Remove the `currentProposedCommand` state variable (line 728).

### Step 5 — Frontend: Add inline response state variables

In the state variable block (near lines 197-205), add:

```typescript
let reosInterceptMode = false;
let reosInterceptCommand = '';
let reosResponseShownAt: number | null = null;
```

`proposalShownAt` is renamed to `reosResponseShownAt` (same semantic, new name to match the new flow).

### Step 6 — Frontend: Update `requestProposal()` into `requestResponse()`

Rename `requestProposal()` to `requestResponse()`. Single callsite in `scanForCommandNotFound()`.

Inside `requestResponse()`:

1. Replace `proposalSpinner.style.display = ''` with `writeReosThinking()`.
2. Unpack the new response shape: `result.message`, `result.command` (nullable).
3. Replace the `showProposal()` call with `writeReosResponse(result.message, result.command ?? null)`.
4. On failure: write a brief inline error to the terminal instead of hiding a spinner.

The `recordEvent('proposal_requested', ...)` and `recordEvent('proposal_generated', ...)` calls are kept. The `proposal_generated` payload adds `message: result.message ?? ''`.

### Step 7 — Frontend: Add terminal write helpers

Add three new functions in `reosView.ts`:

**`writeReosThinking()`** — writes the spinner line:

```typescript
function writeReosThinking(): void {
  if (!term) return;
  term.write('\r\n\x1b[38;2;88;166;255m[ReOS]\x1b[0m \x1b[2mthinking\u2026\x1b[0m\r\n');
}
```

**`eraseReosThinking()`** — moves up two lines (the content line and the preceding blank) and erases each:

```typescript
function eraseReosThinking(): void {
  if (!term) return;
  // Cursor up + erase line, twice: removes content line and preceding \r\n.
  term.write('\x1b[1A\x1b[2K\x1b[1A\x1b[2K');
}
```

Note: cursor-up + erase-line is `\x1b[1A\x1b[2K`. This is best-effort visual cleanup. See Risk 1 for the failure mode and mitigation.

**`writeReosResponse(message: string, command: string | null)`** — writes the full conversational response:

```typescript
function writeReosResponse(message: string, command: string | null): void {
  if (!term) return;

  eraseReosThinking();

  // Prefix on first line: [ReOS] in blue, then message body in dim
  const messageLines = message.split('\n');
  term.write('\r\n\x1b[38;2;88;166;255m[ReOS]\x1b[0m \x1b[2m' + messageLines[0] + '\x1b[0m\r\n');
  for (let i = 1; i < messageLines.length; i++) {
    term.write('       \x1b[2m' + messageLines[i] + '\x1b[0m\r\n');
  }

  if (command) {
    // Command line: bold, indented
    term.write('\r\n       \x1b[1mSuggested:\x1b[0m ' + command + '\r\n');
    // Y/n prompt in green
    term.write('       \x1b[38;2;62;185;80mRun?\x1b[0m [Y/n] ');

    // Enter intercept mode
    reosInterceptCommand = command;
    reosInterceptMode = true;
    reosResponseShownAt = Date.now();
  } else {
    // No command — conversational only. Return control immediately.
    term.write('\r\n');
  }
}
```

### Step 8 — Frontend: Modify `term.onData` to route through intercept mode

The existing handler (line 995):

```typescript
term.onData((data: string) => {
  const currentAuth = callbacks.getSessionCred();
  if (!currentAuth) return;
  const writeArgs = { ...ptyArgs(currentAuth), data };
  void invoke('pty_write', writeArgs).catch((e: unknown) => {
    console.error('[PTY] write error:', e);
  });
});
```

Becomes:

```typescript
term.onData((data: string) => {
  if (reosInterceptMode) {
    handleReosIntercept(data);
    return;
  }
  const currentAuth = callbacks.getSessionCred();
  if (!currentAuth) return;
  const writeArgs = { ...ptyArgs(currentAuth), data };
  void invoke('pty_write', writeArgs).catch((e: unknown) => {
    console.error('[PTY] write error:', e);
  });
});
```

**`handleReosIntercept(data: string)`**:

```typescript
function handleReosIntercept(data: string): void {
  const key = data.toLowerCase();
  const auth = callbacks.getSessionCred();
  if (!auth) {
    exitReosIntercept();
    return;
  }

  if (key === 'y' || data === '\r') {
    term?.write('y\r\n');
    recordEvent('user_action', {
      action: 'run',
      proposed_command: reosInterceptCommand,
      model_name: currentProposalMeta.model_name,
      latency_ms: currentProposalMeta.latency_ms,
      response_display_duration_ms: reosResponseShownAt ? Date.now() - reosResponseShownAt : null,
    });
    const writeArgs = { ...ptyArgs(auth), data: reosInterceptCommand + '\n' };
    void invoke('pty_write', writeArgs).catch((e: unknown) => {
      console.error('[PTY] write error:', e);
    });
    exitReosIntercept();
  } else if (key === 'n' || data === '\x1b') {
    term?.write('n\r\n\r\n');
    recordEvent('user_action', {
      action: 'dismiss',
      proposed_command: reosInterceptCommand,
      model_name: currentProposalMeta.model_name,
      latency_ms: currentProposalMeta.latency_ms,
      response_display_duration_ms: reosResponseShownAt ? Date.now() - reosResponseShownAt : null,
    });
    exitReosIntercept();
  }
  // All other keys: swallow silently.
}

function exitReosIntercept(): void {
  reosInterceptMode = false;
  reosInterceptCommand = '';
  reosResponseShownAt = null;
  term?.focus();
}
```

### Step 9 — Frontend: Update `teardownTerminalResources()`

Replace the `hideProposal()` call (line 1097) with `exitReosIntercept()`. This ensures that if the terminal is torn down mid-intercept, the intercept state is reset cleanly.

### Step 10 — Frontend: Update the suppression check in `scanForCommandNotFound()`

The current guard (line 772):
```typescript
if (fullInput && !proposalPending && proposalCard.style.display === 'none') {
```

`proposalCard` is removed. Replace with:
```typescript
if (fullInput && !proposalPending && !reosInterceptMode) {
```

Also update the `pty_line` event payload (line 763), changing:
```typescript
suppressed: proposalPending || proposalCard.style.display !== 'none',
```
to:
```typescript
suppressed: proposalPending || reosInterceptMode,
```

### Step 11 — Rename `proposalShownAt`

`proposalShownAt` is used only in the button handlers (removed in step 4) and `hideProposal()` (removed in step 4). The new name `reosResponseShownAt` is introduced in step 5 and used in step 8. No other references remain.

`currentProposalMeta` is retained unchanged — it stores model metadata for telemetry in both the old and new flows.

---

## Files Affected

### Modified
- `ReOS/src/reos/shell_propose.py`
  - Replace `STANDARD_PROMPT` and `CONSTRAINED_PROMPT` with `CONVERSATIONAL_PROMPT` and `CONSTRAINED_FALLBACK_PROMPT`
  - Add `extract_conversational_response()` function
  - Update `propose_command_with_meta()` return type and internal logic

- `ReOS/src/reos/rpc_handlers/propose.py`
  - Update response dict: rename `explanation` -> `message`, make `command` nullable
  - Update `proposal_generated` telemetry payload to include `message` field
  - Update `success` semantics (True when message generated, not only when command generated)

- `Cairn/apps/cairn-tauri/src/reosView.ts`
  - Remove proposal card DOM construction and button handlers (~120 lines removed)
  - Remove `showProposal()`, `hideProposal()`, `currentProposedCommand` state
  - Add `reosInterceptMode`, `reosInterceptCommand`, `reosResponseShownAt` state
  - Add `writeReosThinking()`, `eraseReosThinking()`, `writeReosResponse()` helpers
  - Add `handleReosIntercept()` and `exitReosIntercept()` helpers
  - Modify `term.onData` to check intercept mode
  - Rename `requestProposal()` -> `requestResponse()` (internal rename, single callsite)
  - Update `teardownTerminalResources()` to call `exitReosIntercept()`
  - Update suppression check in `scanForCommandNotFound()`

### Not Modified
- `ReOS/src/reos/shell_context.py` — context gathering unchanged
- `ReOS/src/reos/telemetry.py` — telemetry schema unchanged
- `Cairn/src/cairn/ui_rpc_server.py` — dispatch registration unchanged
- `CMD_NOT_FOUND_RE` regex — unchanged
- `extractUserInput()` — unchanged
- `scanForCommandNotFound()` outer structure — only the guard condition updated

---

## Risks and Mitigations

### Risk 1: Cursor-up erase clobbers user content
The `eraseReosThinking()` function uses `\x1b[1A\x1b[2K` twice. If the PTY has produced output between when the spinner was written and when the response arrives, the cursor-up may erase the wrong lines.

**Mitigation**: Add a `reosThinkingWritten: boolean` guard so `eraseReosThinking()` is a no-op if the spinner was never written (or if it has already been erased). Additionally, the implementer should test with real Ollama latency. If races are observed in practice, the erase can simply be removed — the spinner line remains in scrollback, which is visually noisy but harmless and does not corrupt terminal state.

### Risk 2: Intercept mode active when PTY produces background output
If the PTY sends output during the Y/n intercept window, that output scrolls through the terminal and visually displaces the `Run? [Y/n]` prompt. The intercept state is unaffected — the next Y/n keystroke still works correctly.

**Mitigation**: Acceptable given the short window (user reads one or two sentences and presses one key). Does not corrupt state.

### Risk 3: LLM omits `COMMAND:` sentinel for requests that obviously need one
If the LLM produces a conversational response without the sentinel, the frontend writes the message with no `Run?` prompt. The user gets helpful text but no shortcut.

**Mitigation**: The constrained fallback prompt exists for this case. If `extract_conversational_response()` returns `command=None` on the first attempt and the input `looks_like_command()` check suggests a command was expected, a second attempt using `CONSTRAINED_FALLBACK_PROMPT` can be made. The retry path already exists in `propose_command_with_meta()`.

### Risk 4: `extract_command()` correctly strips `COMMAND:` prefix
The existing prefix-stripping loop uses `.lower()` comparison. The LLM will write `COMMAND:` (all-caps per the prompt) which lowercases to `command:`, matching the existing entry in the prefix list. No code change needed. This should be verified in tests.

### Risk 5: Escape key delivery in xterm.js
The Escape key (`\x1b`) is also the prefix byte for multi-byte escape sequences (arrow keys, function keys). A standalone Escape should arrive in `onData` as the single byte `\x1b`. If it arrives as a partial sequence prefix, the exact-equality check `data === '\x1b'` will fail silently and the keystroke will be swallowed (the intercept mode stays active).

**Mitigation**: In `handleReosIntercept`, use `data.startsWith('\x1b')` rather than `data === '\x1b'` for the escape check. Arrow keys and function keys start with `\x1b[` or `\x1b[O` — these should also dismiss the prompt since the user is clearly trying to navigate. Swallowing arrow keys while in intercept mode would be confusing.

### Risk 6: The `edit` action disappears from telemetry
The `btnEdit` handler recorded `user_action` with `action: 'edit'`. The inline system has no edit affordance. Existing telemetry queries filtering on `action = 'edit'` will find zero results going forward.

**Mitigation**: Intentional behavioral change. The edit use case is served by dismiss + Up arrow in the shell. The change is noted here for awareness.

### Risk 7: `propose_command_with_meta()` return consumed in two places
The CLI entrypoint at the bottom of `shell_propose.py` unpacks this return tuple. After the change the positions shift. The CLI path must be updated alongside the RPC handler update.

---

## New Prompt Text (Final)

```python
CONVERSATIONAL_PROMPT = """You are ReOS, a natural language assistant embedded in a Linux terminal.
The user typed something the shell did not recognize. Help them.

FORMAT YOUR RESPONSE IN TWO PARTS:

First, write 1-3 sentences explaining what the user likely wants and what
tool or approach to use. Be direct. No markdown. Under 60 words.

Second, if a specific runnable shell command applies, write exactly:
COMMAND: <the full shell command here>

If no specific command applies (greeting, question with no shell equivalent,
etc.), omit the COMMAND line entirely.

RULES:
- No markdown formatting (no backticks, no asterisks, no hash symbols)
- COMMAND line contains ONLY the bare command, nothing else
- Use sudo when root privileges are required
- Never suggest dangerous commands (rm -rf /, dd to block devices, etc.)

EXAMPLES:

Input: show running processes
It looks like you want to see what is running. Use ps for a snapshot or htop for a live interactive view.
COMMAND: ps aux --sort=-%cpu | head -20

Input: install vim
You want to install the Vim text editor from the Ubuntu package repositories.
COMMAND: sudo apt install vim

Input: hello
Hello. I am ReOS. Type Linux commands here, or describe what you want to do in plain English and I will suggest the right command.

Input: what is my ip address
To see your machine's network addresses, ip addr lists all interfaces with their IPs. Use curl ifconfig.me for your public internet IP.
COMMAND: ip addr show

Input: list running services
This shows all systemd services that are currently active on your system.
COMMAND: systemctl list-units --type=service --state=running"""


CONSTRAINED_FALLBACK_PROMPT = """Output exactly one line: COMMAND: <shell command>
If no command applies, output: COMMAND: NONE

Task: {intent}"""
```

---

## Testing Strategy

### Backend tests (`ReOS/tests/`)

New file: `test_shell_propose_conversational.py`

- `test_extract_conversational_response_with_command()`: input contains `COMMAND:` sentinel, assert message and command are correctly split.
- `test_extract_conversational_response_without_command()`: input has no `COMMAND:` line, assert message is the full text and command is `None`.
- `test_extract_conversational_response_strips_message_prefix()`: input starts with `MESSAGE:`, assert it is stripped.
- `test_extract_conversational_response_caps_message_length()`: message over 500 chars is truncated.
- `test_extract_command_strips_command_prefix()`: regression guard confirming the existing `extract_command()` correctly handles `COMMAND:` prefix input.

New file or extend existing: `test_propose_rpc.py`

- `test_propose_returns_message_field()`: mock LLM response, assert `handle_reos_propose()` returns `message` key.
- `test_propose_returns_null_command_when_no_command()`: LLM returns conversational-only response, assert `command` is `None`.
- `test_propose_success_true_on_message_without_command()`: assert `success=True` when message generated even without command.

### Frontend verification

TypeScript unit tests are not currently in the codebase (no Jest/Vitest config in `apps/cairn-tauri/`). Manual testing is the primary verification path.

**Manual test checklist**:

1. Type `show running processes` -> verify `[ReOS] thinking...` appears, then conversational response with command and `Run? [Y/n]` prompt.
2. Press Y -> verify command is written to PTY and executes.
3. Repeat, press n -> verify terminal returns to shell prompt cleanly.
4. Repeat, press Escape -> verify same behavior as n.
5. Press an arrow key while in intercept mode -> verify it dismisses (not silently swallowed forever).
6. Type `hello` -> verify response appears with no `Run?` prompt, terminal immediately returns to shell.
7. Type a valid shell command (`ls`) -> verify no ReOS intervention.
8. While intercept mode is active, press a random letter (e.g., `a`) -> verify it is swallowed and intercept remains.
9. Trigger a proposal and while it is loading, type something in the terminal -> verify PTY write is not blocked (proposalPending prevents a second proposal but does not block normal typing).
10. Confirm telemetry events appear at `~/.talkingrock/reos_telemetry.db` for the full trace: `error_detected` -> `proposal_requested` -> `proposal_generated` -> `user_action`.

### Regression guards

- `CMD_NOT_FOUND_RE` regex is unchanged. No regression in detection.
- `extractUserInput()` logic is unchanged.
- `reos/vitals` RPC is independent. No regression risk.
- Safety validation (`is_safe_command()`) is unchanged.

---

## Definition of Done

- [ ] `CONVERSATIONAL_PROMPT` and `CONSTRAINED_FALLBACK_PROMPT` replace the old terse prompts in `shell_propose.py`.
- [ ] `extract_conversational_response()` function exists and unit tests pass.
- [ ] `propose_command_with_meta()` returns `(message, command, model_name, latency_ms, attempt_count)` where `command` is empty string when not applicable.
- [ ] `handle_reos_propose()` returns `{message, command, success, model_name, latency_ms}` with `command` nullable.
- [ ] The proposal card DOM elements (`proposalCard`, `proposalSpinner`, `proposalHeader`, `proposalCommand`, `proposalExplanation`, `proposalButtons`, `btnApprove`, `btnEdit`, `btnDismiss`) are removed from `reosView.ts`.
- [ ] No overlay elements are appended to `terminalPane`.
- [ ] `writeReosThinking()`, `eraseReosThinking()`, `writeReosResponse()` helpers exist and write via `term.write()`.
- [ ] `handleReosIntercept()` and `exitReosIntercept()` are implemented.
- [ ] `term.onData` routes through intercept mode check.
- [ ] `teardownTerminalResources()` calls `exitReosIntercept()`.
- [ ] `scanForCommandNotFound()` guard uses `reosInterceptMode` instead of `proposalCard.style.display`.
- [ ] `proposal_generated` telemetry event includes `message` field.
- [ ] `user_action` telemetry event uses `action: 'run' | 'dismiss'` (no `'edit'`).
- [ ] Manual test checklist items 1-10 completed.
- [ ] ReOS backend unit tests pass.

---

## Unknowns Requiring Validation Before or During Implementation

1. **Active Ollama model**: The conversational prompt is tuned for instruction-following models (llama3, mistral, qwen2.5). Verify via `ollama list` before testing. Very small base models may not follow the `COMMAND:` sentinel consistently.

2. **`eraseReosThinking()` behavior under load**: Verify `\x1b[1A\x1b[2K` behaves correctly in xterm.js at the bottom of a full terminal viewport. If the erase misfires in practice, remove it — the spinner line in scrollback is harmless.

3. **Escape key delivery**: Verify that a standalone Escape keypress delivers `\x1b` (single byte) to `onData`, not a partial sequence prefix. If it arrives as a prefix, use `data.startsWith('\x1b')` for the dismiss check.

4. **CLI wrapper in `shell_propose.py`**: The `propose_command()` CLI-facing function near the bottom of the file unpacks the return tuple. Confirm whether this path is exercised in the Tauri deployment and update accordingly.
