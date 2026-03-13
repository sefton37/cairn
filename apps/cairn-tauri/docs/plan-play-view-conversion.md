# Plan: Convert The Play from Overlay to In-App View

## Context

The Play is currently implemented as a full-screen modal overlay (`playOverlay.ts`, 1099 lines).
It is mounted directly on `#app` root, lives outside `mainViewContainer`, and is opened/closed
via `playOverlay.open()` / `playOverlay.close()`. The agent bar treats it as a special top item
that calls `onOpenPlay()` rather than routing through `switchView()`.

The goal is to make The Play a peer view of cairn/reos/riva: listed in the agent bar like the
other agents, visible in `mainViewContainer` when selected, and never drawn as an overlay.

**Key insight (confirmed by reading the source):** `playOverlay.ts` builds two DOM layers:
1. `overlay` — the outer `.play-overlay` div (position: fixed, full-screen backdrop, z-index 1000)
2. `container` — the inner `.play-container` div (the actual UI: header + sidebar + content)

The `container` already has the correct layout for an inline view. The plan is to expose it
directly and discard the outer `overlay` wrapper, leaving the 1099-line interior logic untouched.

**Discovered during research:** `main.ts` contains a second, entirely separate Play inspector
implementation (`renderPlayInspector`, `refreshActs`, `refreshScenes`, `activeActId`,
`actsCache`, `selectedSceneId`, `scenesCache`, `kbSelectedPath`, `kbTextDraft`, `kbPreview`,
lines 540–1115 approximately). This code renders into `inspectionBody`/`inspectionTitle` —
detached stub divs that are never appended to the DOM. The `playInspectorActive` flag guards
the render calls, but `refreshActs`/`refreshScenes` still execute at startup (line 1208–1209).
This is dead code. The plan must account for it.

---

## Approach A — Recommended: Expose the inner container directly

Add a `viewElement` to the return value of `createPlayOverlay` that points to `container`
(the `.play-container` div) rather than `overlay` (the `.play-overlay` wrapper). `main.ts`
uses `viewElement` as the view in `mainViewContainer` and never mounts `overlay` at all.

**Scope:**
- `playOverlay.ts` — add one property to the return object; remove dead overlay listeners
- `agentBar.ts` — add `'play'` to `AgentId`, add Play to `CORE_AGENTS`, remove special `playItem`
  block and `onOpenPlay` from the interface
- `main.ts` — four areas of change: (1) add Play to viewMap + mainViewContainer, (2) remove
  overlay mount, (3) wire `playOverlay.open()` on view switch, (4) remove dead inspector code
  (`renderPlayInspector` block and associated state variables)
- `style.css` — remove `margin: 24px` from `.play-container`

**Risk:** Low for the overlay conversion. Moderate for removing dead inspector code — it is
definitely dead (inspectionBody is never in the DOM) but the block is large (~450 lines in
main.ts) and removing it in the same PR increases diff size.

**Recommendation:** Split into two commits. Commit 1: the view conversion (minimal, low-risk).
Commit 2: delete the dead `renderPlayInspector` block (cleanup).

---

## Approach B — Rename and rebuild as a fresh view component

Create a new `playView.ts` that calls the same kernel endpoints but is built as a plain view
from scratch (no overlay wrapper ever). `playOverlay.ts` is deleted or kept for reference.

**Scope:** Large. Rewrites 1099 lines of working UI logic. High risk of regressions.
Rejected — contradicts the stated goal of touching as little code as possible.

---

## Implementation Steps

### Step 1 — `playOverlay.ts`: expose `container` as `viewElement`

At the return object (line 1094), add `viewElement: container`:

```ts
return {
  element: overlay,       // can be left for now; no longer mounted
  viewElement: container, // ← ADD: the inner layout div
  open: openOverlay,
  close,
};
```

Also remove the two dead event listeners in the same pass:

**Backdrop click (lines 141–145):** Delete — dead once `overlay` is not in the DOM.

**Escape keydown (lines 148–152):** Delete — this listener IS attached to `document`, so it
fires even if `overlay` is not in the DOM. If left in place and Play is the active view, pressing
Escape will call `close()` which calls `onClose()` (a no-op after step 3) and sets `state.isOpen`
to false. It will not crash but it is misleading. Remove it.

### Step 2 — `agentBar.ts`: add 'play' as a regular agent

**Line 11:** Extend the union:
```ts
export type AgentId = 'cairn' | 'reos' | 'riva' | 'play';
```

**Lines 13–17 — `AgentBarCallbacks` interface:** Remove `onOpenPlay`:
```ts
interface AgentBarCallbacks {
  onSwitchAgent: (id: AgentId) => void;
  onOpenSettings: () => void;
}
```

