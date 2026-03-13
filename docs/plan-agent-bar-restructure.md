# Plan: Nav Bar → Agent Bar UI Restructure

## Context

### What Exists Today

The main shell (`apps/cairn-tauri/src/main.ts`, `buildUi()`) has a two-column layout:

```
shell (flex row, 100vh)
  ├── nav (280px fixed, flex column)
  │     ├── navContent (title, context meter, health indicator, dashboardBtn, playBtn)
  │     └── settingsBtn (pinned to bottom)
  └── mainViewContainer (flex: 1)
        └── cairnView.container (surfaced panel + chat panel, side by side)
```

The nav is a **horizontal-content sidebar** — a list of actions and utilities, not an agent-selector. It does not switch views. The main content area is always `cairnView`.

Key observations:
- `playBtn` in the nav calls `openPlayWindow()`, which opens The Play as a **separate browser window** (`/?view=play`). It is not the `createPlayOverlay()` popup.
- `createPlayOverlay()` is created and appended to root, but in the current code its trigger is not wired from the nav — `playBtn` opens a new window instead. The overlay is available but its `open()` method is only used by `openPlayScene` custom event handling (which is dispatched from `cairnView.ts` but never listened to in `main.ts` — it is currently unimplemented).
- `dashboardBtn` opens a separate window (`/?view=dashboard`).
- `cairnView` returns `{ container, addChatMessage, addAssistantMessage, showThinking, hideThinking, clearChat, getChatInput, updateSurfaced, persistAndShowFeedback }`. The container is a `div.cairn-view` containing the surfaced-panel and chat-panel side by side.
- The CSS class `.nav` applies `background: rgba(26, 26, 46, 0.95)` and is referenced in `style.css` at lines 103–119.
- `lastActivityTime` and `IDLE_THRESHOLD` are declared inside `buildUi()` and referenced by both `scheduleNextPoll` and `scheduleHealthPoll`. Any refactor must keep these in scope.

### Why Change

ReOS and RIVA are now extracted agents (separate repos). The Cairn UI needs to reflect the multi-agent reality of the Talking Rock ecosystem while remaining the single desktop window. Navigating between agents should feel like switching workspaces, not opening new windows.

---

## Approach A: Thin Agent Bar + View Router in `main.ts` (Recommended)

Extract the current nav into a narrow icon-or-icon+label **agent bar** (vertical, ~60–180px), and introduce a `ViewRouter` — a simple object that owns the `mainViewContainer` and swaps its content when the agent selection changes.

The agent bar contains:
- App wordmark/logo (top)
- CAIRN (default, selected on load)
- ReOS (placeholder)
- RIVA (placeholder)
- Divider + user-agent section (empty, populated from RIVA later)
- Settings (bottom, replaces current settings button)

The Play trigger moves from the nav into `cairnView` itself — either as a toolbar button above the chat panel or as a slash-command entry. The current window-based `openPlayWindow()` is preserved; its button just relocates.

**Files touched:** `main.ts`, `cairnView.ts`, `style.css`. New file: `agentBar.ts`, `reosView.ts`, `rivaView.ts`.

**Complexity:** Medium. The core risk is that `buildUi()` is a 700-line monolith with tightly scoped closures (`lastActivityTime`, `currentConversationId`, polling timers, `refreshAttentionItems`, health polling). The view router must be introduced without breaking these internal scopes.

**Reversibility:** High — the change is additive. The old nav structure can be reverted by removing the agent bar and reinstating the original nav block.

---

## Approach B: Inline Agent Sections Inside Existing Nav

Keep the current `.nav` div but expand it: add agent entries at the top, style the active one, and show/hide the `mainViewContainer`'s child depending on which agent is selected.

**Files touched:** `main.ts`, `style.css` only. No new files.

**Complexity:** Lower initially, but worsens the already-large `buildUi()` function. The nav grows to include view management logic. Placeholder views are inline divs rather than dedicated modules.

**Reversibility:** High.

**Assessment:** This approach works for the near term but will make the nav/view entanglement worse as ReOS and RIVA get real implementations. Defer to Approach A.

---

## Approach A: Detailed Plan (Recommended)

### Architecture

```
shell (flex row)
  ├── agentBar (60px icon-only, or 180px icon+label)
  │     ├── app logo
  │     ├── [CAIRN] ← default, selected
  │     ├── [ReOS]
  │     ├── [RIVA]
  │     ├── divider
  │     └── [Settings] (bottom)
  └── mainViewContainer (flex: 1)
        ← ViewRouter swaps content here
        active child is one of:
          cairnView.container     (CAIRN selected)
          reosPlaceholder         (ReOS selected)
          rivaPlaceholder         (RIVA selected)
```

