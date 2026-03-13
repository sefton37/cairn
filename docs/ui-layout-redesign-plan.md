# Plan: UI Layout Redesign — Two-Column Attention Panel + Consciousness-in-Chat

## Context

The current main window layout (1920px wide) is four columns:

| Panel | Width | Notes |
|-------|-------|-------|
| Nav sidebar | 280px | Fixed |
| What Needs Attention | 320px | Mixed calendar + email in a single scrollable list |
| Chat (CAIRN) | flex (~840px at 1920) | Has "Show details" on assistant messages |
| Consciousness Stream | 480px | Real-time events polled at 200ms |

The total non-nav space is 1640px. Removing the 480px consciousness panel and reallocating it to the attention panel gives 800px for "What Needs Attention" (up from 320px), with the chat panel keeping its flex fill at approximately 840px.

**Why change:** The consciousness stream panel occupies 480px of persistent screen real estate but is only active during the 5-30 seconds a response is generating. The rest of the time it shows a static event log from the previous response — useful for developers during a session, but not for daily use. Moving the consciousness data per-message into the "Show details" popout makes it contextually useful (you can re-read what CAIRN was thinking about that specific response at any time) while freeing the space for the attention panel, which is always relevant.

---

## Approach (Recommended)

### Layout

At 1920px:
- Nav: 280px (unchanged)
- What Needs Attention: **800px** (two 50/50 columns = ~390px each after gap/padding)
- Chat: flex, fills remaining ~840px
- Consciousness: removed

800px is the right choice for the attention panel:
- 320px was too narrow — single-column email cards truncated sender and subject
- The full 800px (480px recovered + 320px original) gives room for two comfortable columns
- Two 390px columns match the width common task management UIs use for card columns
- The chat panel at 840px flex is actually wider than before (was ~840px at 1920 with three dynamic columns), so chat UX is preserved

### Two-Column Split in the Attention Panel

The `updateSurfaced()` function already receives `entity_type` on each item (`'scene'` for calendar/task items, `'email'` for email). Split on that field:

```
Left column  — header "Calendar & Tasks" — items where entity_type !== 'email'
Right column — header "Email"            — items where entity_type === 'email'
```

Both columns are independently scrollable. Drag-and-drop is kept within each column (cross-column drag is out of scope — the reorder RPC operates on entity priority within the full list, not by column).

### Consciousness Events Per Message

**The capture problem:** Currently `consciousnessEvents[]` is a closure variable reset on each message send (`startConsciousnessPolling` at line 638-644). When `stopConsciousnessPolling` is called from `hideThinking()` (line 1161), the events are already accumulated. The fix is to snapshot them at that moment and attach the snapshot to the `MessageData` being added.

**Timing:** `hideThinking()` is called from `main.ts` at line 565, and then `addAssistantMessage()` is called at line 570. This means:
1. `hideThinking()` fires — polling stops, `consciousnessEvents` is complete for this response
2. `addAssistantMessage()` fires — builds `MessageData` and renders the bubble

The cleanest approach: expose a `getConsciousnessEvents()` accessor from `createCairnView` (or make `hideThinking` return the events), and pass the snapshot into `addAssistantMessage` from `main.ts`. Alternatively, capture inside `cairnView.ts` itself — since `addAssistantMessage` is always called immediately after `hideThinking`, just read `consciousnessEvents` directly in `addAssistantMessage` (they are in the same closure scope).

**The in-closure approach is preferred** — it requires zero changes to the `createCairnView` public API and zero changes to `main.ts`. `addAssistantMessage` already runs inside the same closure as `consciousnessEvents`. Simply read the current value of `consciousnessEvents` when building `MessageData`.

### Consciousness in "Show details"

Currently `renderChatMessage` shows "Show details" when `hasDetails` is true (line 687):
```typescript
const hasDetails = role === 'assistant' && (
  (thinkingSteps && thinkingSteps.length > 0) ||
  (toolCalls && toolCalls.length > 0)
);
```

After this change, `hasDetails` should also be true when `consciousnessEvents` is non-empty. The details panel renders three sections, each optional: Thinking Steps, Tool Calls, and (new) Consciousness Events.

**Rendering approach — inline sections (not tabs):** Three collapsible sections inside the existing details panel. This matches the pattern already used for thinking steps vs. tool calls: each section has a colored header label and its content below. Tabs add DOM complexity and state management; there is no reason to hide one section to show another. The details panel already has `max-height: 300px; overflow-y: auto` — with three sections it may want `max-height: 400px` to be comfortable.