**Lines 26–30 — `CORE_AGENTS`:** Add Play at the top to preserve current visual order:
```ts
const CORE_AGENTS: AgentEntry[] = [
  { id: 'play',  label: 'The Play', icon: '\u{1F3AD}', description: 'Life organization' },
  { id: 'cairn', label: 'CAIRN',    icon: '\u{1F9ED}', description: 'Attention minder' },
  { id: 'reos',  label: 'ReOS',     icon: '\u{1F5A5}\uFE0F', description: 'System control' },
  { id: 'riva',  label: 'RIVA',     icon: '\u{1F4CB}', description: 'Agent orchestrator' },
];
```

**Lines 62–92 — the `playItem` special block:** Delete entirely. The loop over `CORE_AGENTS`
now renders The Play as a standard item, including active-state styling via `setActive()`.

**`setActive()` function (lines 185–196):** No change needed. It iterates the `items` Map, which
is populated from `CORE_AGENTS`. Play will be included automatically.

**Initial state (line 199):** The app currently starts with `setActive('cairn')`. Leave this
unless you want Play as the landing view — in that case change to `setActive('play')` and ensure
`main.ts` also starts with Play visible.

### Step 3 — `main.ts`: wire Play into the view router

**`createPlayOverlay` call (lines 579–581):** The `onClose` callback now does nothing useful.
Pass an empty function:
```ts
const playOverlay = createPlayOverlay(() => {});
```

**`viewMap` (lines 564–568):** Add the play entry using `viewElement`:
```ts
const viewMap: Record<AgentId, HTMLElement> = {
  cairn: cairnView.container,
  reos:  reosView.container,
  riva:  rivaView.container,
  play:  playOverlay.viewElement,  // ← ADD
};
```

**`mainViewContainer` population (lines 557–561):** Append and hide Play:
```ts
mainViewContainer.appendChild(cairnView.container);
mainViewContainer.appendChild(reosView.container);
mainViewContainer.appendChild(rivaView.container);
mainViewContainer.appendChild(playOverlay.viewElement);   // ← ADD
reosView.container.style.display = 'none';
rivaView.container.style.display = 'none';
playOverlay.viewElement.style.display = 'none';           // ← ADD
```

**`root.appendChild(playOverlay.element)` (line 599):** Remove this line. The outer overlay
wrapper is no longer mounted.

**`onSwitchAgent` in `createAgentBar` call (lines 584–591):** Replace `onOpenPlay` with a
Play-specific hook inside `onSwitchAgent`:
```ts
const agentBar = createAgentBar({
  onSwitchAgent: (id) => {
    switchView(id);
    if (id === 'play') {
      playOverlay.open();  // triggers refreshData() + render() inside playOverlay
    }
  },
  onOpenSettings: () => settingsOverlay.show(),
});
```
Remove the `onOpenPlay` property entirely.

**`playInspectorActive` (lines 580, 588, 624–625):** These three locations must all be removed:
- Line 580: `playInspectorActive = false;` (inside the `onClose` callback — removed with the callback)
- Line 588: `playInspectorActive = true;` (inside `onOpenPlay` — removed with that callback)
- Lines 624–625: `let playInspectorActive = false;` — delete

The guards at lines 1123 and 1135 (`if (playInspectorActive) { renderPlayInspector(); }`) can
be left as dead `if (false)` branches, or the entire dead inspector block can be removed
in a separate cleanup commit (recommended — see Commit 2 note below).

**Startup `refreshActs` call (lines 1208–1209):** After removing `playInspectorActive`, the
`refreshActs()` and `refreshScenes()` calls at startup will still run but `renderPlayInspector()`
will never fire (the guards will always be false). The data fetches themselves are benign but
wasteful. They should be removed in the cleanup commit.

### Step 4 — `style.css`: fix `.play-container` layout

`.play-container` (line 339) currently has `margin: 24px` which creates a floating-box
appearance suitable for a modal but wrong for an inline view. Change to `margin: 0`.

Additionally consider:
- `border-radius: 0` — makes it flush with the viewport edge like the other views
- `border: none` and `box-shadow: none` — removes the modal "card" framing

These are cosmetic and optional. The only required change is `margin: 0`.

### Commit 2 (cleanup, separate PR) — remove dead inspector code from `main.ts`

The block from approximately lines 540–1115 in `main.ts` contains:
- `inspectionTitle`, `inspectionBody` stub elements (never mounted)
- `activeActId`, `actsCache`, `selectedSceneId`, `scenesCache`, `kbSelectedPath`, `kbTextDraft`,
  `kbPreview` state variables (duplicates of what lives inside `playOverlay.ts`)
- `renderPlayInspector()` and all its sub-functions
- `refreshActs()`, `refreshScenes()`, `refreshKbForSelection()`
- `showJsonInInspector()`

All of this is dead code. Removing it shrinks `main.ts` by roughly 450 lines. This is safe
but is a large diff with no behavioral change, so it belongs in a separate commit after the
view conversion is verified working.