The context meter, health indicator, and The Play trigger move out of the global nav and into CAIRN-specific scope:

- **Context meter** → top of `cairnView.container` (or a new header strip inside it)
- **Health indicator** → stays inside `cairnView.container` (it writes to `cairnView.addChatMessage`)
- **The Play trigger** → a button in the CAIRN view header or as a top-bar element that appears only when CAIRN is active
- **Settings** → bottom of agent bar (replaces settings button in nav)

The polling functions (`scheduleNextPoll`, `scheduleHealthPoll`, `updateNavContextMeter`) are CAIRN-specific and should live in the CAIRN activation scope, not global.

### ViewRouter Contract

A simple router object:

```typescript
interface ViewRouter {
  register(agentId: string, element: HTMLElement, onActivate?: () => void, onDeactivate?: () => void): void;
  switchTo(agentId: string): void;
  activeId(): string;
}
```

`register` stores the element and lifecycle hooks. `switchTo` hides all non-active elements, shows the target, and fires hooks. This is a ~30-line pure function — it does not need to be a class.

### The Play Trigger Migration

Currently `playBtn` in the nav calls `openPlayWindow()`, which opens `/?view=play` as a new Tauri WebviewWindow. This behavior is preserved. The button simply moves:

**Option 1:** Add a "The Play" button to `cairnView`'s header row (alongside the CAIRN wordmark). This is the lowest-risk move — one element relocates.

**Option 2:** Wire `createPlayOverlay()` as an in-window modal triggered from the CAIRN view header instead of the separate window. The overlay already exists and is fully implemented. This is a higher-value change but slightly more scope.

The plan recommends **Option 1** for this iteration (preserving the separate window behavior) with Option 2 noted as a follow-on.

---

## Implementation Steps

### Step 1: Create `agentBar.ts`

New file: `/home/kellogg/dev/Cairn/apps/cairn-tauri/src/agentBar.ts`

Exports `createAgentBar(onSelect: (agentId: string) => void): { element: HTMLElement; setActive: (agentId: string) => void }`.

Responsibilities:
- Build the vertical bar element with CSS class `agent-bar`
- Render CAIRN, ReOS, RIVA entries (hardcoded for now)
- Call `onSelect` when an entry is clicked
- Expose `setActive(id)` to update the active indicator (CSS class `active` on the item)
- Include settings button at the bottom

The element should be the full height of the shell, narrow (60px icon-only initially, expandable to 180px with label later).

### Step 2: Create `reosView.ts`

New file: `/home/kellogg/dev/Cairn/apps/cairn-tauri/src/reosView.ts`

Exports `createReosView(): { element: HTMLElement }`.

Renders a full-pane placeholder:
- Dark background consistent with the app theme
- ReOS icon/wordmark centered
- "ReOS — System Control Agent" subtitle
- "Coming soon. ReOS will surface system state and let you control your Linux environment from here." body
- Optionally a subtle gear icon

### Step 3: Create `rivaView.ts`

New file: `/home/kellogg/dev/Cairn/apps/cairn-tauri/src/rivaView.ts`

Exports `createRivaView(): { element: HTMLElement }`.

Same pattern as ReOS:
- RIVA icon/wordmark
- "RIVA — Code Verification Agent" subtitle
- "Coming soon. RIVA will surface code verification and project management from here."

### Step 4: Add `createViewRouter` to `main.ts` (or a new `viewRouter.ts`)

Given the small size (~30 lines), implement inline in `main.ts` as a local function `createViewRouter(container: HTMLElement)`. This avoids a new file for trivial logic.

### Step 5: Refactor `buildUi()` in `main.ts`

The structural changes inside `buildUi()`:

**Remove from nav:**
- `navTitle` element
- `dashboardBtn` (move to CAIRN view header or remove — the dashboard is a separate window and rarely used; confirm with user before removing)
- `playBtn` (move to CAIRN view header)
- `navContextMeter` and all associated polling/update logic
- `healthIndicator` and associated polling
- `settingsBtn` (move to agent bar)

**Keep as globals within `buildUi()`:**
- `lastActivityTime`, `IDLE_THRESHOLD`, `ACTIVE_POLL_INTERVAL`, `IDLE_POLL_INTERVAL` — these are needed for both attention polling and health polling; keep in `buildUi()` scope
- `currentConversationId` — needed for context stats
- `cairnView` instance
- `playOverlay`, `settingsOverlay`, `contextOverlay`

