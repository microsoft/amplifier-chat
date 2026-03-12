# Message Queue Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow users to queue messages while the assistant is processing, display them in an in-place panel above the input area, and auto-drain them sequentially with a 3-second countdown.

**Architecture:** Per-session queue stored as `Map<sessionKey, QueuedMsg[]>` via `useRef` (mirrors the existing `pendingEventsRef` pattern). A `queueVersion` useState counter triggers re-renders when the queue changes. Drain logic uses `setTimeout` with a 3-second countdown, paused by Stop and resumed by a Resume button. A new `QueuePanel` component renders between `MessageList` and `InputArea`.

**Tech Stack:** Preact (via CDN), htm tagged templates (no JSX, no bundler), inline `<style>` CSS, manual browser testing.

**Single file:** `src/chat_plugin/static/index.html` (~6,113 lines). All changes are to this one file.

---

## File Structure

All modifications target a single file:

- **Modify:** `src/chat_plugin/static/index.html`
  - CSS section (~line 1244): Add QueuePanel styles
  - CSS section (~line 410): Add queue-count badge styles
  - State declarations (~line 3510): Add queue refs and state
  - New helper functions (after state declarations): Queue manipulation helpers
  - New helper functions: Countdown/drain logic
  - `InputArea` component (~line 3212): Modify props, doSend, textarea, buttons
  - New `QueuePanel` component (before `ChatApp`)
  - `ChatApp` main layout (~line 6073): Wire QueuePanel between MessageList and InputArea
  - SSE handlers (~lines 4426, 4456, 4476): Wire drain triggers
  - `sendMessage` error catch (~line 5142): Wire drain trigger
  - `stopExecution` (~line 5146): Add queue pause logic
  - `switchSession` (~line 5531): Handle countdown on switch
  - `newSession` (~line 5178): Clear queue for new session
  - `SessionCard` render (~line 3200): Add queue count badge

---

## Chunk 1: Queue State Infrastructure

### Task 1: Add queue state declarations

**File:** `src/chat_plugin/static/index.html:3503-3510`

Add new refs and state variables for the message queue, immediately after the existing `autoDiskRefreshAtRef` ref (line 3503) and before the sub-session block (line 3505).

- [ ] **Step 1: Add queue refs and state**

Find the block at lines 3503-3504:

```javascript
    const autoDiskRefreshAtRef = useRef({});

    // — Sub-session rendering —
```

Insert the queue state between them:

```javascript
    const autoDiskRefreshAtRef = useRef({});

    // — Message queue —
    // Map<sessionKey, Array<{ id: string, content: string, images: string[], queuedAt: number }>>
    const msgQueueRef = useRef(new Map());
    // Re-render trigger — bump this counter whenever the queue changes
    const [queueVersion, setQueueVersion] = useState(0);
    // Map<sessionKey, 'idle' | 'countdown' | 'paused'>
    const queueDrainStateRef = useRef(new Map());
    // Active setTimeout ID for the countdown
    const countdownTimerRef = useRef(null);
    // Seconds remaining in the active countdown (drives UI); null when no countdown is active
    const [countdownRemaining, setCountdownRemaining] = useState(null);

    // — Sub-session rendering —
```

- [ ] **Step 2: Verify — check for syntax errors**

Open the browser, load the chat UI. The page should render exactly as before with no console errors. Open DevTools Console and confirm no red errors.

- [ ] **Step 3: Commit**

```bash
cd /Users/samule/repo/amplifierd-plugin-chat/.worktrees/message-queue
git add src/chat_plugin/static/index.html
git commit -m "feat(queue): add queue state declarations (refs + useState)"
```

---

### Task 2: Add queue helper functions

**File:** `src/chat_plugin/static/index.html` — insert immediately after `resetSubSessionState()` function (which ends around line 3517) and before the next function.

These are plain helpers that operate on the refs. They live inside `ChatApp()` so they close over the refs.

- [ ] **Step 1: Add helper functions**

Find the end of `resetSubSessionState`:

```javascript
    function resetSubSessionState() {
      subSessionsRef.current = new Map();
      subBlockMapRef.current = new Map();
      subNextIndexRef.current = new Map();
      if (subSessionRafRef.current) { cancelAnimationFrame(subSessionRafRef.current); subSessionRafRef.current = null; }
```

After the closing `}` of `resetSubSessionState`, insert:

```javascript

    // — Message queue helpers —
    // Returns Array<{ id, content, images, queuedAt }> for the given (or active) session key
    function getQueue(key) {
      return msgQueueRef.current.get(key || activeKeyRef.current) || [];
    }

    // Accepts (content: string, images: string[]) — images are base64 strings (no data-URL prefix)
    function pushToQueue(content, images) {
      const key = activeKeyRef.current;
      if (!key) return;
      const queue = msgQueueRef.current.get(key) || [];
      queue.push({ id: makeId(), content, images: images || [], queuedAt: Date.now() });
      msgQueueRef.current.set(key, queue);
      setQueueVersion(v => v + 1);
    }

    // Removes the item with the given id from the active session's queue
    function removeFromQueue(msgId) {
      const key = activeKeyRef.current;
      if (!key) return;
      const queue = (msgQueueRef.current.get(key) || []).filter(m => m.id !== msgId);
      if (queue.length === 0) {
        msgQueueRef.current.delete(key);
      } else {
        msgQueueRef.current.set(key, queue);
      }
      setQueueVersion(v => v + 1);
    }

    // Clears all queued items for the given (or active) session key
    function clearSessionQueue(key) {
      msgQueueRef.current.delete(key || activeKeyRef.current);
      setQueueVersion(v => v + 1);
    }

    function getQueueDrainState(key) {
      return queueDrainStateRef.current.get(key || activeKeyRef.current) || 'idle';
    }

    function setQueueDrainState(state, key) {
      queueDrainStateRef.current.set(key || activeKeyRef.current, state);
      // Force re-render so QueuePanel picks up the new state
      setQueueVersion(v => v + 1);
    }
```

- [ ] **Step 2: Verify — page loads without errors**