---

## Files Affected

| File | Action | Commit |
|------|--------|--------|
| `apps/cairn-tauri/src/playOverlay.ts` | Modify: +1 line return, remove 2 event listeners (~12 lines) | 1 |
| `apps/cairn-tauri/src/agentBar.ts` | Modify: extend AgentId, add to CORE_AGENTS, remove playItem block + onOpenPlay | 1 |
| `apps/cairn-tauri/src/main.ts` | Modify: add to viewMap/container, remove overlay mount, rewire onSwitchAgent, remove playInspectorActive | 1 |
| `apps/cairn-tauri/src/style.css` | Modify: margin: 0 on .play-container (+ optional cosmetics) | 1 |
| `apps/cairn-tauri/src/main.ts` | Modify: delete ~450 lines of dead inspector code | 2 |

---

## Risks & Mitigations

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| `.play-container` does not fill `mainViewContainer` | Low | Container has `flex: 1; display: flex; flex-direction: column` — same as other views |
| Escape key fires `close()` on Play view | Medium (if step 1 cleanup skipped) | Remove the `keydown` listener in `playOverlay.ts` |
| `playInspectorActive` reads at lines 1123/1135 break after variable deletion | None | After removing the variable declaration and its assignments, the guards become `if (false)` — or remove the entire dead block in commit 2 |
| `refreshActs`/`refreshScenes` still fire at startup after commit 1 | Low — benign network call | Removed in commit 2; harmless in commit 1 |
| TypeScript errors from incomplete `Record<AgentId, HTMLElement>` | Certain if partial | Add `'play': playOverlay.viewElement` to `viewMap` in the same change that adds `'play'` to `AgentId` |
| `onOpenPlay` callback type mismatch | Certain if partial | Remove from interface and call site in the same change |
| The Play does not refresh when re-selected | Low | `playOverlay.open()` in `onSwitchAgent` always calls `refreshData()`, so re-selecting Play re-fetches |

---

## Testing Strategy

Manual (no automated UI tests exist for the Tauri frontend layer):

1. **Inline rendering:** Clicking "The Play" in the agent bar shows The Play UI in the main
   content area, not as an overlay. The sidebar and content pane fill the available space.
2. **View switching:** Switching away from Play to CAIRN/ReOS/RIVA and back correctly
   hides/shows each view. No stale state between switches.
3. **Active state highlight:** The Play item in the agent bar shows the blue active background
   when selected, same as other agents.
4. **Data loads on switch:** On switching to Play, acts and scenes populate the sidebar.
   On switching away and back, data reloads.
5. **No overlay remnant:** Inspect the DOM — `#app` should not contain a `.play-overlay` element.
6. **No ghost Escape behavior:** Pressing Escape while the Play view is active does not trigger
   any close/hide action.
7. **Other overlays unaffected:** Settings overlay and Context overlay still open and close
   normally.
8. **Layout:** `.play-container` fills the main area edge-to-edge with no floating margin.

---

## Definition of Done

- [ ] `AgentId` union includes `'play'`
- [ ] `CORE_AGENTS` in agentBar.ts includes the Play entry at the top
- [ ] Special `playItem` block is removed from agentBar.ts
- [ ] `onOpenPlay` is removed from `AgentBarCallbacks` interface and from the `createAgentBar` call
- [ ] `playOverlay.viewElement` is returned from `createPlayOverlay`
- [ ] `playOverlay.viewElement` is appended to `mainViewContainer` and hidden by default
- [ ] `root.appendChild(playOverlay.element)` is removed from main.ts
- [ ] `playOverlay.open()` is called when switching to Play
- [ ] `playInspectorActive` variable and all its assignment sites are removed
- [ ] Escape key `keydown` listener is removed from `playOverlay.ts`
- [ ] `.play-container` has `margin: 0` in style.css
- [ ] TypeScript compiles without errors
- [ ] All 7 manual test scenarios above pass
- [ ] (Commit 2) Dead inspector block in main.ts is deleted

---

## Confidence Assessment

**High confidence on the conversion itself.** The plan is grounded in direct reading of all
four affected files. The inner/outer DOM split in `playOverlay.ts` is confirmed at lines 101–138.
The `viewMap` routing pattern is the established mechanism for all existing views. No new patterns
are introduced.

**Medium confidence on the dead code boundary.** The `renderPlayInspector` block in `main.ts`
is large and was not read in full. Before commit 2, the implementer should verify there are no
other callers outside the grep results, and that removing the block does not affect any startup
path other than the two `refreshActs`/`refreshScenes` calls at lines 1208–1209.

**Validated assumption:** `playInspectorActive` IS read at lines 1123 and 1135 (grep confirmed).
The plan accounts for this — the variable is removed in commit 1 and the guards become dead
`if (false)` branches, cleaned up in commit 2.
