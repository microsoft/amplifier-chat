# Sub-Session Rendering Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Wire existing SSE sub-session events to render sub-agent activity inline within tool call cards, with recursive nesting, user-collapsible sections, and session navigation links.

**Architecture:** Separate `subSessionsRef` map (not nested state arrays) stores sub-session data. Event routing in `handleWsMessage` checks nesting context fields on every event and dispatches to sub-session or main session. `SubSessionView` component reads from the map and renders recursively.

**Tech Stack:** Preact + HTM (no build step), SSE via EventSource, all changes in `src/chat_plugin/static/index.html`

**Design doc:** `docs/plans/2026-03-09-sub-session-rendering-design.md`

---

## Task 1: Add Sub-Session Refs and State

**Files:**
- Modify: `src/chat_plugin/static/index.html:2729-2756` (refs block in ChatApp)

**Step 1: Add new refs after the existing refs block**

After line 2756 (`const autoDiskRefreshAtRef = useRef({});`), add:

```js
    // — Sub-session rendering —
    // Map<parentToolCallId, SubSession> — primary sub-session storage
    const subSessionsRef = useRef(new Map());
    // Map<parentToolCallId, Map<serverBlockIndex, localIndex>> — per-sub-session block index
    const subBlockMapRef = useRef(new Map());
    // Map<parentToolCallId, number> — next local block index per sub-session
    const subNextIndexRef = useRef(new Map());
    // Set<parentToolCallId> — user-collapsed sub-sessions
    const collapsedSubSessionsRef = useRef(new Set());
    // Revision counter to trigger re-renders when ref data changes
    const [subSessionRevision, setSubSessionRevision] = useState(0);
    // Throttle ref for rAF-based revision bumps during streaming
    const subSessionRafRef = useRef(null);
```

**Step 2: Add helper functions for sub-session state management**

Add these inside `ChatApp`, before `handleWsMessage` (before line 2924). These are the core mutation functions:

```js
    // — Sub-session helpers —
    function bumpSubSessionRevision() {
      if (subSessionRafRef.current) return;
      subSessionRafRef.current = requestAnimationFrame(() => {
        subSessionRafRef.current = null;
        setSubSessionRevision(r => r + 1);
      });
    }

    function createSubSession(parentToolCallId, sessionId, agent) {
      subSessionsRef.current.set(parentToolCallId, {
        sessionId,
        parentToolCallId,
        agent: agent || null,
        status: 'running',
        content: [],
        toolCalls: [],
        orderCounter: 0,
      });
      subBlockMapRef.current.set(parentToolCallId, new Map());
      subNextIndexRef.current.set(parentToolCallId, 0);
    }

    function getSubSession(parentToolCallId) {
      return subSessionsRef.current.get(parentToolCallId);
    }

    function resolveSubSessionKey(msg) {
      // Direct parent_tool_call_id
      if (msg.parent_tool_call_id && subSessionsRef.current.has(msg.parent_tool_call_id)) {
        return msg.parent_tool_call_id;
      }
      // Lookup via child_session_id
      if (msg.child_session_id) {
        const mapped = childToToolRef.current[msg.child_session_id];
        if (mapped && subSessionsRef.current.has(mapped)) return mapped;
      }
      return null;
    }

    function addSubSessionContent(parentToolCallId, item) {
      const sub = subSessionsRef.current.get(parentToolCallId);
      if (!sub) return;
      item.order = sub.orderCounter++;
      sub.content.push(item);
      bumpSubSessionRevision();
    }

    function updateSubSessionContent(parentToolCallId, updateFn) {
      const sub = subSessionsRef.current.get(parentToolCallId);
      if (!sub) return;
      updateFn(sub);
      bumpSubSessionRevision();
    }

    function addSubSessionToolCall(parentToolCallId, item) {
      const sub = subSessionsRef.current.get(parentToolCallId);
      if (!sub) return;
      item.order = sub.orderCounter++;
      sub.toolCalls.push(item);
      bumpSubSessionRevision();
    }

    function updateSubSessionToolCall(parentToolCallId, toolCallId, updateFn) {
      const sub = subSessionsRef.current.get(parentToolCallId);
      if (!sub) return;
      const tc = sub.toolCalls.find(t => t.toolCallId === toolCallId);
      if (tc) updateFn(tc);
      bumpSubSessionRevision();
    }

    function endSubSession(parentToolCallId, status) {
      const sub = subSessionsRef.current.get(parentToolCallId);
      if (!sub) return;
      sub.status = status;
      // Clean up per-sub-session tracking
      subBlockMapRef.current.delete(parentToolCallId);
      subNextIndexRef.current.delete(parentToolCallId);
      bumpSubSessionRevision();
    }
```

