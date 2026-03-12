# Message Queue Design

## Goal

Allow users to queue messages while the assistant is processing, with queued messages draining sequentially via a 3-second countdown.

## Background

The amplifierd-plugin-chat frontend is a single-file Preact SPA (`static/index.html`, ~6,100 lines) built around a monolithic `ChatApp` component using `useState`/`useRef` hooks. Currently, when the assistant is processing a message, the input is fully disabled — the textarea is disabled, the send button becomes a Stop button — gated by a boolean `executing` flag. This means strictly one message in flight at a time. Users must wait for processing to complete before they can even type their next message, which disrupts conversational flow.

## Approach

**Per-session queue (Approach B)** — the queue is stored as a parallel `Map` keyed by session, persisting across session switches. This follows the existing `pendingEventsRef` pattern already established in the codebase: a `useRef` holds the mutable data structure and a version counter `useState` triggers re-renders when contents change. The queue is purely frontend — zero backend API changes required.

## Architecture

The queue system adds a thin layer between user input and `sendMessage()`. Instead of hard-blocking input during execution, `doSend()` conditionally routes messages into a per-session queue. A drain mechanism, triggered by processing-complete events, pops items and feeds them to `sendMessage()` with a countdown delay.

```
User Input
    │
    ▼
 doSend()
    │
    ├─ not executing ──► sendMessage() (direct, unchanged)
    │
    └─ executing ──► messageQueueRef.get(activeKey).push(item)
                          │
                          ▼
                     bump queueVersion (re-render)
                          │
                          ▼
                     QueuePanel shows item
                          │
          ┌───────────────┘
          ▼
  orchestrator:complete fires
          │
          ▼
  drain logic checks queue
          │
          ├─ empty or paused ──► idle
          │
          └─ has items ──► 3s countdown ──► sendMessage(next item)
```

## Components

### Data Model

**Queued message shape:**

```js
{
  id: string,          // crypto.randomUUID()
  content: string,     // message text
  images: string[],    // base64 image data
  queuedAt: number,    // Date.now()
}
```

### New State in ChatApp

| State | Type | Purpose |
|-------|------|---------|
| `messageQueueRef` | `useRef(new Map())` | `Map<sessionKey, QueuedMsg[]>` — per-session queue storage |
| `queueVersion` | `useState(0)` | Bump to trigger re-render when queue contents change |
| `queueDrainState` | `useRef(new Map())` | `Map<sessionKey, 'idle' \| 'countdown' \| 'paused'>` — per-session drain state |
| `countdownRef` | `useRef(null)` | Active `setTimeout` ID |
| `countdownRemaining` | `useState(null)` | Seconds left in countdown (drives timer UI), `null` when inactive |

The queue map is a ref (same pattern as `pendingEventsRef`). The `queueVersion` counter is the re-render trigger.

### Modified Send Flow

**Current `doSend()`:** `if (executing) return;` — hard block.

**New `doSend()`:**

- If `executing` or drain state is `countdown`: push `{id, content, images, queuedAt}` into `messageQueueRef` for `activeKey`, bump `queueVersion`, clear textarea, return.
- Else: send normally via `sendMessage()`.

Textarea stays enabled during processing. Placeholder changes from `"Processing..."` to `"Queue a message..."` when executing. Send button stays visible (not replaced by Stop). Stop button becomes a separate element — always visible during execution, independent of send button.

### Auto-Drain with Countdown

When `orchestrator:complete` fires (or `cancel:completed`, `execution_error`):

1. `setExecuting(false)`
2. Check `messageQueueRef` for active session
3. If queue is empty OR drain state is `paused` → done
4. If queue has items:
   a. Set drain state to `countdown`
   b. Start 3-second countdown (update `countdownRemaining` each second)
   c. On countdown complete: pop first item from queue, bump `queueVersion`, set drain state to `idle`, call `sendMessage(item.content, item.images)`

If the user removes the countdown item via X during countdown, cancel the timer and check for next item. If queue is now empty, return to idle.

### Stop Behavior

When the user hits Stop:

1. `POST /sessions/{id}/cancel` (existing behavior)
2. Set drain state to `paused` for this session
3. Cancel any active countdown timer
4. Queue items remain visible in the panel

Queue panel shows a **Resume** button when paused. Tapping it:

1. Set drain state to `idle`
2. Start the 3-second countdown for the next item

If user types and sends a new message while paused:

1. New message sends immediately (normal `sendMessage` flow)
2. Queue stays paused — doesn't auto-resume
3. User must explicitly tap Resume to drain remaining items

### QueuePanel Component

Renders between the message list and `InputArea`. Only visible when the queue for the active session has items.

**Layout:**