**Add:**
- `createAgentBar(...)` call
- `createViewRouter(mainViewContainer)` call
- `router.register('cairn', cairnView.container, onCairnActivate, onCairnDeactivate)`
- `router.register('reos', reosView.element)`
- `router.register('riva', rivaView.element)`
- Wire agent bar `onSelect` → `router.switchTo(id)` + `agentBar.setActive(id)`

**`onCairnActivate`:** Starts attention polling, health polling, context meter polling.
**`onCairnDeactivate`:** Could pause polling (optional optimization — for now, polling can continue regardless since it only updates CAIRN-specific UI elements).

**The Play button relocation:** In `cairnView.ts`, add a `setPlayButtonCallback(cb: () => void): void` or pass the callback through `CairnViewCallbacks`. When CAIRN is assembled in `main.ts`, pass `onOpenPlay: () => void openPlayWindow()`. Inside `cairnView`, render a "The Play" button in the chat header row.

Alternatively, place the Play button in `main.ts`'s CAIRN activation section, absolutely positioned over the CAIRN view header. This avoids touching `cairnView.ts`.

**Recommended:** Pass as a callback through `CairnViewCallbacks` — it's clean and keeps `cairnView` self-contained.

### Step 6: Update `style.css`

Add CSS classes:
- `.agent-bar` — vertical bar, `width: 60px`, `background`, border-right, flex column, align-items center
- `.agent-item` — each agent entry, padding, cursor pointer, hover state
- `.agent-item.active` — active indicator (accent border left or background tint)
- `.agent-item .agent-icon` — icon sizing
- `.agent-item .agent-label` — optional label (hidden in icon-only mode)
- `.reos-placeholder`, `.riva-placeholder` — full-pane placeholder styles (centered content, dark bg)

The existing `.nav` class can be kept for CSS specificity on the dark background. The new `.agent-bar` can share the same background token.

**Important:** The `.nav button:hover` rule currently applies to ALL buttons inside `.nav`. After this change, the agent bar buttons use `.agent-item` instead, so hover rules must move to `.agent-item:hover`. Audit for unintended selector bleed.

### Step 7: Wire `openPlayScene` custom event

The `openPlayScene` event is dispatched from `cairnView.ts` (line 1710) when the user clicks a Scene in the surfaced panel. It was never handled in `main.ts`. Now that The Play overlay is in scope:

In `main.ts`, after creating `playOverlay`:
```
window.addEventListener('openPlayScene', (e: Event) => {
  const { actId, sceneId } = (e as CustomEvent).detail;
  playOverlay.open(actId, sceneId);
});
```

This is a small but valuable correctness fix — Scene click-through to The Play will now work.

---

## Files Affected

| File | Action | Notes |
|------|--------|-------|
| `apps/cairn-tauri/src/main.ts` | Modify | Remove old nav block, add agent bar + view router wiring, wire openPlayScene |
| `apps/cairn-tauri/src/cairnView.ts` | Modify | Add `onOpenPlay` to `CairnViewCallbacks`, render Play button in chat header |
| `apps/cairn-tauri/src/style.css` | Modify | Add `.agent-bar`, `.agent-item`, placeholder styles; migrate `.nav button:hover` |
| `apps/cairn-tauri/src/agentBar.ts` | Create | Agent bar component |
| `apps/cairn-tauri/src/reosView.ts` | Create | ReOS placeholder view |
| `apps/cairn-tauri/src/rivaView.ts` | Create | RIVA placeholder view |

No backend changes. No new RPC endpoints. No TypeScript types changes needed.

---

## Risks & Mitigations

### Risk 1: Polling timers lose their closure references

`scheduleHealthPoll` references `lastActivityTime` and `IDLE_THRESHOLD`. If these are moved into a sub-scope during refactor, the health poll will break silently (no error, just stale data).

**Mitigation:** Keep `lastActivityTime`, `IDLE_THRESHOLD`, and the polling scheduling functions at the top of `buildUi()` scope. Do not move them into sub-functions or the agent activation callbacks. The activation callback only _starts_ the timer; it does not own the variables.

### Risk 2: The Play overlay vs. The Play window: two entry points, one state

Currently The Play window (`/?view=play`) and `createPlayOverlay()` are two separate implementations of the same feature. After this change, the Play button in CAIRN view will continue to open the window. The overlay is wired for `openPlayScene`. This creates two paths that can both show Play state.

**Mitigation:** Accept this for now. Document the duality. The long-term resolution (Option 2 above) is to make the overlay the primary entry point and deprecate the separate window. That is a follow-on change, not part of this plan.

### Risk 3: `healthIndicator.style.display = 'flex'` vs. `'none'` — element must be in the CAIRN view