**Step 3: Verify no syntax errors**

Open the plugin in a browser (or run `python -m chat_plugin`) and confirm it loads without console errors. The new refs/functions are inert until wired up.

**Step 4: Commit**

```bash
git add src/chat_plugin/static/index.html
git commit -m "feat: add sub-session refs and helper functions"
```

---

## Task 2: Wire session_fork to Create Sub-Sessions

**Files:**
- Modify: `src/chat_plugin/static/index.html:3322-3330` (session_fork case in handleWsMessage)

**Step 1: Replace the session_fork handler**

Replace the existing `case 'session_fork'` block (lines 3322-3330) with:

```js
        case 'session_fork': {
          const childId = typeof msg.child_id === 'string' ? msg.child_id : null;
          applySessionForkLineage(msg);

          // Resolve parent tool call: direct ID or FIFO fallback
          let parentToolCallId = msg.parent_tool_call_id || null;
          let parentItemId = parentToolCallId ? toolMapRef.current[parentToolCallId] : null;

          if (!parentItemId) {
            // FIFO fallback: find oldest pending delegate/task without a sub-session
            const currentItems = chronoItemsRef.current;
            for (let i = 0; i < currentItems.length; i++) {
              const ci = currentItems[i];
              if (ci.type === 'tool_call'
                  && (ci.toolName === 'delegate' || ci.toolName === 'task')
                  && (ci.toolStatus === 'pending' || ci.toolStatus === 'running')
                  && !ci.subSessionId) {
                parentToolCallId = ci.toolCallId;
                parentItemId = ci.id;
                break;
              }
            }
          }

          if (!parentToolCallId || !parentItemId) break;

          // Store routing lookup
          if (childId) childToToolRef.current[childId] = parentToolCallId;

          // Create sub-session entry
          createSubSession(parentToolCallId, childId, msg.agent);

          // Set subSessionId on the parent tool call chrono item
          setChronoItems(prev => prev.map(item =>
            item.id === parentItemId
              ? { ...item, subSessionId: childId }
              : item
          ));
          break;
        }
```

**Step 2: Verify with a live session**

Start a session and send a prompt that triggers delegation (e.g. "use the explorer to survey this directory"). Confirm in browser DevTools that `subSessionsRef.current` has an entry after the fork event, and the tool call chrono item has `subSessionId` set.

**Step 3: Commit**

```bash
git commit -am "feat: wire session_fork to create sub-session entries"
```

---

## Task 3: Route Content Events to Sub-Sessions

**Files:**
- Modify: `src/chat_plugin/static/index.html:3117-3175` (content_start, content_delta, content_end cases)

**Step 1: Add sub-session routing guard to content_start**

At the very top of `case 'content_start'` (line 3117), before the placeholder removal, add:

```js
        case 'content_start': {
          // Sub-session routing check
          const subKey = resolveSubSessionKey(msg);
          if (subKey && (msg.nesting_depth ?? 0) > 0) {
            const blockMap = subBlockMapRef.current.get(subKey);
            const nextIdx = subNextIndexRef.current.get(subKey) || 0;
            subNextIndexRef.current.set(subKey, nextIdx + 1);
            if (blockMap) blockMap.set(msg.index, nextIdx);
            const itemId = makeId();
            // Register in blockMap for delta/end lookup
            if (blockMap) blockMap.set('id-' + nextIdx, itemId);
            if (msg.block_type === 'thinking' && blockMap) {
              blockMap.set('thinking-id-' + nextIdx, itemId);
            }
            addSubSessionContent(subKey, {
              id: itemId,
              type: msg.block_type === 'thinking' ? 'thinking' : 'text',
              content: '',
              streaming: true,
              role: 'assistant',
            });
            break;
          }

          // — existing content_start logic follows unchanged —
```

Keep all existing code after this guard block. The `break` inside the guard prevents fallthrough to main session handling.

**Step 2: Add sub-session routing guard to content_delta**

At the top of `case 'content_delta'` (line 3145), add:

```js
        case 'content_delta': {
          const delta = typeof msg.delta === 'string' ? msg.delta : '';
          if (!delta) break;

          // Sub-session routing check
          const subKey = resolveSubSessionKey(msg);
          if (subKey && (msg.nesting_depth ?? 0) > 0) {
            const blockMap = subBlockMapRef.current.get(subKey);
            const localIdx = blockMap ? blockMap.get(msg.index) : null;
            if (localIdx != null) {
              const textItemId = blockMap.get('id-' + localIdx);
              const thinkingItemId = blockMap.get('thinking-id-' + localIdx);
              const targetId = textItemId || thinkingItemId;
              if (targetId) {
                // Direct DOM mutation for streaming performance
                const el = document.getElementById(targetId);
                if (el) {
                  el.textContent += delta;
                } else {
                  updateSubSessionContent(subKey, sub => {
                    const block = sub.content.find(b => b.id === targetId);
                    if (block) block.content += delta;
                  });
                }
              }
            }
            break;
          }

          // — existing content_delta logic follows (remove duplicate delta extraction) —
```

Note: the existing `const delta = ...` line at 3146 should be removed since we moved it above the guard. Adjust so there's only one delta extraction.

**Step 3: Add sub-session routing guard to content_end**

At the top of `case 'content_end'` (line 3177), add:

```js
        case 'content_end': {
          // Sub-session routing check
          const subKey = resolveSubSessionKey(msg);
          if (subKey && (msg.nesting_depth ?? 0) > 0) {
            const blockMap = subBlockMapRef.current.get(subKey);
            const localIdx = blockMap ? blockMap.get(msg.index) : null;
            if (localIdx != null) {
              const textItemId = blockMap.get('id-' + localIdx);
              const thinkingItemId = blockMap.get('thinking-id-' + localIdx);
              const targetId = textItemId || thinkingItemId;
              const payloadText = typeof msg.text === 'string' ? msg.text : '';
              updateSubSessionContent(subKey, sub => {
                const block = sub.content.find(b => b.id === targetId);
                if (block) {
                  block.content = payloadText || block.content;
                  block.streaming = false;
                  if (block.type === 'text') {
                    block.htmlContent = sanitizeHtml(marked.parse(block.content));
                  }
                }
              });
            }
            break;
          }

          // — existing content_end logic follows unchanged —
```

**Step 4: Verify**

Trigger a delegation in a live session. Confirm sub-agent text content appears in `subSessionsRef` rather than in main `chronoItems`.

**Step 5: Commit**

```bash
git commit -am "feat: route content events to sub-sessions"
```

---

## Task 4: Route Thinking Events to Sub-Sessions

**Files:**
- Modify: `src/chat_plugin/static/index.html:3248-3265` (thinking_delta, thinking_final cases)

**Step 1: Add sub-session routing guard to thinking_delta**

At the top of `case 'thinking_delta'` (line 3248), add:

```js
        case 'thinking_delta': {
          // Sub-session routing check
          const subKey = resolveSubSessionKey(msg);
          if (subKey && (msg.nesting_depth ?? 0) > 0) {
            updateSubSessionContent(subKey, sub => {
              const block = sub.content.find(b => b.type === 'thinking' && b.streaming);
              if (block) block.content += msg.delta;
            });
            break;
          }

          // — existing thinking_delta logic follows unchanged —
```

**Step 2: Add sub-session routing guard to thinking_final**

At the top of `case 'thinking_final'` (line 3258), add:

```js
        case 'thinking_final': {
          // Sub-session routing check
          const subKey = resolveSubSessionKey(msg);
          if (subKey && (msg.nesting_depth ?? 0) > 0) {
            updateSubSessionContent(subKey, sub => {
              const block = sub.content.find(b => b.type === 'thinking' && b.streaming);
              if (block) {
                block.content = msg.content;
                block.streaming = false;
              }
            });
            break;
          }

          // — existing thinking_final logic follows unchanged —
```

**Step 3: Commit**

```bash
git commit -am "feat: route thinking events to sub-sessions"
```

---

## Task 5: Route Tool Events to Sub-Sessions

**Files:**
- Modify: `src/chat_plugin/static/index.html:3282-3320` (tool_call, tool_result cases)

**Step 1: Add sub-session routing guard to tool_call**

At the top of `case 'tool_call'` (line 3282), add:

```js
        case 'tool_call': {
          // Sub-session routing check
          const subKey = resolveSubSessionKey(msg);
          if (subKey && (msg.nesting_depth ?? 0) > 0) {
            const itemId = makeId();
            // Register in toolMapRef so deeper session_forks can resolve
            toolMapRef.current[msg.tool_call_id] = itemId;
            addSubSessionToolCall(subKey, {
              id: itemId,
              type: 'tool_call',
              toolName: msg.tool_name,
              toolCallId: msg.tool_call_id,
              arguments: msg.arguments || {},
              toolStatus: 'running',
              origin: 'sub-agent',
              subAgentName: null,
            });
            break;
          }

          // — existing tool_call logic follows unchanged —
```

**Step 2: Add sub-session routing guard to tool_result**

At the top of `case 'tool_result'` (line 3311), add:

```js
        case 'tool_result': {
          // Check if this result completes a sub-session
          const completedSubKey = msg.tool_call_id;
          if (subSessionsRef.current.has(completedSubKey)) {
            endSubSession(completedSubKey, msg.success ? 'complete' : 'error');
            // Still update the tool call item status in main chrono items
            const itemId = toolMapRef.current[msg.tool_call_id];
            cycleRef.current++;
            setChronoItems(prev => prev.map(item =>
              item.id === itemId
                ? { ...item, toolStatus: msg.success ? 'complete' : 'error', result: msg.output, resultError: msg.error }
                : item
            ));
            break;
          }

          // Check if this is a tool result for a tool INSIDE a sub-session
          const subKey = resolveSubSessionKey(msg);
          if (subKey && (msg.nesting_depth ?? 0) > 0) {
            updateSubSessionToolCall(subKey, msg.tool_call_id, tc => {
              tc.toolStatus = msg.success ? 'complete' : 'error';
              tc.result = msg.output;
              tc.resultError = msg.error;
            });
            break;
          }

          // — existing tool_result logic follows unchanged —
```

**Step 3: Verify end-to-end**

Trigger delegation. Confirm:
1. Sub-session is created on fork
2. Content streams into sub-session
3. Tool calls within sub-session appear in `subSession.toolCalls`
4. When delegation completes, sub-session status changes to `'complete'`

**Step 4: Commit**

```bash
git commit -am "feat: route tool events to sub-sessions and handle completion"
```

---

## Task 6: Pass Sub-Session Context Through normalizeKernelPayload

**Files:**
- Modify: `src/chat_plugin/static/index.html:1405-1465` (normalizeKernelPayload function)

**Step 1: Preserve sub-session fields**

At the end of `normalizeKernelPayload`, before the final `return p;`, add a block that ensures sub-session routing fields are always passed through from the raw kernel payload:

```js
    // Preserve sub-session routing fields from kernel events
    if (payload.child_session_id && !p.child_session_id) p.child_session_id = payload.child_session_id;
    if (payload.parent_tool_call_id && !p.parent_tool_call_id) p.parent_tool_call_id = payload.parent_tool_call_id;
    if (payload.nesting_depth != null && p.nesting_depth == null) p.nesting_depth = payload.nesting_depth;
```

This ensures the routing fields survive normalization for all event types.

**Step 2: Commit**

```bash
git commit -am "feat: preserve sub-session routing fields in normalizeKernelPayload"
```

---

## Task 7: Rewrite SubSessionView and Add NestedToolCallView

**Files:**
- Modify: `src/chat_plugin/static/index.html:2009-2058` (ToolCallCard and SubSessionView components)

**Step 1: Rewrite SubSessionView**

Replace the existing `SubSessionView` (lines 2053-2058) with:

```js
  function SubSessionView({ parentToolCallId, subSessionsRef, revision, depth = 0, onNavigate }) {
    const sub = subSessionsRef.current.get(parentToolCallId);
    if (!sub) return null;

    const [collapsed, setCollapsed] = useState(false);
    const statusIcon = sub.status === 'running' ? '\u27F3'
                     : sub.status === 'error' ? '\u2717' : '\u2713';
    const statusClass = sub.status === 'running' ? ' status-running' : '';

    // Merge content and toolCalls, sort by .order
    const allItems = [...sub.content, ...sub.toolCalls]
      .sort((a, b) => (a.order ?? 0) - (b.order ?? 0));

    return html`
      <div class="sub-session" style=${'--nesting-depth: ' + depth}>
        <div class="sub-session-header" onClick=${() => setCollapsed(c => !c)}>
          <span class=${'sub-session-status' + statusClass}>${statusIcon}</span>
          <span class="sub-session-agent">${sub.agent || 'sub-agent'}</span>
          ${onNavigate && sub.sessionId && html`
            <a class="sub-session-nav-link"
               onClick=${(e) => { e.stopPropagation(); onNavigate(sub.sessionId); }}
               title="Open this agent session">Open session \u2192</a>
          `}
          <span class="sub-session-chevron">${collapsed ? '\u25B6' : '\u25BC'}</span>
        </div>
        ${!collapsed && html`
          <div class="sub-session-body">
            ${allItems.map(item => {
              if (item.type === 'tool_call') {
                return html`<${NestedToolCallView}
                  item=${item}
                  subSessionsRef=${subSessionsRef}
                  revision=${revision}
                  depth=${depth + 1}
                  onNavigate=${onNavigate}
                />`;
              }
              return html`<${ChronoItem} item=${item} isActivity=${true} />`;
            })}
          </div>
        `}
      </div>
    `;
  }
```

**Step 2: Add NestedToolCallView**

Add this immediately after `SubSessionView`:

```js
  function NestedToolCallView({ item, subSessionsRef, revision, depth, onNavigate }) {
    const [expanded, setExpanded] = useState(false);
    const statusIcon = getToolStatusIcon(item.toolStatus);
    const isRunning = item.toolStatus === 'running';
    const argPreview = getArgPreview(item.toolName, item.arguments || {});
    const hasSubSession = subSessionsRef.current.has(item.toolCallId);

    return html`
      <div class="nested-tool-call">
        <div class="nested-tool-header" onClick=${() => setExpanded(e => !e)}>
          <span class=${'tool-status' + (isRunning ? ' status-running' : '')}>${statusIcon}</span>
          <span class="tool-name">${item.toolName || 'tool'}</span>
          <span class="tool-arg-preview">${argPreview}</span>
        </div>
        ${expanded && !hasSubSession && html`
          <div class="nested-tool-body">
            <pre class="tool-args-json">${JSON.stringify(item.arguments || {}, null, 2)}</pre>
            ${item.result && html`
              <div class=${'tool-result-text' + (item.resultError ? ' tool-error-text' : '')}>
                ${item.resultError || item.result || ''}
              </div>
            `}
          </div>
        `}
        ${hasSubSession && html`
          <${SubSessionView}
            parentToolCallId=${item.toolCallId}
            subSessionsRef=${subSessionsRef}
            revision=${revision}
            depth=${depth}
            onNavigate=${onNavigate}
          />
        `}
      </div>
    `;
  }
```

