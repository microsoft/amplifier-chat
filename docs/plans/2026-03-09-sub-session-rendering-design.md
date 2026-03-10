# Sub-Session Rendering Design

**Date:** 2026-03-09
**Branch:** `feat/sub-session-rendering`
**Scope:** UI-only — wire existing SSE events to render sub-agent activity inline within tool call cards.

## Context

The plugin already receives `delegate:agent_spawned` (mapped to `session_fork`) SSE events and has a `SubSessionView` component stub + `subSessionId`/`subItems` fields on the `ChronoItem` shape. None of this is wired up — the `session_fork` handler records lineage refs but never populates sub-session content, so the component never renders.

The `amplifier-web-spec` repo (`~/repo/amplifier-web-spec`) contains a complete implementation-ready specification for this feature in a React/WebSocket/Zustand architecture. This design adapts those patterns to this plugin's Preact/SSE/useState+useRef architecture.

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Sub-session data storage | Separate ref map (not nested state arrays) | Avoids deep immutable state updates; matches streaming perf pattern |
| Nesting depth | Recursive (depth-2+) | Sub-sessions within sub-sessions, flat map with implicit nesting in render tree |
| Default expand state | Expanded, user-collapsible | Full inline visibility of sub-agent work; user controls collapse |
| Collapse persistence | User's collapse state is respected | Status icon updates on tool card header regardless of collapse |
| Completed sub-sessions | Stay expanded (unless user collapsed) | No auto-collapse; only status icon changes (spinner to checkmark/X) |
| Session navigation | "Open session" link in SubSessionView header | Loads child session as standalone view; parent link shown in child's metadata |

## Data Model

### SubSession Object

```js
{
  sessionId: string,           // child session ID
  parentToolCallId: string,    // tool_call_id that spawned this
  agent: string | null,        // e.g. "foundation:explorer"
  status: 'running' | 'complete' | 'error',
  content: ChronoItem[],       // thinking + text blocks from child
  toolCalls: ChronoItem[],     // tool_call items from child
  orderCounter: number,        // monotonic counter for .order within this sub-session
}
```

### New Refs in ChatApp

```js
// Primary sub-session storage: Map<parentToolCallId, SubSession>
const subSessionsRef = useRef(new Map());

// Per-sub-session block index tracking: Map<parentToolCallId, Map<serverIndex, localIndex>>
const subBlockMapRef = useRef(new Map());

// Per-sub-session next index: Map<parentToolCallId, number>
const subNextIndexRef = useRef(new Map());

// Routing lookup: Map<childSessionId, parentToolCallId>
// (childToToolRef already exists, just needs to be used for routing)

// User collapse state: Set<parentToolCallId>
const collapsedSubSessionsRef = useRef(new Set());
```

### Re-render Mechanism

Sub-session data lives in refs for streaming performance. A revision counter triggers re-renders:

```js
const [subSessionRevision, setSubSessionRevision] = useState(0);
```

Bump is throttled to one `requestAnimationFrame` per frame during streaming to avoid thrashing.

### Recursive Nesting

All sub-sessions live in the same flat `subSessionsRef` map, keyed by `parentToolCallId`. Recursive nesting is implicit: a tool call inside `SubSession.toolCalls` can itself be a key in the map. When a grandchild `session_fork` arrives, its `parent_tool_call_id` points to the child's tool call — we create a new map entry for it. The render tree handles nesting: `SubSessionView` renders `NestedToolCallView`, which checks the map for its own `toolCallId` and renders another `SubSessionView` if found.

## Event Routing

All routing happens in `handleWsMessage`. The decision for every incoming event:

```
Has nesting context? (parent_tool_call_id OR child_session_id in childToToolRef)
  YES -> route to sub-session
  NO  -> route to main session (existing behavior)
```

### session_fork (delegate:agent_spawned)

1. Resolve `parentToolCallId`: use `msg.parent_tool_call_id` directly. If null, FIFO fallback — find oldest pending `delegate`/`task` tool call in `chronoItems` without a sub-session.
2. Store routing: `childToToolRef[msg.child_id] = parentToolCallId`
3. Create SubSession entry in `subSessionsRef`
4. Initialize per-sub-session tracking in `subBlockMapRef`, `subNextIndexRef`
5. Set `subSessionId = msg.child_id` on the matching tool call chrono item (flag for rendering)

### content_start / content_delta / content_end

1. Resolve `parentToolCallId` from event fields or `childToToolRef` lookup
2. If resolved and `nesting_depth > 0`: create/update content ChronoItem in `subSession.content`
3. If not resolved: route to main session as today
4. `content_delta` uses direct DOM mutation for streaming performance (same pattern as main session, with stable DOM IDs derived from `parentToolCallId + blockIndex`)