Reload the browser. The page should render identically. Open DevTools Console — no errors.

- [ ] **Step 3: Commit**

```bash
cd /Users/samule/repo/amplifierd-plugin-chat/.worktrees/message-queue
git add src/chat_plugin/static/index.html
git commit -m "feat(queue): add queue helper functions"
```

---

## Chunk 2: InputArea Modifications

### Task 3: Pass new props to InputArea

**File:** `src/chat_plugin/static/index.html`

We need to pass queue-related props down to `InputArea` so it can route messages to the queue during execution.

- [ ] **Step 1: Update InputArea function signature**

Find the InputArea signature at line 3212:

```javascript
  function InputArea({ onSend, onStop, executing, viewMode, setViewMode, activeKey }) {
```

Replace with:

```javascript
  function InputArea({ onSend, onStop, onQueueMessage, executing, shouldQueue, queueCount, viewMode, setViewMode, activeKey }) {
```

> **Note:** `shouldQueue` is `true` when messages should be routed to the queue (`executing || getQueueDrainState() === 'countdown'`). It is distinct from `executing`, which is still needed to control Stop button visibility. See Issue 4.

- [ ] **Step 2: Update InputArea usage in main layout**

Find the InputArea render at lines 6074-6081:

```javascript
            <${InputArea}
              onSend=${sendMessage}
              onStop=${stopExecution}
              executing=${executing}
              viewMode=${viewMode}
              setViewMode=${setViewMode}
              activeKey=${activeKey}
            />
```

Replace with:

```javascript
            <${InputArea}
              onSend=${sendMessage}
              onStop=${stopExecution}
              onQueueMessage=${pushToQueue}
              executing=${executing}
              shouldQueue=${executing || getQueueDrainState() === 'countdown'}
              queueCount=${getQueue().length}
              viewMode=${viewMode}
              setViewMode=${setViewMode}
              activeKey=${activeKey}
            />
```

- [ ] **Step 3: Verify — page loads, InputArea renders normally**

Reload. The input area should look and behave identically — type a message, send it, no errors.

- [ ] **Step 4: Commit**

```bash
cd /Users/samule/repo/amplifierd-plugin-chat/.worktrees/message-queue
git add src/chat_plugin/static/index.html
git commit -m "feat(queue): pass queue props to InputArea"
```

---

### Task 4: Modify doSend() to route to queue when executing

**File:** `src/chat_plugin/static/index.html:3260-3274`

When `shouldQueue` is true (i.e. `executing || drainState === 'countdown'`), instead of returning early, route the message to the queue. Slash commands always bypass the queue. Images are passed through when queuing.

- [ ] **Step 1: Update doSend**

Find the existing `doSend` at lines 3260-3274:

```javascript
    const doSend = useCallback(() => {
      if (executing) return;  // Guard against double-send
      const ta = textareaRef.current;
      if (!ta) return;
      const content = ta.value.trim();
      if (!content && pendingImages.length === 0) return;

      // Strip data URL prefix from images
      const images = pendingImages.map(d => d.split(',')[1]);
      onSend(content, images);
      ta.value = '';
      ta.style.height = 'auto';
      setPendingImages([]);
      setSlashOpen(false);
    }, [onSend, pendingImages, executing]);
```

Replace with:

```javascript
    const doSend = useCallback(() => {
      const ta = textareaRef.current;
      if (!ta) return;
      const content = ta.value.trim();
      if (!content && pendingImages.length === 0) return;

      // Slash commands always bypass the queue and send directly
      if (shouldQueue && !content.startsWith('/')) {
        // Route to queue instead of sending directly; include any attached images
        if (content || pendingImages.length > 0) {
          onQueueMessage(content, pendingImages.map(d => d.split(',')[1]));
          ta.value = '';
          ta.style.height = 'auto';
          setPendingImages([]);
          setSlashOpen(false);
        }
        return;
      }

      // Strip data URL prefix from images
      const images = pendingImages.map(d => d.split(',')[1]);
      onSend(content, images);
      ta.value = '';
      ta.style.height = 'auto';
      setPendingImages([]);
      setSlashOpen(false);
    }, [onSend, onQueueMessage, pendingImages, executing, shouldQueue]);
```

- [ ] **Step 2: Verify — queue routing works**

1. Open the chat UI, start a session.
2. Send a message to begin execution (assistant starts processing).
3. While the assistant is processing, type another message and press Enter.
4. Open DevTools Console and type: `// No errors should be present`
5. The textarea should clear (message was accepted), but nothing is sent yet — the message went to the queue ref. You can't see it in the UI yet (QueuePanel comes later).
6. The assistant should continue processing normally.

- [ ] **Step 3: Commit**

```bash
cd /Users/samule/repo/amplifierd-plugin-chat/.worktrees/message-queue
git add src/chat_plugin/static/index.html
git commit -m "feat(queue): route messages to queue when executing"
```

---

### Task 5: Update textarea to stay enabled during execution

**File:** `src/chat_plugin/static/index.html:3385-3391`

The textarea should remain enabled during execution so users can type queued messages. The placeholder changes to indicate queuing mode.

- [ ] **Step 1: Update textarea props**

Find the textarea at lines 3385-3391:

```javascript
          <textarea
            id="message-input"
            ref=${textareaRef}
            placeholder=${executing ? "Processing\u2026" : "Message\u2026 (/ for commands)"}
            rows="1"
            disabled=${executing}
            style=${{ opacity: executing ? 0.6 : 1 }}
```

Replace with:

```javascript
          <textarea
            id="message-input"
            ref=${textareaRef}
            placeholder=${executing ? "Queue a message\u2026" : "Message\u2026 (/ for commands)"}
            rows="1"
            disabled=${false}
            style=${{ opacity: 1 }}
```

- [ ] **Step 2: Update the focus effect to remove disabled check**

Find the focus effect at lines 3220-3229:

```javascript
    useEffect(() => {
      const ta = textareaRef.current;
      if (!ta || ta.disabled) return;
      const rafId = window.requestAnimationFrame(() => {
        try {
          ta.focus();
        } catch {}
      });
      return () => window.cancelAnimationFrame(rafId);
    }, [activeKey]);
```