**Step 3: Update ToolCallCard to use new SubSessionView**

Replace the `SubSessionView` render in ToolCallCard (line 2046) and update the component to pass the new props. The key change is replacing `item.subItems` usage with the ref-based lookup:

In the ToolCallCard `expanded` block, replace:
```js
            ${item.subSessionId && html`<${SubSessionView} sessionId=${item.subSessionId} items=${item.subItems || []} />`}
```

With:
```js
            ${item.subSessionId && html`<${SubSessionView}
              parentToolCallId=${item.toolCallId}
              subSessionsRef=${subSessionsRef}
              revision=${subSessionRevision}
              depth=${0}
              onNavigate=${onNavigate}
            />`}
```

ToolCallCard needs `subSessionsRef`, `subSessionRevision`, and `onNavigate` as new props. Update its signature and the call site in `ChronoItem` to pass them through.

Also: when a sub-session exists, hide the args/result display (matching the spec):

```js
        ${expanded && html`
          <div class="tool-body">
            ${!item.subSessionId && html`
              <pre class="tool-args-json">${JSON.stringify(item.arguments || {}, null, 2)}</pre>
              ${item.result && html`
                <div class=${'tool-result-text' + (item.resultError ? ' tool-error-text' : '')}>\
                  ${item.resultError || item.result || ''}
                </div>
              `}
            `}
            ${item.subSessionId && html`<${SubSessionView} ... />`}
          </div>
        `}
```

**Step 4: Update ChronoItem to pass through sub-session props**

`ChronoItem` (line 2081) currently renders `ToolCallCard` without sub-session context. Add the props. The signature needs `subSessionsRef`, `subSessionRevision`, `onNavigate`, and forward them to `ToolCallCard`.

**Step 5: Update MessageList/ChatApp render to pass sub-session context**

Wherever `ChronoItem` is rendered (in `MessageList` and anywhere else), pass `subSessionsRef`, `subSessionRevision`, and `onNavigate` through.

**Step 6: Verify**

Trigger delegation. The sub-agent's streaming content, thinking blocks, and tool calls should render inside the parent tool card. Collapsing and expanding should work. Nested delegation (if available) should render recursively.

**Step 7: Commit**

```bash
git commit -am "feat: rewrite SubSessionView with recursive nesting and session navigation"
```

---

## Task 8: CSS Styling for Sub-Session Nesting

**Files:**
- Modify: `src/chat_plugin/static/index.html:899-906` (sub-session CSS)

**Step 1: Replace the existing `.sub-session` CSS block**

Replace lines 899-906 with expanded styles:

```css
    /* — Sub-Session ——————————————————————————————————————————— */
    .sub-session {
      background: rgba(255,255,255,0.02);
      border-left: 2px solid var(--border);
      margin-top: 6px;
      padding: 6px 0 6px 10px;
      font-size: 0.9em;
    }
    /* Progressive dimming for nested sub-sessions */
    .sub-session .sub-session {
      border-left-color: rgba(255,255,255,0.08);
      font-size: 0.95em; /* relative to parent, compounds */
    }
    .sub-session .sub-session .sub-session {
      border-left-color: rgba(255,255,255,0.05);
    }

    .sub-session-header {
      display: flex;
      align-items: center;
      gap: 6px;
      cursor: pointer;
      padding: 2px 0;
      font-size: 12px;
      color: var(--text-muted);
      user-select: none;
    }
    .sub-session-header:hover {
      color: var(--text-secondary);
    }
    .sub-session-status {
      font-size: 12px;
      display: inline-block;
    }
    .sub-session-agent {
      font-weight: 500;
      color: var(--accent, #7c8aff);
    }
    .sub-session-nav-link {
      font-size: 11px;
      color: var(--accent, #7c8aff);
      cursor: pointer;
      opacity: 0.7;
      margin-left: auto;
    }
    .sub-session-nav-link:hover {
      opacity: 1;
      text-decoration: underline;
    }
    .sub-session-chevron {
      font-size: 10px;
      margin-left: 4px;
      color: var(--text-muted);
    }
    .sub-session-body {
      padding-top: 4px;
    }
    .sub-session-body .text-block {
      color: var(--text-secondary);
      font-size: 0.95em;
    }
    .sub-session-body .thinking-block {
      font-size: 0.9em;
      opacity: 0.85;
    }

    /* Nested tool calls (inside sub-sessions) */
    .nested-tool-call {
      margin: 4px 0;
    }
    .nested-tool-header {
      display: flex;
      align-items: center;
      gap: 4px;
      font-size: 12px;
      color: var(--text-muted);
      cursor: pointer;
      padding: 2px 4px;
      border-radius: 3px;
    }
    .nested-tool-header:hover {
      background: rgba(255,255,255,0.04);
    }
    .nested-tool-body {
      padding: 4px 8px;
      font-size: 0.9em;
    }
    .nested-tool-body .tool-args-json {
      max-height: 120px;
      overflow: auto;
    }
    .nested-tool-body .tool-result-text {
      max-height: 120px;
      overflow: auto;
    }
```

**Step 2: Commit**

```bash
git commit -am "feat: add sub-session and nested tool call CSS styles"
```

---

## Task 9: Session Navigation ("Open Session" Link)

**Files:**
- Modify: `src/chat_plugin/static/index.html` (ChatApp, wherever session loading is triggered)

**Step 1: Create the `onNavigate` callback in ChatApp**