### thinking_delta / thinking_final

Same routing as content events. This fixes the known gap from the amplifier-web spec where thinking blocks from sub-agents leak into the parent message.

### tool_call / tool_result (nested)

1. Same routing check
2. `tool_call`: push to `subSession.toolCalls`, register `toolCallId` in `toolMapRef` so deeper `session_fork` events can resolve
3. `tool_result`: update matching tool call item status/result in the sub-session

### tool_result (for parent delegate/task)

When the result arrives for the tool call that spawned the sub-session:
1. Mark `subSession.status = 'complete'` (or `'error'` if failed)
2. Clean up per-sub-session tracking refs (`subBlockMapRef`, `subNextIndexRef`)
3. Do NOT remove the SubSession — it stays for display

## Component Tree

```
ToolCallCard (existing, modified)
  +-- Header: status icon + tool name + agent label + collapse chevron
  +-- [if not collapsed AND no subSessionId] Args/Result (existing)
  +-- [if not collapsed AND subSessionId] SubSessionView
        +-- Agent header:
        |     status icon (spinner/checkmark/X)
        |     "Agent: foundation:explorer"
        |     [Open session ->] link
        +-- Chronological items (content + toolCalls merged, sorted by .order):
        |   +-- ContentBlockView (text) -- muted, smaller
        |   +-- ContentBlockView (thinking) -- collapsible, muted
        |   +-- NestedToolCallView -- compact, expandable
        |         +-- [if this tool call has its own sub-session] SubSessionView (recursive)
        +-- [if status === 'error'] Error indicator
```

## Visual Treatment

### Nesting Indication

- Left border (`border-left: 2px solid`) + left margin per nesting depth
- Border color gets progressively lighter/more transparent with depth
- Nesting depth passed as prop, used for styling calculations

### Muted Styling

- Sub-session text: smaller font size, lower contrast than parent
- Tool calls inside sub-sessions: compact single-line rows, expandable
- Thinking blocks: collapsible with muted purple border (same as main, but smaller)

### Status Icons

On the ToolCallCard header (visible even when collapsed):
- Running: spinner
- Complete: checkmark
- Error: X mark

### Collapse Toggle

- Chevron on the SubSessionView agent header (not the ToolCallCard header)
- Click toggles collapse for that sub-session
- Collapse state stored in `collapsedSubSessionsRef` (Set of parentToolCallIds)
- Content hidden when collapsed; agent header + status always visible

## Session Navigation

### In SubSessionView Header

"Open session" link/button next to agent name. Clicking calls the existing session-load function (same as SessionCard click) with `subSession.sessionId`.

### In Child Session Metadata

When viewing a child session loaded via the link above, the session metadata area shows "Child of [parent session name]" as a clickable link back to the parent session.

### Data Available

- `subSession.sessionId` — for loading the child
- `session_history.py` already returns `parent_session_id` and `spawn_agent` metadata
- No new backend endpoints needed

## Transcript Replay

When loading a saved session via `transcriptToChronoItems`:

1. First pass: build all chrono items as today (existing behavior)
2. Second pass: identify tool_use blocks that spawned sub-sessions (have `agent` metadata or matching tool_result with `session_id` fields)
3. For each identified delegation: reconstruct a SubSession from the child's content blocks that arrived between the tool_call and tool_result
4. Populate `subSessionsRef` from reconstructed data
5. Set `subSessionId` on the parent tool call chrono items

This ensures sub-session nesting is visible both during live streaming and when loading history.

## Known Limitations (Accepted)

1. **Deep nesting gets narrow** — at depth 3+, left margins compress available width. Acceptable for now; deep delegation is rare in practice.
2. **No cross-session sub-session state** — collapse state is per-session-view, not persisted to disk. Reloading resets to expanded.
3. **FIFO fallback for session_fork** — when `parent_tool_call_id` is null, we match to the oldest pending delegate/task. Parallel delegations without IDs could mis-route. In practice, the daemon sends `parent_tool_call_id` reliably.

## Reference

- Spec: `~/repo/amplifier-web-spec/04-frontend.md` sections 4.6, 4.7, 5, 6.4
- Spec: `~/repo/amplifier-web-spec/02-protocol.md` sections 3.4, 6.3, 9
- Implementation reference: `~/repo/amplifier-web/frontend/src/components/Chat/MessageBubble.tsx`
- Implementation reference: `~/repo/amplifier-web/frontend/src/hooks/useWebSocket.ts`