Replace with:

```javascript
    useEffect(() => {
      const ta = textareaRef.current;
      if (!ta) return;
      const rafId = window.requestAnimationFrame(() => {
        try {
          ta.focus();
        } catch {}
      });
      return () => window.cancelAnimationFrame(rafId);
    }, [activeKey]);
```

- [ ] **Step 3: Verify — textarea stays enabled during execution**

1. Send a message to start processing.
2. While the assistant is processing, the textarea should show placeholder "Queue a message..." and be fully interactive (not grayed out, not disabled).
3. You should be able to type in it and press Enter to queue messages.

- [ ] **Step 4: Commit**

```bash
cd /Users/samule/repo/amplifierd-plugin-chat/.worktrees/message-queue
git add src/chat_plugin/static/index.html
git commit -m "feat(queue): keep textarea enabled during execution with queue placeholder"
```

---

### Task 6: Show both Send and Stop buttons during execution

**File:** `src/chat_plugin/static/index.html:3407-3410`

Currently the Send and Stop buttons are toggled — only one shows at a time. We need both visible during execution so the user can queue messages (Send) and also stop the assistant (Stop).

- [ ] **Step 1: Replace the button toggle with both-visible pattern**

Find the button toggle at lines 3407-3410:

```javascript
          ${executing
            ? html`<button class="input-btn stop-btn" onClick=${onStop}>■ Stop</button>`
            : html`<button class="input-btn send-btn" onClick=${doSend}>Send</button>`
          }
```

Replace with:

```javascript
          <button class="input-btn send-btn" onClick=${doSend}>
            ${executing ? 'Queue' : 'Send'}
          </button>
          ${executing && html`
            <button class="input-btn stop-btn" onClick=${onStop}>\u25a0 Stop</button>
          `}
```

- [ ] **Step 2: Verify — both buttons visible during execution**

1. Send a message to start processing.
2. While the assistant is processing, you should see **both** a "Queue" button (blue) and a "■ Stop" button (red) in the input row.
3. When idle (not executing), only the "Send" button should appear.
4. Click "Queue" — the textarea text should be queued (textarea clears).
5. Click "■ Stop" — the assistant should stop.

- [ ] **Step 3: Commit**

```bash
cd /Users/samule/repo/amplifierd-plugin-chat/.worktrees/message-queue
git add src/chat_plugin/static/index.html
git commit -m "feat(queue): show both Send/Queue and Stop buttons during execution"
```

---

## Chunk 3: QueuePanel Component + CSS

### Task 7: Add QueuePanel CSS

**File:** `src/chat_plugin/static/index.html` — insert after the `.stop-btn` rule (line 1243) and before the `.attach-btn` rule (line 1244).

- [ ] **Step 1: Add CSS rules**

Find line 1243-1244:

```css
    .stop-btn { background: var(--accent-red); color: white; }
    .attach-btn { background: var(--bg-tertiary); border: 1px solid var(--border); color: var(--text-secondary); }
```

Insert between them:

```css
    .stop-btn { background: var(--accent-red); color: white; }

    /* —— Queue Panel ———————————————————————————————————————— */
    .queue-panel {
      border-top: 1px solid var(--border);
      background: var(--bg-secondary);
      padding: 8px 16px;
      flex-shrink: 0;
      max-height: 30vh; /* responsive; avoids eating the whole viewport on short screens */
      overflow-y: auto;
    }
    @media (max-width: 768px) {
      .queue-panel { max-height: 25vh; }
    }
    .queue-panel-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 6px;
      font-size: 12px;
      color: var(--text-secondary);
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.03em;
    }
    .queue-panel-header-actions {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .queue-countdown {
      font-variant-numeric: tabular-nums;
      color: var(--accent-blue);
      font-weight: 700;
      font-size: 13px;
      min-width: 24px;
      text-align: center;
    }
    .queue-panel-btn {
      background: none;
      border: 1px solid var(--border);
      border-radius: 4px;
      color: var(--text-secondary);
      font-size: 11px;
      padding: 2px 8px;
      cursor: pointer;
      line-height: 1.4;
      min-height: 44px; /* 44px minimum touch target for accessibility */
    }
    .queue-panel-btn:hover {
      background: var(--bg-tertiary);
      color: var(--text-primary);
    }
    .queue-panel-btn.resume {
      border-color: var(--accent-blue);
      color: var(--accent-blue);
    }
    .queue-panel-btn.resume:hover {
      background: rgba(59, 130, 246, 0.1);
    }
    .queue-panel-btn.clear-all {
      border-color: var(--accent-red);
      color: var(--accent-red);
    }
    .queue-panel-btn.clear-all:hover {
      background: rgba(239, 68, 68, 0.1);
    }
    .queue-item {
      display: flex;
      align-items: flex-start;
      gap: 8px;
      padding: 4px 0;
      font-size: 13px;
      color: var(--text-primary);
      border-bottom: 1px solid var(--border);
    }
    .queue-item:last-child { border-bottom: none; }
    .queue-item-number {
      flex-shrink: 0;
      width: 18px;
      height: 18px;
      border-radius: 50%;
      background: var(--bg-tertiary);
      color: var(--text-secondary);
      font-size: 10px;
      font-weight: 600;
      display: flex;
      align-items: center;
      justify-content: center;
      margin-top: 1px;
    }
    .queue-item-text {
      flex: 1;
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .queue-item-remove {
      flex-shrink: 0;
      /* 44px minimum touch target for accessibility; visual circle stays small via flex centering */
      min-width: 44px;
      min-height: 44px;
      border: none;
      background: none;
      color: var(--text-secondary);
      font-size: 14px;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      border-radius: 4px;
      padding: 0;
    }
    .queue-item-remove:hover {
      background: var(--bg-tertiary);
      color: var(--accent-red);
    }
    /* Countdown item gets a pulsing left-border to signal it's about to be sent */
    @keyframes pulse-border {
      0%, 100% { border-left-color: var(--accent-blue); }
      50%       { border-left-color: transparent; }
    }
    .queue-item--countdown {
      border-left: 3px solid var(--accent-blue);
      padding-left: 6px;
      animation: pulse-border 1s ease-in-out infinite;
    }
    .queue-item-countdown-label {
      font-size: 11px;
      color: var(--accent-blue);
      font-weight: 600;
      white-space: nowrap;
      margin-left: 4px;
    }
    .queue-item-image {
      font-size: 11px;
      color: var(--text-secondary);
      background: var(--bg-tertiary);
      border-radius: 3px;
      padding: 1px 4px;
      margin-left: 4px;
      white-space: nowrap;
    }
    .queue-paused-label {
      font-size: 11px;
      color: var(--accent-amber);
      font-weight: 600;
    }

    /* —— Queue count badge for sidebar ————————————————————— */
    .queue-count-badge {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 16px;
      height: 16px;
      padding: 0 4px;
      border-radius: 999px;
      background: var(--accent-blue);
      color: white;
      font-size: 10px;
      font-weight: 700;
      line-height: 1;
    }

    .attach-btn { background: var(--bg-tertiary); border: 1px solid var(--border); color: var(--text-secondary); }
```