The consciousness section renders the same event rows as `consciousnessPane.ts`: icon + headline + optional expandable content. Reuse the same rendering logic (copy the `renderEvent` function pattern into `cairnView.ts` or extract it to a shared module — see Alternatives below).

---

## Alternatives Considered

### Alternative A: Keep consciousness panel, add a toggle to hide/show it

**Pros:** Zero layout change risk; consciousness stream stays real-time during response.
**Cons:** The panel is still 480px of wasted space when idle. Toggling requires persistent state. It doesn't solve the "I can't re-read what CAIRN thought about a specific old response" problem.
**Verdict:** Set aside. The user explicitly wants the panel removed. The real-time streaming experience during the 20 seconds of processing is less valuable than persistent per-message access.

### Alternative B: Narrow the consciousness panel to ~200px instead of removing it

**Pros:** Keeps real-time streaming visible.
**Cons:** 200px is too narrow to read event text without truncation. The attention panel would still only grow to ~600px — too constrained for comfortable two-column layout.
**Verdict:** Set aside. 200px makes the stream unreadable and still doesn't free enough space.

### Alternative C: Extract renderEvent to a shared module

**Pros:** `consciousnessPane.ts` and `cairnView.ts` share the rendering logic without duplication.
**Cons:** Adds a new file (`consciousnessEventRenderer.ts` or similar) for a relatively small function. The rendering is simple enough to duplicate safely.
**Verdict:** Optional refactor, not required for this plan. The implementer should decide based on their judgment of duplication tolerance. If they extract it, the new file is `apps/cairn-tauri/src/consciousnessEventRenderer.ts`.

### Alternative D: Consciousness events as a separate tab in details panel

**Pros:** Clean separation; doesn't make the details panel taller.
**Cons:** Adds tab state management (which tab is active). The existing details panel has no tab infrastructure. Three inline sections with headers are simpler and more consistent with the current thinking steps / tool calls presentation.
**Verdict:** Set aside. Tabs are complexity without benefit here.

---

## Implementation Steps

### Step 1 — Extend `MessageData` to carry consciousness events

**File:** `apps/cairn-tauri/src/cairnView.ts`

Add `consciousnessEvents?: ConsciousnessEvent[]` to the `MessageData` interface (line ~22-39):

```typescript
interface MessageData {
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  thinkingSteps?: string[];
  toolCalls?: Array<{ ... }>;
  messageId?: string;
  messageType?: string;
  extendedThinkingTrace?: ExtendedThinkingTrace | null;
  consciousnessEvents?: ConsciousnessEvent[];   // NEW
}
```

### Step 2 — Capture events snapshot in `addAssistantMessage`

**File:** `apps/cairn-tauri/src/cairnView.ts`, function `addAssistantMessage` (~line 1135)

`addAssistantMessage` is inside the same closure as `consciousnessEvents`. Add the snapshot:

```typescript
function addAssistantMessage(result: ChatRespondResult): void {
  const data: MessageData = {
    role: 'assistant',
    content: result.answer,
    timestamp: new Date(),
    thinkingSteps: result.thinking_steps,
    toolCalls: result.tool_calls,
    messageId: result.message_id,
    messageType: result.message_type,
    extendedThinkingTrace: result.extended_thinking_trace,
    consciousnessEvents: consciousnessEvents.length > 0
      ? [...consciousnessEvents]   // snapshot — defensive copy
      : undefined,
  };
  // rest unchanged
}
```

The defensive copy is important: `consciousnessEvents` is a mutable array that gets cleared on the next `startConsciousnessPolling` call. Without the copy, all previous messages' events would be wiped when the next message is sent.

### Step 3 — Update `hasDetails` check in `renderChatMessage`

**File:** `apps/cairn-tauri/src/cairnView.ts`, function `renderChatMessage` (~line 685-792)

```typescript
const hasDetails = role === 'assistant' && (
  (thinkingSteps && thinkingSteps.length > 0) ||
  (toolCalls && toolCalls.length > 0) ||
  (data.consciousnessEvents && data.consciousnessEvents.length > 0)   // NEW
);
```

Note: `renderChatMessage` receives `data: MessageData` — destructure `consciousnessEvents` from it alongside the other fields.

### Step 4 — Add consciousness section to `detailsPanel` HTML

**File:** `apps/cairn-tauri/src/cairnView.ts`, inside `renderChatMessage` (~line 744-778)