Inside `ChatApp`, create a function that loads a session by its ID. This should reuse the same logic used when a user clicks a `SessionCard`. Find the existing session-load function (likely tied to `SessionCard`'s `onClick` handler) and extract or call it:

```js
    const navigateToSession = useCallback((sessionId) => {
      // Find the session key that matches this sessionId
      for (const [key, session] of sessionsRef.current.entries()) {
        if (session && session.sessionId === sessionId) {
          // Use the same logic as SessionCard onClick
          setActiveKey(key);
          return;
        }
      }
      // Session not in sidebar yet — it may need to be loaded from disk
      // Trigger a history refresh, then activate
      // (implementation depends on existing session loading patterns)
    }, []);
```

Pass `navigateToSession` as `onNavigate` prop down to `ChronoItem` → `ToolCallCard` → `SubSessionView`.

**Step 2: Show parent session link when viewing a child session**

In the session metadata/header area of `ChatApp`, when the active session has a `parentSessionId`, render a link back:

```js
    ${activeSession.parentSessionId && html`
      <a class="parent-session-link"
         onClick=${() => navigateToSession(activeSession.parentSessionId)}>
        \u2190 Parent session
      </a>
    `}
```

**Step 3: Commit**

```bash
git commit -am "feat: add session navigation links in sub-session view"
```

---

## Task 10: Transcript Replay Reconstruction

**Files:**
- Modify: `src/chat_plugin/static/index.html:1783+` (transcriptToChronoItems function)

**Step 1: Reconstruct sub-sessions from saved transcripts**

The `transcriptToChronoItems` function (line 1783) builds chrono items from saved transcript data. It already reads `session_id`, `parent_id`, and `agent` from tool_use blocks (around lines 1869-1871).

Add a second pass after the existing logic that:

1. Identifies tool_use blocks with delegation metadata (tool name is `delegate` or `task`, and the transcript contains blocks from a child session)
2. Creates SubSession entries in `subSessionsRef`
3. Moves child content from main chrono items to the SubSession

```js
    // After transcriptToChronoItems returns items, reconstruct sub-sessions
    function reconstructSubSessions(items, subSessionsRef) {
      // Find delegation tool calls and their child session content
      const delegateTools = items.filter(i =>
        i.type === 'tool_call' &&
        (i.toolName === 'delegate' || i.toolName === 'task') &&
        i.originSessionId
      );

      for (const dt of delegateTools) {
        const childSessionId = dt.originSessionId;
        if (!childSessionId) continue;

        // Find content items that belong to this child session
        const childItems = items.filter(i =>
          i.originSessionId === childSessionId && i.id !== dt.id
        );
        if (childItems.length === 0) continue;

        // Create sub-session
        const parentToolCallId = dt.toolCallId;
        subSessionsRef.current.set(parentToolCallId, {
          sessionId: childSessionId,
          parentToolCallId,
          agent: dt.subAgentName || null,
          status: dt.toolStatus === 'error' ? 'error' : 'complete',
          content: childItems.filter(i => i.type !== 'tool_call'),
          toolCalls: childItems.filter(i => i.type === 'tool_call'),
          orderCounter: childItems.length,
        });

        // Set flag on parent tool call
        dt.subSessionId = childSessionId;
      }

      // Remove child items from main list
      const childSessionIds = new Set(delegateTools.map(d => d.originSessionId).filter(Boolean));
      return items.filter(i => !i.originSessionId || !childSessionIds.has(i.originSessionId) || i.type === 'tool_call' && delegateTools.includes(i));
    }
```

Call this function after `transcriptToChronoItems` returns, wherever transcript loading happens.

**Step 2: Verify**

Load a saved session that had delegation. Confirm the sub-session renders inline in the tool card rather than as flat items in the main timeline.

**Step 3: Commit**

```bash
git commit -am "feat: reconstruct sub-sessions from saved transcripts"
```

---

## Task 11: Reset Sub-Session State on Session Switch

**Files:**
- Modify: `src/chat_plugin/static/index.html` (wherever session state is reset on session switch)

**Step 1: Clear sub-session refs on session switch**

Find the session switch/reset logic in `ChatApp` (wherever `blockMapRef`, `toolMapRef`, etc. are reset). Add:

```js
    subSessionsRef.current = new Map();
    subBlockMapRef.current = new Map();
    subNextIndexRef.current = new Map();
    collapsedSubSessionsRef.current = new Set();
```

This ensures stale sub-session data from a previous session doesn't leak.

**Step 2: Cancel any pending rAF on unmount/switch**

In the cleanup path:

```js
    if (subSessionRafRef.current) {
      cancelAnimationFrame(subSessionRafRef.current);
      subSessionRafRef.current = null;
    }
```

**Step 3: Commit**

```bash
git commit -am "feat: reset sub-session state on session switch"
```

---

## Task 12: Final Integration Testing

**Step 1: Test live streaming**

1. Start a session, trigger delegation with a prompt like "use the explorer to survey this project"
2. Confirm: sub-agent activity appears inline in the tool card
3. Confirm: thinking blocks from sub-agent appear inside SubSessionView (not in parent)
4. Confirm: status icon updates from spinner to checkmark when complete
5. Confirm: collapse toggle works — clicking collapses, clicking again expands
6. Confirm: "Open session" link navigates to the child session

**Step 2: Test recursive nesting**

1. Trigger a prompt that causes a sub-agent to delegate further (e.g. a complex task using zen-architect that then delegates to modular-builder)
2. Confirm: the inner delegation renders as a nested SubSessionView inside the outer one

**Step 3: Test transcript replay**

1. Close and reopen a session that had delegation
2. Confirm: sub-session content appears inline in the tool card (not as flat items)

**Step 4: Test session switch**

1. Switch between sessions
2. Confirm: sub-session data from the previous session doesn't appear in the new one

**Step 5: Commit any fixes and push**

```bash
git push origin feat/sub-session-rendering
```