The health indicator currently writes to `cairnView.addChatMessage` on click (line 252–263). If the health indicator moves inside `cairnView.container`, the click handler references `cairnView` directly — that is fine. But if health polling runs while the CAIRN view is hidden (ReOS or RIVA active), the health indicator visibility toggle is a no-op because the element is not visible anyway.

**Mitigation:** No action needed. The health polling continues regardless of active agent. The indicator simply becomes visible when CAIRN is next switched to. This is correct behavior.

### Risk 4: CSS selector `.nav button` bleeds into agent bar

If the agent bar is appended before the main content and shares a parent class with `.nav`, the `.nav button` hover/background rules may apply to agent bar items unexpectedly.

**Mitigation:** The agent bar uses `.agent-item` (a `div`, not a `button`, optionally) or `.agent-bar button` scoped rules. Ensure `.nav` class is only applied to the old nav remnant (now likely removed or repurposed as a header/status area within CAIRN view).

### Risk 5: `dashboardBtn` removal/relocation

The System Dashboard button currently opens a Tauri WebviewWindow. If removed from the nav without a new home, the dashboard becomes unreachable.

**Mitigation:** Confirm with user whether dashboard access is needed in the CAIRN view header, in the Settings overlay, or can be temporarily removed. Do not silently drop it. The implementer should surface this question before removing the button.

---

## Testing Strategy

There are no automated frontend tests for the Tauri UI. Testing is manual.

### Functional Checklist (manual)

- [ ] App loads and shows CAIRN view by default (agent bar shows CAIRN as active)
- [ ] Clicking ReOS in agent bar switches content area to ReOS placeholder
- [ ] Clicking RIVA in agent bar switches content area to RIVA placeholder
- [ ] Clicking CAIRN in agent bar returns to CAIRN view with chat and attention panes intact
- [ ] Chat history is preserved when switching away from CAIRN and back
- [ ] The Play button in CAIRN view opens The Play window (same behavior as before)
- [ ] Settings button in agent bar opens the settings overlay
- [ ] Context meter still shows and updates while on CAIRN view
- [ ] Health indicator appears when findings exist and clicking it adds to chat
- [ ] Clicking a Scene in the surfaced attention panel now opens `playOverlay` (was previously broken — now fixed by wiring `openPlayScene`)
- [ ] The Play overlay closes on Escape and backdrop click
- [ ] No console errors on any view switch

### Regression Checklist

- [ ] Sending a CAIRN message still works (async chat → poll → response)
- [ ] Consciousness events appear in message details
- [ ] Attention items refresh after chat (surfaced panel updates)
- [ ] Auto-archive on window close still fires
- [ ] Lock screen still appears on session expiry

---

## Definition of Done

- [ ] `agentBar.ts`, `reosView.ts`, `rivaView.ts` created and exported correctly
- [ ] `main.ts` refactored: old nav replaced by agent bar + view router
- [ ] `cairnView.ts` updated: Play button added to header via `onOpenPlay` callback
- [ ] `style.css` updated: new classes added, old `.nav button` rules migrated
- [ ] `openPlayScene` event now handled in `main.ts` (correctness fix)
- [ ] Manual checklist above passes completely
- [ ] No TypeScript errors (`tsc --noEmit` passes)
- [ ] No regressions in CAIRN chat, attention panel, or overlays

---

## Confidence Assessment

**High confidence** in the structural approach. The codebase is well-factored at the module level — `cairnView.ts`, `playOverlay.ts`, and `settingsOverlay.ts` are already self-contained components. The view router pattern is trivial. The main risk is the monolithic `buildUi()` scope with tightly coupled polling timers, but the mitigation (keep polling variables in `buildUi()` scope, not in sub-functions) is straightforward.

**Medium confidence** on the exact Play button placement. The plan recommends adding `onOpenPlay` to `CairnViewCallbacks`, but the implementer should confirm: does the Play button belong in the CAIRN chat header (inside `chatPanel`), or as a separate top-bar element above `cairnView.container`? Both work; the former is cleaner.

## Open Assumptions

1. **Dashboard button fate:** The `dashboardBtn` for the System Dashboard window has no designated new home in this plan. Confirm with user: move to CAIRN view header, move to settings overlay, or remove.
2. **Agent bar width:** 60px icon-only vs. 180px icon+label. The plan is written for 60px icon-only, which is more compact. If labels are desired immediately, the agent bar needs a label column and slightly more CSS.
3. **The Play window vs. overlay:** The plan preserves the separate window behavior. If the user wants the Play trigger to open the in-window overlay instead (Option 2), that is a scoped follow-on — `playOverlay.open()` replaces `openPlayWindow()` in one line.