After the existing tool calls section, add:

```typescript
if (data.consciousnessEvents && data.consciousnessEvents.length > 0) {
  detailsHTML += `
    <div style="margin-top: 12px;">
      <div style="color: #a78bfa; font-weight: 600; margin-bottom: 6px;">
        Consciousness Stream (${data.consciousnessEvents.length} events)
      </div>
      <div class="details-consciousness-events">
        ${data.consciousnessEvents.map((evt, i) => renderConsciousnessEventHtml(evt, i)).join('')}
      </div>
    </div>
  `;
}
```

Add a local helper `renderConsciousnessEventHtml(evt, index)` that generates the same HTML as `consciousnessPane.ts`'s `renderEvent()`. Use the same `EVENT_TYPE_CLASSES` and `EVENT_TYPE_ICONS` maps — either import from a shared module (Alternative C) or copy them to the top of `cairnView.ts`.

The expand/collapse behavior for individual events inside the details panel: because this is rendered as a `innerHTML` string (same pattern as the existing details panel), event attachment requires a post-render pass. The simplest approach is to attach a delegated click handler on the `.details-consciousness-events` container after setting `detailsPanel.innerHTML`, rather than re-using the full interactive rendering from `consciousnessPane.ts`.

**Max-height adjustment:** Increase `detailsPanel` max-height from `300px` to `400px` to accommodate the third section without feeling cramped.

### Step 5 — Restructure `surfacedPanel` to two columns

**File:** `apps/cairn-tauri/src/cairnView.ts`, surfaced panel section (~line 90-142)

Change the panel width from `320px` to `800px`.

Replace the single `surfacedList` div with a two-column flex layout:

```
surfacedPanel (800px, flex-direction: column)
  surfacedHeader (unchanged — spans full width)
  surfacedColumns (flex: 1, display: flex, flex-direction: row, gap: 0, overflow: hidden)
    calendarColumn (flex: 1, display: flex, flex-direction: column, border-right: ...)
      columnHeader ("Calendar & Tasks")
      calendarList (flex: 1, overflow-y: auto, padding: 12px)
    emailColumn (flex: 1, display: flex, flex-direction: column)
      columnHeader ("Email")
      emailList (flex: 1, overflow-y: auto, padding: 12px)
```

### Step 6 — Update `updateSurfaced` to split by entity_type

**File:** `apps/cairn-tauri/src/cairnView.ts`, function `updateSurfaced` (~line 1349-1615)

Split `items` into two arrays at the top of the function:

```typescript
const calendarItems = items.filter(i => i.entity_type !== 'email');
const emailItems = items.filter(i => i.entity_type === 'email');
```

Replace `surfacedList.innerHTML = ''` with:

```typescript
calendarList.innerHTML = '';
emailList.innerHTML = '';
```

Render `calendarItems` into `calendarList` and `emailItems` into `emailList`.

The drag-and-drop state (`dragSourceIndex`) needs to be tracked per-column since DOM indices are now column-local. The simplest approach: create a `makeColumnDragHandlers(items, list, allItems)` closure that handles drag within a column and calls the same `kernelRequest('cairn/attention/reorder', ...)` with the full re-merged order. When a drop occurs within one column, the merged order is: take the current calendarItems order (possibly reordered) + current emailItems order (possibly reordered), interleaved by their original position priority — or more simply, concatenate calendar + email (the reorder RPC accepts any ordering and applies user_priority). This is a simplification: cross-column ordering is not supported.

The empty-state message should appear per-column when that column has zero items (e.g., "No email" if no email items exist).

The fingerprint must cover both columns — no change needed to the fingerprint computation since it hashes the full `items` array.

### Step 7 — Remove consciousness panel DOM and creation

**File:** `apps/cairn-tauri/src/cairnView.ts`

- Remove the `consciousnessContainer` element construction (~line 488-497)
- Remove the `createConsciousnessPane(consciousnessContainer)` call (~line 500)
- Remove the `consciousnessStyles` `<style>` block injection (~line 503-634) — **but keep the event type classes** if they are now used inline in the details panel. Move `EVENT_TYPE_CLASSES` and `EVENT_TYPE_ICONS` to module-level constants in `cairnView.ts` instead.
- Remove `container.appendChild(consciousnessContainer)` (~line 681)
- In `startConsciousnessPolling`: remove `consciousnessPane.clear()` call. Keep the polling logic itself — it still feeds `consciousnessEvents[]` which is now captured per-message.
- In `stopConsciousnessPolling`: remove `consciousnessPane.update(...)` call. The function can become a simple one-liner: `consciousnessPolling = false`.
- Remove the `import { createConsciousnessPane } from './consciousnessPane'` line.