- [ ] **Step 2: Verify — no visual regressions**

Reload the browser. Everything should look identical — the new CSS classes are defined but not yet used.

- [ ] **Step 3: Commit**

```bash
cd /Users/samule/repo/amplifierd-plugin-chat/.worktrees/message-queue
git add src/chat_plugin/static/index.html
git commit -m "feat(queue): add QueuePanel and badge CSS"
```

---

### Task 8: Build QueuePanel component

**File:** `src/chat_plugin/static/index.html` — insert immediately before the `InputArea` function (line 3212).

The QueuePanel is a standalone component that receives its data via props.

- [ ] **Step 1: Add QueuePanel component**

Find line 3212:

```javascript
  function InputArea({ onSend, onStop, executing, viewMode, setViewMode, activeKey }) {
```

Insert before it:

```javascript
  function QueuePanel({ queue, drainState, countdownSecs, onRemove, onClearAll, onResume }) {
    if (queue.length === 0) return null;

    return html`
      <div class="queue-panel" role="region" aria-label="Message queue">
        <div class="queue-panel-header">
          <span>Queued (${queue.length})</span>
          <div class="queue-panel-header-actions">
            ${drainState === 'countdown' && countdownSecs !== null && html`
              <span class="queue-countdown" aria-live="polite">
                ${countdownSecs}s
              </span>
            `}
            ${drainState === 'paused' && html`
              <span class="queue-paused-label">Paused</span>
              <button class="queue-panel-btn resume" onClick=${onResume}>
                Resume
              </button>
            `}
            <button class="queue-panel-btn clear-all" onClick=${onClearAll}>
              Clear all
            </button>
          </div>
        </div>
        ${queue.map((msg, i) => html`
          <div
            class=${"queue-item" + (i === 0 && drainState === 'countdown' ? " queue-item--countdown" : "")}
            key=${msg.id}
          >
            <span class="queue-item-number">${i + 1}</span>
            <span class="queue-item-text" title=${msg.content}>${msg.content}</span>
            ${msg.images && msg.images.length > 0 && html`
              <span class="queue-item-image">[image]</span>
            `}
            ${i === 0 && drainState === 'countdown' && countdownSecs !== null && html`
              <span class="queue-item-countdown-label">Sending in ${countdownSecs}s\u2026</span>
            `}
            <button
              class="queue-item-remove"
              onClick=${() => onRemove(msg.id)}
              title="Remove from queue"
              aria-label=${"Remove queued message: " + msg.content}
            >\u00d7</button>
          </div>
        `)}
      </div>
    `;
  }

```

- [ ] **Step 2: Verify — page loads without errors**

Reload the browser. The QueuePanel component is defined but not yet rendered. No visual changes. No console errors.

- [ ] **Step 3: Commit**

```bash
cd /Users/samule/repo/amplifierd-plugin-chat/.worktrees/message-queue
git add src/chat_plugin/static/index.html
git commit -m "feat(queue): add QueuePanel component"
```

---

### Task 9: Wire QueuePanel into main layout

**File:** `src/chat_plugin/static/index.html:6073-6074`

Insert the QueuePanel between `MessageList` (ends at line 6073) and `InputArea` (starts at line 6074).

- [ ] **Step 1: Add QueuePanel render**

Find lines 6073-6074 (the boundary between MessageList and InputArea):

```javascript
            />
            <${InputArea}
```

The full context is the closing `/>` of `MessageList` followed by `<${InputArea}`. Replace:

```javascript
            />
            <${QueuePanel}
              queue=${getQueue()}
              drainState=${getQueueDrainState()}
              countdownSecs=${countdownRemaining}
              onRemove=${(msgId) => {
                // If removing the head item during a countdown, cancel the timer first
                // so it doesn't fire for a message that's gone, then restart for the new head.
                const q = getQueue();
                const isFirst = q.length > 0 && q[0].id === msgId;
                if (isFirst && getQueueDrainState() === 'countdown') {
                  cancelCountdown();
                  removeFromQueue(msgId);
                  tryDrainQueue(); // start countdown for new head (if any)
                } else {
                  removeFromQueue(msgId);
                }
              }}
              onClearAll=${() => {
                cancelCountdown();
                clearSessionQueue();
              }}
              onResume=${resumeQueue}
            />
            <${InputArea}
```

> **Note:** `cancelCountdown`, `tryDrainQueue`, and `resumeQueue` don't exist yet. They will be added in Chunks 4 and 5. To avoid a runtime error, add temporary stubs right after the queue helpers (from Task 2). Find the end of `setQueueDrainState` and add:

```javascript

    // Placeholder stubs — replaced in Chunk 4 & 5
    function cancelCountdown() {}
    function resumeQueue() {}
```

- [ ] **Step 2: Verify — QueuePanel renders when messages are queued**

1. Open the chat UI.
2. Send a message to start execution.
3. While executing, type "test message 1" and press Enter.
4. Type "test message 2" and press Enter.
5. A panel should appear above the input area showing:
   - Header: "Queued (2)"
   - Item 1: "test message 1" with an × button
   - Item 2: "test message 2" with an × button
   - A "Clear all" button