```
 ┌─────────────────────────────────────────────┐
 │  Chat messages (scrollable)                  │
 ├─────────────────────────────────────────────┤
 │  Queue Panel (max-height, scrollable)        │
 │  ┌─────────────────────────────────────┐    │
 │  │ "Your message content..."       [X] │    │
 │  │ "Another queued msg..."         [X] │    │
 │  │ "Next up (sending in 3s)"   [Cancel]│    │
 │  └─────────────────────────────────────┘    │
 │  [Resume queue (2 remaining)]  <- if paused │
 ├─────────────────────────────────────────────┤
 │  InputArea (textarea + Send + Stop)          │
 └─────────────────────────────────────────────┘
```

**Responsive behavior:**

- `max-height` capped — `30vh` on desktop, `25vh` on mobile (via media query or `clamp`)
- `overflow-y: scroll` when items exceed max-height
- Touch targets: X buttons and Resume at minimum 44×44px tap area
- Items truncate long messages with ellipsis (single line)
- On very small viewports (<380px), queue items compact further

**Countdown item styling:**

- Distinct visual treatment — subtle progress bar or pulsing border
- Shows "Sending in 3s..." that counts down
- X button cancels timer and removes item

**Paused state:**

- Queue items shown with muted/dimmed style
- "Resume queue (N remaining)" full-width button at bottom

### Sidebar Badge

When a session has queued messages, the sidebar entry shows a small count badge. Derived at render time from the queue ref + version counter. No changes to `SessionState` shape.

## Data Flow

1. **Enqueue:** User presses Enter/Send while `executing` → `doSend()` creates `QueuedMsg`, pushes to `messageQueueRef.get(activeKey)`, bumps `queueVersion` → `QueuePanel` re-renders showing the item.

2. **Drain trigger:** SSE delivers `orchestrator:complete` / `cancel:completed` / `execution_error` → handler sets `executing = false` → drain logic inspects queue for active session.

3. **Countdown:** Drain logic sets drain state to `countdown`, starts 3-second timer updating `countdownRemaining` each second → `QueuePanel` shows countdown on the next item.

4. **Send:** Timer completes → pops first item → calls `sendMessage(content, images)` → sets `executing = true` → cycle repeats when next complete event fires.

5. **Cancellation:** User taps X on countdown item → `clearTimeout(countdownRef.current)` → item removed → drain logic checks for next item or returns to idle.

6. **Stop:** User taps Stop → cancellation request sent → drain state set to `paused` → countdown cancelled → queue items remain → Resume button appears.

## Session Lifecycle Integration

| Event | Queue Behavior |
|-------|---------------|
| Switch away from session | Queue persists in map, countdown cancelled if active |
| Switch back to session | Queue restored, drain state restored. If was `countdown`, restart countdown |
| Delete/close session | Remove entry from `messageQueueRef` and `queueDrainState` |
| New session created | No queue initially (empty) |
| History session (read-only) | Queue disabled — `doSend` still blocked for history sessions |

## Error Handling

- **SSE disconnect during processing:** Queue drain won't fire since it depends on `orchestrator:complete`. The Stop button is the user's escape hatch. Queue items remain visible and can be manually removed.
- **Rapid typing:** Each Enter press pushes to queue. No debounce needed — each push is a simple array append + counter bump.
- **Images in queued messages:** Captured at queue time (base64). Queue items show an `[image]` indicator for v1. Image data is retained in the queued message object until drain sends it.
- **Slash commands while queued:** Bypass queue entirely, execute immediately.

## Testing Strategy

- **Unit-level validation:** Verify `doSend()` routes to queue when `executing` is true and sends directly when false. Verify queue CRUD operations (push, remove, clear on session delete).
- **Drain logic:** Verify countdown starts on `orchestrator:complete`, verify countdown fires `sendMessage` with correct item, verify Stop pauses drain, verify Resume restarts countdown.
- **Session switching:** Verify queue persists when switching away and restores when switching back. Verify countdown cancels on switch-away and restarts on switch-back.
- **QueuePanel rendering:** Verify panel appears when queue is non-empty and hides when empty. Verify countdown item has distinct styling. Verify paused state shows Resume button with correct count.
- **Edge cases:** Removing the countdown item mid-countdown, stopping during countdown, sending a manual message while paused, deleting a session with active queue.

## Scope Boundaries

The following are explicitly **unchanged** by this feature:

- **Backend API** — zero changes, queue is purely frontend
- **`sendMessage()` internals** — same function, called from drain logic
- **SSE event handling** — no changes to event parsing or routing
- **`chronoItems` rendering** — no changes to message display
- **`pendingEventsRef`** (background session event queue) — untouched

## Open Questions

None — design is fully validated.