**File:** `apps/cairn-tauri/src/consciousnessPane.ts`

This file becomes unreferenced. Do not delete it — it still contains useful `EVENT_TYPE_CLASSES` and `EVENT_TYPE_ICONS` constants and the `renderEvent` logic that may be extracted to a shared module later. Add a comment at the top:

```typescript
// NOTE: This component is no longer mounted in the main layout (as of the
// two-column attention panel redesign). Consciousness events are now captured
// per-message and rendered inside the "Show details" panel. This file is
// retained for reference and potential future use (e.g., a debug mode).
```

### Step 8 — Add CSS for the details consciousness section

**File:** `apps/cairn-tauri/src/cairnView.ts` (inline styles, consistent with existing approach)

The details panel uses inline `innerHTML` with inline styles, so no external CSS is needed. However, the column headers for the two-column layout should be added via the `<style>` tag already injected into `document.head` — add `.surfaced-column-header` class rules there.

---

## Files Affected

| File | Change |
|------|--------|
| `apps/cairn-tauri/src/cairnView.ts` | Primary file — all structural changes |
| `apps/cairn-tauri/src/consciousnessPane.ts` | Add deprecation comment; no functional changes |
| `apps/cairn-tauri/src/main.ts` | No changes needed |
| `apps/cairn-tauri/src/types.ts` | No changes needed — `ConsciousnessEvent` type already exists |
| `apps/cairn-tauri/src/style.css` | Optional: add column header styles if extracted from inline |

If the implementer chooses Alternative C (shared renderer module):

| File | Change |
|------|--------|
| `apps/cairn-tauri/src/consciousnessEventRenderer.ts` | New file — shared rendering logic |
| `apps/cairn-tauri/src/cairnView.ts` | Import from shared module |
| `apps/cairn-tauri/src/consciousnessPane.ts` | Import from shared module |

---

## Risks & Mitigations

### Risk 1: Defensive copy of `consciousnessEvents` is missed

**What goes wrong:** Without `[...consciousnessEvents]`, all previously rendered messages share a reference to the same array. When `startConsciousnessPolling` runs for the next message, it sets `consciousnessEvents = []` — overwriting the reference and clearing the events from all prior messages.

**Mitigation:** The spread copy in Step 2 is explicit and documented with a comment. A code reviewer should verify this specifically.

### Risk 2: Drag-and-drop breaks across the column split

**What goes wrong:** The existing DnD code uses a flat `dragSourceIndex` that counts into `items[]`. After the split, each column has its own index space. If the implementer reuses the old flat-index logic without adaptation, drops will target wrong items.

**Mitigation:** Step 6 specifies creating per-column drag handlers with column-local indices. The implementer must be careful not to mix index spaces. Testing: drag an item within the calendar column, drag an item within the email column, verify the reorder RPC is called with a sensible ordering.

### Risk 3: Consciousness events attached to messages before `hideThinking` completes

**What goes wrong:** `hideThinking()` is called at line 565 of `main.ts`, then `addAssistantMessage()` is called at line 570. This is sequential in a single `await`-resolved block, so there is no async gap. However, if `hideThinking` ever becomes async in the future, the snapshot could be taken before polling has fully stopped.

**Mitigation:** The current code is synchronous between `hideThinking` and `addAssistantMessage`. Document this ordering dependency with a comment in `main.ts`. The snapshot in `addAssistantMessage` reads `consciousnessEvents` which is the accumulated array at that point — even if polling fires one more time after `hideThinking` sets `consciousnessPolling = false` but before the interval clears, it would add to the array and the snapshot in `addAssistantMessage` would include it. This is correct behavior (more events is better than fewer).

### Risk 4: 800px attention panel feels too wide with few items

**What goes wrong:** If a user has 2 calendar items and 0 email items, the panel has one partially-filled column and one empty column. The empty column shows "No email" but the space feels wasteful.

**Mitigation:** This is a UX judgment call, not a technical risk. The panel was previously 320px and always felt cramped when items exist. The tradeoff favors the common case (items present). The empty-state message is informative. If the user finds it wasteful long-term, a future improvement could collapse an empty column to ~150px with a "no items" placeholder and give the space to the other column — but that is out of scope here.