6. Click the × on item 1 — it should disappear, leaving only item 2.
7. Click "Clear all" — all items disappear and the panel hides.

- [ ] **Step 3: Commit**

```bash
cd /Users/samule/repo/amplifierd-plugin-chat/.worktrees/message-queue
git add src/chat_plugin/static/index.html
git commit -m "feat(queue): wire QueuePanel into main layout"
```

---

## Chunk 4: Auto-Drain Logic

### Task 10: Add startCountdown and cancelCountdown functions

**File:** `src/chat_plugin/static/index.html` — replace the `cancelCountdown` stub (from Task 9) and add `startCountdown`.

These functions manage the 3-second countdown before auto-sending the next queued message.

- [ ] **Step 1: Replace stubs with real implementations**

Find the placeholder stubs:

```javascript
    // Placeholder stubs — replaced in Chunk 4 & 5
    function cancelCountdown() {}
    function resumeQueue() {}
```

Replace with:

```javascript
    function cancelCountdown() {
      if (countdownTimerRef.current != null) {
        clearTimeout(countdownTimerRef.current);
        countdownTimerRef.current = null;
      }
      setCountdownRemaining(null); // null = no countdown active
    }

    function startCountdown(onFire) {
      cancelCountdown();
      const key = activeKeyRef.current;
      if (!key) return;
      setQueueDrainState('countdown', key);
      let remaining = 3;
      setCountdownRemaining(remaining);

      function tick() {
        remaining -= 1;
        if (remaining <= 0) {
          countdownTimerRef.current = null;
          setCountdownRemaining(null); // countdown finished — reset to null
          onFire();
        } else {
          setCountdownRemaining(remaining);
          countdownTimerRef.current = setTimeout(tick, 1000);
        }
      }
      countdownTimerRef.current = setTimeout(tick, 1000);
    }

    // Placeholder stub — replaced in Chunk 5
    function resumeQueue() {}
```

- [ ] **Step 2: Verify — no errors**

Reload. No visual changes yet (countdown isn't triggered). No console errors.

- [ ] **Step 3: Commit**

```bash
cd /Users/samule/repo/amplifierd-plugin-chat/.worktrees/message-queue
git add src/chat_plugin/static/index.html
git commit -m "feat(queue): add startCountdown and cancelCountdown"
```

---

### Task 11: Add tryDrainQueue function

**File:** `src/chat_plugin/static/index.html` — insert after `startCountdown`, before the `resumeQueue` stub.

`tryDrainQueue` is the main drain entry point. It checks if there are queued messages, and if so, starts a countdown that fires `sendMessage` with the first queued message.

- [ ] **Step 1: Add tryDrainQueue**

Find the resumeQueue stub:

```javascript
    // Placeholder stub — replaced in Chunk 5
    function resumeQueue() {}
```

Insert before it:

```javascript
    function tryDrainQueue() {
      const key = activeKeyRef.current;
      if (!key) return;
      const queue = getQueue(key);
      if (queue.length === 0) {
        setQueueDrainState('idle', key);
        return;
      }
      // Don't drain if already executing (safety guard)
      if (executing) return;

      startCountdown(() => {
        const currentKey = activeKeyRef.current;
        if (!currentKey) return;
        const currentQueue = getQueue(currentKey);
        if (currentQueue.length === 0) {
          setQueueDrainState('idle', currentKey);
          return;
        }
        const nextMsg = currentQueue[0];
        removeFromQueue(nextMsg.id);
        setQueueDrainState('idle', currentKey);
        sendMessage(nextMsg.content, nextMsg.images || []);
      });
    }

```

> **Important note on the `executing` guard:** When `tryDrainQueue` is called from SSE event handlers, `executing` will have **just been set to `false`** by `setExecuting(false)` on the line before. However, because `setExecuting` is async (React batching), the `executing` closure variable may still be `true` at call time. To fix this, `tryDrainQueue` should read the sessions ref directly instead. Replace the `executing` check:

Find in the `tryDrainQueue` you just added:

```javascript
      // Don't drain if already executing (safety guard)
      if (executing) return;
```

Replace with:

```javascript
      // Don't drain if still executing (read ref for latest state)
      const sess = sessionsRef.current.get(key) || {};
      if (sess.status === 'running') return;
```

- [ ] **Step 2: Verify — no errors**

Reload. No visual changes yet (drain isn't triggered). No console errors.

- [ ] **Step 3: Commit**

```bash
cd /Users/samule/repo/amplifierd-plugin-chat/.worktrees/message-queue
git add src/chat_plugin/static/index.html
git commit -m "feat(queue): add tryDrainQueue function"
```

---

### Task 12: Wire drain trigger into prompt_complete handler

**File:** `src/chat_plugin/static/index.html:4426`

When a prompt completes, if there are queued messages, we should start draining.

- [ ] **Step 1: Add tryDrainQueue call after setExecuting(false)**

Find the `prompt_complete` handler. The relevant section is at line 4426:

```javascript
            setExecuting(false);
            setTurnCount(nextTurn ?? (turnCountRef.current + 1));
          }
          // Flush accumulated token usage as a chrono item
```

Insert `tryDrainQueue()` call right after `setTurnCount`:

```javascript
            setExecuting(false);
            setTurnCount(nextTurn ?? (turnCountRef.current + 1));
            // Auto-drain queued messages
            tryDrainQueue();
          }
          // Flush accumulated token usage as a chrono item
```

- [ ] **Step 2: Verify — drain triggers on prompt_complete**

1. Open the chat UI, start a session.
2. Send a message like "Say hello" to start processing.
3. While the assistant is processing, type "Say goodbye" and press Enter (queues it).
4. Wait for the assistant to finish.
5. The QueuePanel should show a countdown: "3s", "2s", "1s".
6. After the countdown, "Say goodbye" should be sent automatically and disappear from the queue.
7. The assistant should start processing the queued message.

- [ ] **Step 3: Commit**

```bash
cd /Users/samule/repo/amplifierd-plugin-chat/.worktrees/message-queue
git add src/chat_plugin/static/index.html
git commit -m "feat(queue): wire drain trigger into prompt_complete"
```

---

### Task 13: Wire drain trigger into execution_cancelled handler

**File:** `src/chat_plugin/static/index.html:4456`

When execution is cancelled, the queue should also attempt to drain (the user might want to send the next queued message after cancelling).

- [ ] **Step 1: Add tryDrainQueue call**

Find the `execution_cancelled` handler at line 4456:

```javascript
          setExecuting(false);
          break;
```

(This is inside the `case 'execution_cancelled':` block.) Replace with:

```javascript
          setExecuting(false);
          // Auto-drain queued messages
          tryDrainQueue();
          break;
```

- [ ] **Step 2: Verify — drain triggers on cancel**

1. Send a message, then while processing, queue "follow up message".
2. Click "■ Stop" to cancel execution.
3. After cancellation, the QueuePanel should show a countdown and then send the queued message.

> **Note:** The Stop button behavior will be further refined in Chunk 5 (Task 16) to pause the queue instead. For now, this wiring confirms the plumbing works.

- [ ] **Step 3: Commit**

```bash
cd /Users/samule/repo/amplifierd-plugin-chat/.worktrees/message-queue
git add src/chat_plugin/static/index.html
git commit -m "feat(queue): wire drain trigger into execution_cancelled"
```

---

### Task 14: Wire drain trigger into execution_error handler

**File:** `src/chat_plugin/static/index.html:4476`

- [ ] **Step 1: Add tryDrainQueue call**

Find the `execution_error` handler at line 4476:

```javascript
          setExecuting(false);
          setChronoItems(prev => [...prev, {
```

Insert after `setExecuting(false)`:

```javascript
          setExecuting(false);
          // Auto-drain queued messages (even after error, let user decide via queue)
          tryDrainQueue();
          setChronoItems(prev => [...prev, {
```

- [ ] **Step 2: Verify — no errors on page load**

Reload. No console errors. The error handler path is hard to trigger manually but the wiring is in place.

- [ ] **Step 3: Commit**

```bash
cd /Users/samule/repo/amplifierd-plugin-chat/.worktrees/message-queue
git add src/chat_plugin/static/index.html
git commit -m "feat(queue): wire drain trigger into execution_error"
```

---

### Task 15: Wire drain trigger into executeStream error catch

**File:** `src/chat_plugin/static/index.html:5142`

This catches network/API errors when starting execution.

- [ ] **Step 1: Add tryDrainQueue call**

Find the `executeStream` catch block at line 5142:

```javascript
        setExecuting(false);
      });
    }, [connect]);
```

Insert after `setExecuting(false)`:

```javascript
        setExecuting(false);
        // Auto-drain queued messages
        tryDrainQueue();
      });
    }, [connect]);
```

- [ ] **Step 2: Verify — no errors**

Reload. No console errors. This code path only fires on network failures.

- [ ] **Step 3: Commit**

```bash
cd /Users/samule/repo/amplifierd-plugin-chat/.worktrees/message-queue
git add src/chat_plugin/static/index.html
git commit -m "feat(queue): wire drain trigger into executeStream error catch"
```

---

## Chunk 5: Stop + Resume Behavior

### Task 16: Modify stopExecution to pause queue drain

**File:** `src/chat_plugin/static/index.html:5146-5155`

When the user clicks Stop, we should also pause any active queue drain so it doesn't auto-send the next message immediately after cancellation.

- [ ] **Step 1: Update stopExecution**

Find `stopExecution` at lines 5146-5155:

```javascript
    const stopExecution = useCallback(() => {
      const key = activeKeyRef.current;
      const activeSession = key ? sessionsRef.current.get(key) : null;
      const sessionId = activeSession?.sessionId || null;
      if (sessionId) {
        api.cancelExecution(sessionId, false).catch(err => {
          console.error('[chat] cancelExecution failed', err);
        });
      }
    }, []);
```

Replace with:

```javascript
    const stopExecution = useCallback(() => {
      const key = activeKeyRef.current;
      const activeSession = key ? sessionsRef.current.get(key) : null;
      const sessionId = activeSession?.sessionId || null;
      if (sessionId) {
        api.cancelExecution(sessionId, false).catch(err => {
          console.error('[chat] cancelExecution failed', err);
        });
      }
      // Pause queue drain so queued messages don't auto-send after cancel
      cancelCountdown();
      if (key && getQueue(key).length > 0) {
        setQueueDrainState('paused', key);
      }
    }, []);
```

- [ ] **Step 2: Update execution_cancelled to not auto-drain when paused**

The `execution_cancelled` handler (Task 13) currently calls `tryDrainQueue()` unconditionally. We need to skip it if the user explicitly paused by clicking Stop.

Find the `tryDrainQueue()` call in the `execution_cancelled` handler:

```javascript
          setExecuting(false);
          // Auto-drain queued messages
          tryDrainQueue();
          break;
```

Replace with:

```javascript
          setExecuting(false);
          // Auto-drain queued messages (unless user explicitly paused via Stop)
          if (getQueueDrainState(ownerKey) !== 'paused') {
            tryDrainQueue();
          }
          break;
```

- [ ] **Step 3: Verify — Stop pauses the queue**

1. Send a message, queue "follow up 1" and "follow up 2".
2. Click "■ Stop".
3. After cancellation, the QueuePanel should show "Paused" label and a "Resume" button.
4. The countdown should NOT start — the queue is paused.

- [ ] **Step 4: Commit**

```bash
cd /Users/samule/repo/amplifierd-plugin-chat/.worktrees/message-queue
git add src/chat_plugin/static/index.html
git commit -m "feat(queue): pause queue drain on Stop"
```

---

### Task 17: Implement resumeQueue function

**File:** `src/chat_plugin/static/index.html` — replace the `resumeQueue` stub.

- [ ] **Step 1: Replace the stub**

Find the stub:

```javascript
    // Placeholder stub — replaced in Chunk 5
    function resumeQueue() {}
```

Replace with:

```javascript
    function resumeQueue() {
      const key = activeKeyRef.current;
      if (!key) return;
      if (getQueue(key).length === 0) {
        setQueueDrainState('idle', key);
        return;
      }
      // If currently executing, just mark as idle — drain will trigger on completion
      const sess = sessionsRef.current.get(key) || {};
      if (sess.status === 'running') {
        setQueueDrainState('idle', key);
        return;
      }
      // Not executing — start draining immediately
      tryDrainQueue();
    }
```

- [ ] **Step 2: Verify — Resume button works**

1. Send a message, queue "follow up".
2. Click "■ Stop" to pause the queue.
3. QueuePanel shows "Paused" and "Resume" button.
4. Click "Resume".
5. The countdown should start: "3s", "2s", "1s", then the queued message is sent.

- [ ] **Step 3: Commit**

```bash
cd /Users/samule/repo/amplifierd-plugin-chat/.worktrees/message-queue
git add src/chat_plugin/static/index.html
git commit -m "feat(queue): implement resumeQueue function"
```

---

### Task 18: Verify full Stop + Resume cycle (integration test)

This is a manual integration verification — no code changes.

- [ ] **Step 1: Full cycle test**

1. Open the chat UI, start a new session.
2. Send "Count from 1 to 20 slowly" (or any message that takes a few seconds).
3. While assistant is processing, type "Now count backwards from 5" and press Enter.
4. Type "Say done" and press Enter.
5. Verify QueuePanel shows 2 queued items.
6. Click "■ Stop".
7. Verify QueuePanel shows "Paused" with "Resume" button.
8. Click "Resume".
9. Verify countdown starts (3s → 2s → 1s).
10. Verify "Now count backwards from 5" is sent automatically.
11. While assistant processes that, verify "Say done" is still queued (1 item).
12. Wait for assistant to finish — countdown starts for "Say done".
13. "Say done" is sent and processed.
14. Queue is empty, QueuePanel disappears.

---

## Chunk 6: Session Lifecycle

### Task 19: Handle switchSession — cancel countdown on switch-away, restore on switch-back

**File:** `src/chat_plugin/static/index.html:5531-5595`

When switching sessions, we need to cancel any active countdown for the old session and check if the new session has a queue that needs draining.

- [ ] **Step 1: Add countdown cancel at the top of switchSession**

Find `switchSession` at line 5531. The beginning of the function (after the early returns) saves the current session state. Find:

```javascript
      // Save current session's messages
      if (currentKey) {
        setSessions(prev => {
```

Insert before this block:

```javascript
      // Cancel countdown for session we're leaving
      cancelCountdown();

      // Save current session's messages
      if (currentKey) {
        setSessions(prev => {
```

- [ ] **Step 2: Add queue drain check at the end of switchSession**

Find the end of `switchSession`, right before the closing `}, [sessions, handleWsMessage, resumeHistorySession]);`:

```javascript
      const queued = pendingEventsRef.current.get(key);
      if (queued && queued.length > 0) {
        pendingEventsRef.current.delete(key);
        for (const queuedMsg of queued) {
          handleWsMessage(queuedMsg, key);
        }
      }
    }, [sessions, handleWsMessage, resumeHistorySession]);
```

Insert after the `pendingEventsRef` replay block but before the closing:

```javascript
      const queued = pendingEventsRef.current.get(key);
      if (queued && queued.length > 0) {
        pendingEventsRef.current.delete(key);
        for (const queuedMsg of queued) {
          handleWsMessage(queuedMsg, key);
        }
      }

      // Restore queue drain state for the target session
      const targetDrainState = getQueueDrainState(key);
      if (targetDrainState !== 'paused' && getQueue(key).length > 0) {
        const targetSess = sessionsRef.current.get(key) || {};
        if (targetSess.status !== 'running') {
          tryDrainQueue();
        }
      }
    }, [sessions, handleWsMessage, resumeHistorySession]);
```

- [ ] **Step 3: Verify — switching sessions handles queue correctly**

1. Start session A. Send a message.
2. While processing, queue "follow up for A".
3. Create a new session (session B). This switches away from A.
4. Verify: the QueuePanel for session B is empty (no queue panel visible).
5. Switch back to session A.
6. Verify: the QueuePanel shows "follow up for A".
7. If session A's execution completed while you were away, the countdown should start.

- [ ] **Step 4: Commit**

```bash
cd /Users/samule/repo/amplifierd-plugin-chat/.worktrees/message-queue
git add src/chat_plugin/static/index.html
git commit -m "feat(queue): handle queue drain state across session switches"
```

---

### Task 20: Handle newSession — clear queue for new session

**File:** `src/chat_plugin/static/index.html:5178-5236`

When creating a new session, the previous session's countdown should be cancelled (already handled by the fact that `newSession` saves the old session). But we should also ensure the new session starts with a clean queue state.

- [ ] **Step 1: Add countdown cancel and queue reset to newSession**

Find line 5205 in `newSession`:

```javascript
      setExecuting(false);
      setPendingApproval(null);
```

Insert before `setExecuting(false)`:

```javascript
      // Cancel any active countdown from the previous session
      cancelCountdown();

      setExecuting(false);
      setPendingApproval(null);
```

> **Note:** We do NOT clear the old session's queue — it stays in `msgQueueRef` keyed by the old session key. The user may switch back to it.

- [ ] **Step 2: Verify — new session has no queue**

1. Start session A, send a message, queue a follow-up.
2. Click "New Session" to create session B.
3. Session B's input area should show no QueuePanel.
4. Switch back to session A — the queued message should still be there.

- [ ] **Step 3: Commit**

```bash
cd /Users/samule/repo/amplifierd-plugin-chat/.worktrees/message-queue
git add src/chat_plugin/static/index.html
git commit -m "feat(queue): cancel countdown on new session creation"
```

---

### Task 20.5: Session deletion — queue cleanup (future consideration)

**No code changes required now.** This task documents what must be done if/when a session delete UI is added.

There is currently no explicit session delete action in the UI — sessions are only removed from the `sessions` Map in edge cases. Because `msgQueueRef` and `queueDrainStateRef` are keyed by session key, stale entries will accumulate if sessions are deleted without cleanup.

**When a session delete action is added, it must:**

```javascript
// Inside the delete handler, after removing from sessionsRef / setSessions:
const deletedKey = /* the key being deleted */;

// 1. Cancel countdown if the deleted session is currently active
if (activeKeyRef.current === deletedKey) {
  cancelCountdown();
}

// 2. Clean up queue state for the deleted session
msgQueueRef.current.delete(deletedKey);
queueDrainStateRef.current.delete(deletedKey);
setQueueVersion(v => v + 1); // force re-render to hide any badge
```

**Also note:** `newSession` (Task 20) cancels the countdown for the session being left, but does NOT clear the old session's queue — that queue is intentionally preserved so the user can switch back and find their queued messages. The session delete path is the only place that should call `msgQueueRef.current.delete()`.

> **This is a non-blocking future consideration.** The current implementation is correct for the existing feature set. Add this cleanup when delete is implemented.

---

### Task 21: Add sidebar queue count badge

**File:** `src/chat_plugin/static/index.html:3200-3204`

Show a queue count badge in the sidebar session card when a session has queued messages.

- [ ] **Step 1: Pass queueCount to SessionCard**

First, find where `SessionCard` is rendered in the sidebar. Search for `<${SessionCard}`:

The SessionCard is rendered inside a `.map()` over sessions. Find the usage and add a `queueCount` prop. The `SessionCard` is likely rendered something like:

```javascript
<${SessionCard}
  session=${session}
  isActive=${...}
  ...
```

Add `queueCount` prop:

```javascript
  queueCount=${(msgQueueRef.current.get(sessionKey) || []).length}
```

The exact location depends on the render. To find it, search for `SessionCard` in the render section. Add the prop alongside the other props.

- [ ] **Step 2: Update SessionCard function signature**

Find line 3029:

```javascript
  function SessionCard({ session, isActive, onClick, setSessions, onTogglePin, isPinned }) {
```

Replace with:

```javascript
  function SessionCard({ session, isActive, onClick, setSessions, onTogglePin, isPinned, queueCount }) {
```

- [ ] **Step 3: Add badge to session-card-meta div**

Find lines 3200-3204 in SessionCard:

```javascript
        <div class="session-card-meta">
          <span>${metaText}</span>
          ${session.hasExternalUpdate
            ? html`<span class="session-stale-badge ${session.isNewSession ? 'new-session' : ''}">${session.isNewSession ? 'New' : 'Updated'}</span>`
            : null}
        </div>
```

Replace with:

```javascript
        <div class="session-card-meta">
          <span>${metaText}</span>
          ${queueCount > 0
            ? html`<span class="queue-count-badge" title="${queueCount} queued">${queueCount}</span>`
            : null}
          ${session.hasExternalUpdate
            ? html`<span class="session-stale-badge ${session.isNewSession ? 'new-session' : ''}">${session.isNewSession ? 'New' : 'Updated'}</span>`
            : null}
        </div>
```

- [ ] **Step 4: Verify — badge appears in sidebar**

1. Start a session, send a message.
2. While processing, queue 2 messages.
3. Look at the sidebar — the active session card should show a blue badge with "2".
4. Remove one from the queue — badge updates to "1".
5. Clear all — badge disappears.

- [ ] **Step 5: Commit**

```bash
cd /Users/samule/repo/amplifierd-plugin-chat/.worktrees/message-queue
git add src/chat_plugin/static/index.html
git commit -m "feat(queue): add queue count badge to sidebar session cards"
```

---

## Final Verification

### Task 22: End-to-end manual smoke test

No code changes — this is a comprehensive verification of all queue features working together.

- [ ] **Step 1: Full feature walkthrough**

Run through each scenario and confirm expected behavior:

| # | Scenario | Expected |
|---|----------|----------|
| 1 | Send message while idle | Normal send, no queue involved |
| 2 | Type + Enter while executing | Message added to queue, textarea clears, QueuePanel appears |
| 3 | Queue 3 messages, wait for completion | Countdown 3s, first sends, countdown 3s, second sends, repeat |
| 4 | Click × on a queued item | Item removed, count updates |
| 5 | Click "Clear all" | All items removed, panel hides |
| 6 | Click Stop while executing with queued items | Execution cancels, queue shows "Paused" + "Resume" |
| 7 | Click Resume after pause | Countdown starts, next message sends |
| 8 | Switch to another session with no queue | QueuePanel hidden, no countdown |
| 9 | Switch back to session with queue | QueuePanel shows, countdown resumes if applicable |
| 10 | New session | Previous session queue preserved, new session has no queue |
| 11 | Sidebar badge | Shows count while queue has items, disappears when empty |
| 12 | Queue a message, then queue another before first drains | Both remain in order, drain continues sequentially |

- [ ] **Step 2: Final commit (if any cleanup needed)**

```bash
cd /Users/samule/repo/amplifierd-plugin-chat/.worktrees/message-queue
git log --oneline -10  # Review all commits
```

Expected commit history (newest first):
```
feat(queue): add queue count badge to sidebar session cards
feat(queue): cancel countdown on new session creation
feat(queue): handle queue drain state across session switches
feat(queue): implement resumeQueue function
feat(queue): pause queue drain on Stop
feat(queue): wire drain trigger into executeStream error catch
feat(queue): wire drain trigger into execution_error
feat(queue): wire drain trigger into execution_cancelled
feat(queue): wire drain trigger into prompt_complete
feat(queue): add tryDrainQueue function
feat(queue): add startCountdown and cancelCountdown
feat(queue): wire QueuePanel into main layout
feat(queue): add QueuePanel component
feat(queue): add QueuePanel and badge CSS
feat(queue): show both Send/Queue and Stop buttons during execution
feat(queue): keep textarea enabled during execution with queue placeholder
feat(queue): route messages to queue when executing
feat(queue): pass queue props to InputArea
feat(queue): add queue helper functions
feat(queue): add queue state declarations (refs + useState)
```