### Risk 5: Details panel `max-height: 400px` is still not enough for messages with many consciousness events

**What goes wrong:** A complex query might generate 40+ consciousness events. At 22px per event row (collapsed), 40 events = 880px of content. The details panel is `overflow-y: auto` so it will scroll, but the initial view height of 400px means the user needs to scroll to see tool calls after consciousness events.

**Mitigation:** Render consciousness events collapsed by default (headlines only, no expanded content). Put the consciousness section last so thinking steps and tool calls are immediately visible. The section header shows the total event count (`X events`) so the user knows what is there. Optionally, cap the consciousness section to its own scrollable sub-container of `max-height: 200px` within the details panel.

---

## Testing Strategy

There are no automated frontend tests in this codebase (TypeScript/Tauri UI is tested manually). The following should be verified by the implementer before declaring complete:

### Layout
- [ ] At 1920x1080, the attention panel is 800px, chat fills the remaining ~840px, consciousness panel is absent
- [ ] Both columns scroll independently when their content exceeds the viewport height
- [ ] Column headers ("Calendar & Tasks" / "Email") are visible and legible
- [ ] With no items in either category, each column shows an appropriate empty state

### Consciousness in details
- [ ] After receiving an AI response that generated consciousness events, the "Show details" button appears on the message bubble
- [ ] Clicking "Show details" reveals three sections: Thinking Steps (if any), Tool Calls (if any), Consciousness Stream (if any)
- [ ] Consciousness Stream section shows the correct event count
- [ ] Events are rendered with the correct icon and headline
- [ ] Individual events can be expanded/collapsed to see content
- [ ] Sending a second message does not corrupt the consciousness events on the first message's details panel
- [ ] Messages with zero consciousness events do not show a Consciousness Stream section

### Drag and drop
- [ ] Items in the calendar column can be dragged and reordered within that column
- [ ] Items in the email column can be dragged and reordered within that column
- [ ] After drag, the `cairn/attention/reorder` RPC is called with a valid merged order

### Regression
- [ ] "Show details" still shows thinking steps and tool calls correctly (existing behavior unchanged)
- [ ] Click to open a scene in The Play still works from calendar column cards
- [ ] Click to open email still works from email column cards
- [ ] Act color labels still appear on calendar cards

---

## Definition of Done

- [ ] `cairnView.ts` no longer creates or appends `consciousnessContainer`
- [ ] `createConsciousnessPane` is no longer imported or called in `cairnView.ts`
- [ ] Consciousness polling loop still runs and accumulates events into `consciousnessEvents[]`
- [ ] `MessageData` interface includes `consciousnessEvents?: ConsciousnessEvent[]`
- [ ] `addAssistantMessage` snapshots consciousness events into `MessageData` with a defensive copy
- [ ] `renderChatMessage` includes a consciousness section in the details panel when events are present
- [ ] `surfacedPanel` is 800px wide with two independently-scrollable columns
- [ ] Calendar/task items render in the left column, email items in the right column
- [ ] Drag-and-drop operates correctly within each column
- [ ] `consciousnessPane.ts` has a deprecation comment and is otherwise untouched
- [ ] No changes to `main.ts`, `types.ts`, or any file outside `cairnView.ts` / `consciousnessPane.ts`
- [ ] All manual test cases above pass

---

## Confidence Assessment

**High confidence** on the structural changes (layout, column split, removing the consciousness panel DOM). The codebase is vanilla TypeScript with direct DOM manipulation; there are no reactive frameworks to worry about. The changes are localized to `cairnView.ts`.

**Medium confidence** on the per-message consciousness capture. The timing assumption — that `hideThinking` is called before `addAssistantMessage` and both are synchronous — holds today at `main.ts` lines 565/570. If that call order ever changes (e.g., if `hideThinking` is made async for an animation), the snapshot would need to move. This is a known fragility and is documented in Risk 3.

**One unvalidated assumption:** The drag-and-drop reorder RPC (`cairn/attention/reorder`) accepts any interleaved ordering of calendar and email entity IDs, not just pure calendar or pure email lists. The current codebase passes a mixed `ordered_entities` array (line 1546-1547 of `cairnView.ts`), which suggests the backend handles mixed entity types. If the backend actually groups by entity type before applying priority, cross-column ordering in the merged list won't matter. This should be verified by reading `src/cairn/cairn/mcp_tools.py` for the `cairn_attention_reorder` tool implementation before implementing Step 6.
