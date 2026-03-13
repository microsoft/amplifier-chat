# Message-Activity Correlation Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add visual correlation between conversation messages (left panel) and activities (right panel) in workspace mode, so users can see which activities belong to which message.

**Architecture:** Derive turn boundaries from existing `chronoItems` data (no data model changes). Each user message starts a new "turn"; all items until the next user message belong to that turn. Add turn separators in the activity panel, a sticky breadcrumb for scroll context, hover cross-highlighting between panels, and click-to-navigate in both directions.

**Tech Stack:** Preact (htm tagged templates), inline CSS, CSS custom properties. Single-file SPA at `src/chat_plugin/static/index.html` (~6150 lines).

**Working directory:** `/Users/samule/repo/amplifierd-plugin-chat/.worktrees/message-activity-correlation`

---

## File Map

All changes are in a single file:

- **Modify:** `src/chat_plugin/static/index.html`
  - CSS section (lines ~100-1200): Add new styles
  - Component section (lines ~2600-3007): Add new components, modify MessageList and ChronoItem
  - State section (lines ~3460-3563): Add turn derivation
  - Layout section (lines ~5811-6140): Wire everything together

---

## Chunk 1: Foundation — Turn Derivation + Separators

This chunk delivers standalone value: organized activities grouped by conversation turn.

### Task 1: Add CSS Custom Properties and Turn Styles

**Files:**
- Modify: `src/chat_plugin/static/index.html` — CSS section near line 100 (`:root` block) and after line 661 (activity panel styles)

- [ ] **Step 1: Add CSS custom properties for turn correlation**

Find the `:root` CSS block (around line 15-60) and add these variables at the end, before the closing `}`:

```css
    /* Turn correlation */
    --turn-highlight: rgba(59, 130, 246, 0.04);
    --turn-highlight-border: rgba(59, 130, 246, 0.25);
    --turn-pulse-peak: rgba(59, 130, 246, 0.12);
```

Find the `body[data-theme="light"]` block and add the light-theme overrides:

```css
    --turn-highlight: rgba(37, 99, 235, 0.05);
    --turn-highlight-border: rgba(37, 99, 235, 0.2);
    --turn-pulse-peak: rgba(37, 99, 235, 0.1);
```

- [ ] **Step 2: Add turn separator CSS**

After the `.activity-scroll` rule (line ~661), add:

```css
    /* Turn separators in activity panel */
    .turn-separator {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 10px 0 6px;
      cursor: pointer;
      user-select: none;
    }
    .turn-separator:first-child {
      padding-top: 0;
    }
    .turn-separator::before,
    .turn-separator::after {
      content: '';
      flex: 1;
      height: 1px;
      background: var(--border);
      transition: background 150ms ease;
    }
    .turn-separator:hover::before,
    .turn-separator:hover::after {
      background: var(--turn-highlight-border);
    }
    .turn-separator-label {
      display: flex;
      align-items: center;
      gap: 6px;
      flex-shrink: 0;
      max-width: 85%;
    }
    .turn-separator-number {
      font-size: 10px;
      color: var(--text-muted);
      letter-spacing: 0.05em;
      font-variant-numeric: tabular-nums;
      flex-shrink: 0;
    }
    .turn-separator-message {
      font-size: 11px;
      color: var(--text-secondary);
      font-style: italic;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      min-width: 0;
    }
    .turn-separator:hover .turn-separator-message {
      color: var(--text-primary);
    }
    .turn-separator:hover .turn-separator-number {
      color: var(--accent-blue, #3b82f6);
    }
```

- [ ] **Step 3: Add activity breadcrumb CSS**

Immediately after the turn separator styles, add:

```css
    /* Sticky turn breadcrumb in activity panel */
    .activity-breadcrumb {
      display: flex;
      align-items: center;
      gap: 6px;
      padding: 4px 12px;
      font-size: 11px;
      color: var(--text-muted);
      background: var(--bg-secondary);
      border-bottom: 1px solid var(--border);
      flex-shrink: 0;
      min-height: 24px;
      box-shadow: 0 1px 4px rgba(0, 0, 0, 0.15);
      z-index: 2;
      position: relative;
    }
    .activity-breadcrumb.hidden { display: none; }
    .activity-breadcrumb-number {
      font-variant-numeric: tabular-nums;
      flex-shrink: 0;
    }
    .activity-breadcrumb-message {
      color: var(--text-secondary);
      font-style: italic;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      flex: 1;
      min-width: 0;
    }
    .activity-breadcrumb-nav {
      opacity: 0;
      cursor: pointer;
      color: var(--text-muted);
      font-size: 12px;
      padding: 2px 4px;
      border-radius: 3px;
      transition: opacity 100ms ease, color 100ms ease;
      background: none;
      border: none;
    }
    .activity-breadcrumb:hover .activity-breadcrumb-nav {
      opacity: 1;
    }
    .activity-breadcrumb-nav:hover {
      color: var(--accent-blue, #3b82f6);
      background: var(--bg-tertiary);
    }
    body[data-theme="light"] .activity-breadcrumb {
      box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
    }
```

- [ ] **Step 4: Add hover highlight and pulse CSS**

After the breadcrumb styles, add:

```css
    /* Turn hover cross-highlight */
    .turn-highlighted {
      background: var(--turn-highlight);
      transition: background 120ms ease-out;
    }
    .turn-highlighted.turn-highlighted-border {
      border-left: 2px solid var(--turn-highlight-border);
    }
    .turn-dimmed {
      opacity: 0.4;
      transition: opacity 150ms ease-out;
    }
    .turn-separator.turn-highlighted::before,
    .turn-separator.turn-highlighted::after {
      background: var(--turn-highlight-border);
    }
    .turn-separator.turn-highlighted .turn-separator-number {
      color: var(--accent-blue, #3b82f6);
    }

    /* Click-to-scroll arrival pulse */
    @keyframes turn-pulse {
      0%   { background: var(--turn-pulse-peak); }
      40%  { background: var(--turn-highlight); }
      100% { background: transparent; }
    }
    .turn-scroll-target {
      animation: turn-pulse 800ms ease-out forwards;
    }

    /* Reduced motion */
    @media (prefers-reduced-motion: reduce) {
      .turn-highlighted,
      .turn-dimmed {
        transition: none;
      }
      .turn-scroll-target {
        animation: none;
        background: var(--turn-highlight);
      }
    }
```

- [ ] **Step 5: Verify and commit**

Open the app in workspace mode and confirm no visual regressions. The new styles shouldn't affect anything yet since no elements use the new classes.

```bash
cd /Users/samule/repo/amplifierd-plugin-chat/.worktrees/message-activity-correlation
git add src/chat_plugin/static/index.html
git commit -m "feat: add CSS for message-activity correlation

Add CSS custom properties, turn separator styles, activity breadcrumb
styles, hover highlight/dim styles, pulse animation, and reduced
motion support for the upcoming message-activity correlation feature."
```

---

### Task 2: Turn Derivation Logic

**Files:**
- Modify: `src/chat_plugin/static/index.html` — near the filter definitions (lines ~5811-5812)

- [ ] **Step 1: Add `deriveTurns` helper function**

Add this function in the component utilities section, after the `transcriptToChronoItems` function (after line ~2393):

```javascript
  /**
   * Derive turn boundaries from chronoItems.
   * A new turn starts at each user message. Returns:
   * - turnMap: Map<turnId, { turnId, turnNumber, userItem, startOrder }>
   * - itemTurnMap: Map<itemId, turnId>
   * turnId is the id of the user message that opened the turn.
   */
  function deriveTurns(items) {
    const turnMap = new Map();
    const itemTurnMap = new Map();
    const sorted = [...items].sort((a, b) => a.order - b.order);

    let currentTurnId = null;
    let turnNumber = 0;

    for (const item of sorted) {
      if (item.type === 'text' && item.role === 'user') {
        turnNumber++;
        currentTurnId = item.id;
        turnMap.set(currentTurnId, {
          turnId: currentTurnId,
          turnNumber,
          userItem: item,
          startOrder: item.order,
        });
      }
      if (currentTurnId) {
        itemTurnMap.set(item.id, currentTurnId);
      }
    }

    return { turnMap, itemTurnMap };
  }
```

- [ ] **Step 2: Add turn derivation state to ChatApp**

Inside the `ChatApp` function, near the filter definitions (lines ~5811-5812), add the memoized turn derivation and hover state. Place this just BEFORE the filter lines:

```javascript
    // Turn correlation
    const { turnMap, itemTurnMap } = useMemo(() => deriveTurns(chronoItems), [chronoItems]);
    const [hoveredTurnId, setHoveredTurnId] = useState(null);
    const [activeTurnId, setActiveTurnId] = useState(null); // for click-to-navigate pulse
```

- [ ] **Step 3: Verify and commit**

Add `console.log('turnMap size:', turnMap.size)` temporarily after the derivation, open workspace mode with an active conversation, and confirm the turn count matches the number of user messages. Remove the console.log.

```bash
git add src/chat_plugin/static/index.html
git commit -m "feat: add turn derivation from chronoItems

Compute turn boundaries from existing chronoItems using useMemo.
Each user message starts a new turn. Adds hoveredTurnId and
activeTurnId state for cross-panel correlation."
```

---

### Task 3: TurnSeparator Component

**Files:**
- Modify: `src/chat_plugin/static/index.html` — component section, after ThinkingBlock (line ~2640)

- [ ] **Step 1: Create TurnSeparator component**

Add after the `ThinkingBlock` component (after line ~2640):

```javascript
  function TurnSeparator({ turn, isHighlighted, onClick }) {
    const preview = turn.userItem.content
      ? turn.userItem.content.replace(/\s+/g, ' ').trim().slice(0, 50)
      : '';
    const cls = 'turn-separator' + (isHighlighted ? ' turn-highlighted' : '');
    return html`
      <div class=${cls} data-turn-id=${turn.turnId}
        onClick=${onClick} tabindex="0"
        onKeyDown=${e => (e.key === 'Enter' || e.key === ' ') && onClick && onClick(e)}
        role="button"
        aria-label=${'Turn ' + turn.turnNumber + ': ' + preview}>
        <span class="turn-separator-label">
          <span class="turn-separator-number">#${turn.turnNumber}</span>
          <span class="turn-separator-message">${preview}${turn.userItem.content && turn.userItem.content.length > 50 ? '…' : ''}</span>
        </span>
      </div>
    `;
  }
```

- [ ] **Step 2: Verify and commit**

The component isn't rendered yet — just confirm no syntax errors by loading the app.

```bash
git add src/chat_plugin/static/index.html
git commit -m "feat: add TurnSeparator component

Lightweight horizontal divider showing turn number and truncated
user message. Clickable and keyboard-accessible."
```

---

### Task 4: ActivityBreadcrumb Component

**Files:**
- Modify: `src/chat_plugin/static/index.html` — component section, after TurnSeparator

- [ ] **Step 1: Create ActivityBreadcrumb component**

Add immediately after the `TurnSeparator` component:

```javascript
  function ActivityBreadcrumb({ turnMap, scrollTurnId, onNavigateToMessage }) {
    if (!scrollTurnId || !turnMap.has(scrollTurnId)) return null;
    if (turnMap.size <= 1) return null;

    const turn = turnMap.get(scrollTurnId);
    const preview = turn.userItem.content
      ? turn.userItem.content.replace(/\s+/g, ' ').trim().slice(0, 50)
      : '';

    return html`
      <div class="activity-breadcrumb" data-turn-id=${turn.turnId}>
        <span class="activity-breadcrumb-number">#${turn.turnNumber}</span>
        <span class="activity-breadcrumb-dot">·</span>
        <span class="activity-breadcrumb-message">${preview}${turn.userItem.content && turn.userItem.content.length > 50 ? '…' : ''}</span>
        <button class="activity-breadcrumb-nav"
          onClick=${() => onNavigateToMessage && onNavigateToMessage(turn.turnId)}
          title="Scroll to this message"
          aria-label=${'Navigate to turn ' + turn.turnNumber + ' message'}>↗</button>
      </div>
    `;
  }
```

- [ ] **Step 2: Verify and commit**

```bash
git add src/chat_plugin/static/index.html
git commit -m "feat: add ActivityBreadcrumb component

Sticky breadcrumb showing current turn context in the activity panel.
Shows turn number, truncated message, and a navigate button."
```

---

### Task 5: Inject Turn Separators into Activity Panel MessageList

**Files:**
- Modify: `src/chat_plugin/static/index.html` — MessageList component (lines ~2883-3007) and workspace layout JSX (lines ~6093-6140)

- [ ] **Step 1: Add turn-aware props to MessageList**

Update the `MessageList` function signature (line ~2883) to accept new props:

```javascript
  function MessageList({
    items,
    filterFn,
    sessionKey,
    showJumpControls = false,
    bottomNoticeSignal = 0,
    bottomNoticeLabel = 'New messages',
    subSessionsRef,
    subSessionRevision,
    onNavigateSession,
    // Turn correlation props
    turnMap,
    itemTurnMap,
    hoveredTurnId,
    setHoveredTurnId,
    isActivityPanel = false,
    onTurnSeparatorClick,
    onScrollTurnChange,
  }) {
```

- [ ] **Step 2: Add turn separator injection in the render**

Replace the `sorted.map` call in the return JSX (lines ~2983-2985). The current code is:

```javascript
          ${sorted.map(item => html`<${ChronoItem} key=${item.id} item=${item}
            subSessionsRef=${subSessionsRef} subSessionRevision=${subSessionRevision}
            onNavigateSession=${onNavigateSession} />`)}
```

Replace with:

```javascript
          ${sorted.map((item, i) => {
            const turnId = itemTurnMap ? itemTurnMap.get(item.id) : null;
            const prevTurnId = i > 0 ? (itemTurnMap ? itemTurnMap.get(sorted[i - 1].id) : null) : null;
            const showSep = isActivityPanel && turnMap && turnId && turnId !== prevTurnId;
            const isItemHighlighted = hoveredTurnId && turnId === hoveredTurnId;
            const isItemDimmed = hoveredTurnId && turnId && turnId !== hoveredTurnId;
            const turn = showSep ? turnMap.get(turnId) : null;

            const itemCls = isItemHighlighted ? 'turn-highlighted' + (isActivityPanel ? ' turn-highlighted-border' : '')
              : isItemDimmed ? 'turn-dimmed' : '';

            return html`
              ${showSep && turn && html`<${TurnSeparator}
                key=${'sep-' + turnId}
                turn=${turn}
                isHighlighted=${hoveredTurnId === turnId}
                onClick=${() => onTurnSeparatorClick && onTurnSeparatorClick(turnId)}
              />`}
              <div class=${itemCls || undefined}
                data-turn-id=${turnId || undefined}
                onMouseEnter=${() => setHoveredTurnId && turnId && setHoveredTurnId(turnId)}
                onMouseLeave=${() => setHoveredTurnId && setHoveredTurnId(null)}>
                <${ChronoItem} key=${item.id} item=${item}
                  isActivity=${isActivityPanel}
                  subSessionsRef=${subSessionsRef} subSessionRevision=${subSessionRevision}
                  onNavigateSession=${onNavigateSession} />
              </div>
            `;
          })}
```

- [ ] **Step 3: Add IntersectionObserver for scroll-based turn tracking**

Inside `MessageList`, after the existing `useEffect` blocks but before the return, add scroll turn tracking for the activity panel:

```javascript
    // Track which turn is currently at the top of the activity panel scroll
    const observerRef = useRef(null);
    useEffect(() => {
      if (!isActivityPanel || !onScrollTurnChange || !listRef.current) return;
      if (observerRef.current) observerRef.current.disconnect();

      const observer = new IntersectionObserver((entries) => {
        // Find the last separator that scrolled above the viewport
        const separators = listRef.current.querySelectorAll('.turn-separator[data-turn-id]');
        let currentTurn = null;
        for (const sep of separators) {
          const rect = sep.getBoundingClientRect();
          const listRect = listRef.current.getBoundingClientRect();
          if (rect.top <= listRect.top + 40) {
            currentTurn = sep.getAttribute('data-turn-id');
          }
        }
        if (currentTurn) onScrollTurnChange(currentTurn);
      }, {
        root: listRef.current,
        rootMargin: '-40px 0px 0px 0px',
        threshold: 0,
      });

      // Observe all turn separators after a short delay for DOM settlement
      const timer = setTimeout(() => {
        const seps = listRef.current.querySelectorAll('.turn-separator[data-turn-id]');
        seps.forEach(sep => observer.observe(sep));
      }, 100);

      observerRef.current = observer;
      return () => {
        clearTimeout(timer);
        observer.disconnect();
      };
    }, [isActivityPanel, onScrollTurnChange, sorted.length, sessionKey]);
```

- [ ] **Step 4: Pass turn props from ChatApp to both MessageList instances**

In the ChatApp layout JSX, update the **main pane** MessageList (lines ~6101-6111) to pass turn props:

```javascript
            <${MessageList}
              items=${chronoItems}
              filterFn=${mainFilter}
              sessionKey=${(activeKey || 'none') + (viewMode === 'workspace' ? ':main-workspace' : ':main-chat')}
              showJumpControls=${true}
              bottomNoticeSignal=${diskUpdateNoticeSignal}
              bottomNoticeLabel="New messages"
              subSessionsRef=${subSessionsRef}
              subSessionRevision=${subSessionRevision}
              onNavigateSession=${navigateToSession}
              turnMap=${viewMode === 'workspace' ? turnMap : undefined}
              itemTurnMap=${viewMode === 'workspace' ? itemTurnMap : undefined}
              hoveredTurnId=${viewMode === 'workspace' ? hoveredTurnId : undefined}
              setHoveredTurnId=${viewMode === 'workspace' ? setHoveredTurnId : undefined}
            />
```

Update the **activity panel** MessageList (lines ~6129-6137) to pass turn props:

```javascript
                <${MessageList}
                  items=${chronoItems}
                  filterFn=${activityFilter}
                  sessionKey=${(activeKey || 'none') + ':activity'}
                  showJumpControls=${true}
                  subSessionsRef=${subSessionsRef}
                  subSessionRevision=${subSessionRevision}
                  onNavigateSession=${navigateToSession}
                  turnMap=${turnMap}
                  itemTurnMap=${itemTurnMap}
                  hoveredTurnId=${hoveredTurnId}
                  setHoveredTurnId=${setHoveredTurnId}
                  isActivityPanel=${true}
                  onTurnSeparatorClick=${(turnId) => {
                    const turn = turnMap.get(turnId);
                    if (!turn) return;
                    const el = document.getElementById(turn.userItem.id);
                    if (el) {
                      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                      el.classList.add('turn-scroll-target');
                      setTimeout(() => el.classList.remove('turn-scroll-target'), 800);
                    }
                  }}
                  onScrollTurnChange=${setActiveTurnId}
                />
```

- [ ] **Step 5: Add ActivityBreadcrumb to the activity panel layout**

In the activity panel JSX (around line 6126-6139), add the breadcrumb between the header and the scroll area. Change:

```javascript
            <div class="activity-panel" style=${{ width: activityPanelWidth + 'px' }}>
              <div class="activity-panel-header">Activity</div>
              <div class="activity-scroll">
```

To:

```javascript
            <div class="activity-panel" style=${{ width: activityPanelWidth + 'px' }}>
              <div class="activity-panel-header">Activity</div>
              <${ActivityBreadcrumb}
                turnMap=${turnMap}
                scrollTurnId=${activeTurnId}
                onNavigateToMessage=${(turnId) => {
                  const turn = turnMap.get(turnId);
                  if (!turn) return;
                  const el = document.getElementById(turn.userItem.id);
                  if (el) {
                    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    el.classList.add('turn-scroll-target');
                    setTimeout(() => el.classList.remove('turn-scroll-target'), 800);
                  }
                }}
              />
              <div class="activity-scroll">
```

- [ ] **Step 6: Verify turn separators render correctly**

1. Open the app in workspace mode with a multi-turn conversation
2. Verify: Turn separators appear between turn groups in the activity panel with `#1`, `#2`, etc.
3. Verify: Truncated user message preview appears in each separator
4. Verify: No separators appear in the main (message) panel
5. Verify: Breadcrumb appears below the "Activity" header and updates on scroll
6. Verify: Chat mode (non-workspace) is unaffected — no turn separators visible

- [ ] **Step 7: Commit**

```bash
git add src/chat_plugin/static/index.html
git commit -m "feat: inject turn separators and breadcrumb into activity panel

MessageList now accepts turn correlation props. In the activity panel,
turn separators are injected between turn groups showing turn number
and truncated user message. A sticky breadcrumb below the Activity
header shows the current scroll turn. Click separator to scroll
the main panel to the corresponding message."
```

---

## Chunk 2: Cross-Panel Interaction — Hover + Click Navigation

### Task 6: Click-to-Navigate from Main Panel to Activity Panel

**Files:**
- Modify: `src/chat_plugin/static/index.html` — ChatApp layout JSX

- [ ] **Step 1: Add click handler for main panel messages**

We need clicking a message in the main panel to scroll the activity panel to that turn's separator. In the main pane `MessageList`, the hover wrapper `div` already has `onMouseEnter`/`onMouseLeave`. We need to add `onClick`. But we can't directly reference the activity panel's scroll container from the main `MessageList`.

Add a ref for the activity scroll container in ChatApp state area (near the other refs around line ~3514):

```javascript
    const activityScrollRef = useRef(null);
```

Update the activity panel's scroll container div to use this ref. Change:

```javascript
              <div class="activity-scroll">
```

To:

```javascript
              <div class="activity-scroll" ref=${activityScrollRef}>
```

Now, update the main pane `MessageList` props to include a click handler. Add this prop alongside the existing turn props:

```javascript
              onTurnSeparatorClick=${viewMode === 'workspace' ? (turnId) => {
                // Scroll activity panel to the turn separator
                if (!activityScrollRef.current) return;
                const sep = activityScrollRef.current.querySelector('.turn-separator[data-turn-id="' + turnId + '"]');
                if (sep) {
                  sep.scrollIntoView({ behavior: 'smooth', block: 'start' });
                  // Pulse the separator and its turn group
                  const parent = sep.parentElement;
                  if (parent) {
                    const items = parent.querySelectorAll('[data-turn-id="' + turnId + '"]');
                    items.forEach(el => {
                      el.classList.add('turn-scroll-target');
                      setTimeout(() => el.classList.remove('turn-scroll-target'), 800);
                    });
                  }
                }
              } : undefined}
```

- [ ] **Step 2: Wire the click in MessageList item wrapper**

In the `MessageList` render, update the item wrapper div to also handle click for the **non-activity** panel. The wrapper div currently has `onMouseEnter`/`onMouseLeave`. Add:

```javascript
                onClick=${() => {
                  if (!isActivityPanel && onTurnSeparatorClick && turnId) {
                    onTurnSeparatorClick(turnId);
                  }
                }}
                style=${!isActivityPanel && turnId ? 'cursor: pointer;' : undefined}
```

- [ ] **Step 3: Verify bidirectional navigation**

1. Workspace mode with a multi-turn conversation
2. Click a user message in the main panel → activity panel scrolls to that turn's separator with a pulse
3. Click a turn separator in the activity panel → main panel scrolls to the user message with a pulse
4. Click breadcrumb ↗ → main panel scrolls to the message

- [ ] **Step 4: Commit**

```bash
git add src/chat_plugin/static/index.html
git commit -m "feat: add bidirectional click-to-navigate between panels

Click a message in the main panel to scroll the activity panel to
that turn's activities. Click a turn separator or breadcrumb nav
to scroll back to the corresponding message. Both directions use
smooth scrolling with an 800ms pulse animation on arrival."
```

---

### Task 7: Hover Debouncing

**Files:**
- Modify: `src/chat_plugin/static/index.html` — MessageList component

- [ ] **Step 1: Add hover debounce to prevent strobe during fast scanning**

In the `MessageList` component, add a debounce ref near the top of the function body (after the existing refs):

```javascript
    const hoverTimerRef = useRef(null);
    const debouncedSetHoveredTurnId = useCallback((turnId) => {
      if (hoverTimerRef.current) clearTimeout(hoverTimerRef.current);
      if (turnId === null) {
        // Clear immediately on mouse leave
        setHoveredTurnId && setHoveredTurnId(null);
        return;
      }
      hoverTimerRef.current = setTimeout(() => {
        setHoveredTurnId && setHoveredTurnId(turnId);
      }, 50); // 50ms hover intent delay
    }, [setHoveredTurnId]);
```

Update the item wrapper's `onMouseEnter`/`onMouseLeave` in the render to use the debounced version:

```javascript
                onMouseEnter=${() => turnId && debouncedSetHoveredTurnId(turnId)}
                onMouseLeave=${() => debouncedSetHoveredTurnId(null)}
```

- [ ] **Step 2: Verify hover behavior**

1. Quickly scan the mouse across multiple messages — activity panel should NOT strobe
2. Hover and rest on a message for >50ms — activities highlight
3. Move to a different message — old highlight fades, new one appears (crossfade)
4. Move mouse off both panels — all highlights clear immediately

- [ ] **Step 3: Commit**

```bash
git add src/chat_plugin/static/index.html
git commit -m "feat: add 50ms hover debounce for turn highlighting

Prevents the activity panel from strobing when the user quickly
scans across messages. Immediate clear on mouse leave."
```

---

## Chunk 3: Polish

### Task 8: Handle Edge Cases

**Files:**
- Modify: `src/chat_plugin/static/index.html`

- [ ] **Step 1: Handle turns with no activities**

In the activity panel, if a turn has no non-text items, no separator should appear for it (it would be an orphaned header). The current logic already handles this because separators are only injected when we encounter an activity item with a new `turnId` — if a turn has only text items, no activity items will trigger a separator.

Verify this by creating a conversation where the assistant responds with text only (no tool calls). Confirm no orphaned separator appears.

- [ ] **Step 2: Handle items before the first user message**

System messages or initial assistant text may appear before any user message. These items get `turnId: null`. Verify they render normally without turn highlighting or separators.

- [ ] **Step 3: Handle session switching**

When switching sessions, `chronoItems` is reset to `[]`, then populated. Verify:
1. Switch between sessions in workspace mode
2. Turn separators update correctly for each session
3. No stale hover state persists across sessions

Add a cleanup in the session-change `useEffect`. Near the session reset code (around line ~5240), ensure `hoveredTurnId` and `activeTurnId` are cleared. Find where `setChronoItems([])` is called during session switch and add:

```javascript
      setHoveredTurnId(null);
      setActiveTurnId(null);
```

- [ ] **Step 4: Handle streaming turn (current/active turn)**

During streaming, new items arrive via SSE. The `deriveTurns` `useMemo` recomputes on every `chronoItems` change — which happens on each streamed item. This is O(n) and should be fast for typical session sizes (<1000 items).

Verify: Start a new message during workspace mode. Confirm the new turn separator appears when the first activity (thinking/tool_call) arrives, and the breadcrumb updates during streaming.

- [ ] **Step 5: Commit**

```bash
git add src/chat_plugin/static/index.html
git commit -m "feat: handle edge cases for turn correlation

Clear hover/active state on session switch. Verify turns with no
activities, pre-first-message items, and streaming behavior."
```

---

### Task 9: Accessibility Pass

**Files:**
- Modify: `src/chat_plugin/static/index.html`

- [ ] **Step 1: Ensure keyboard navigation works**

Turn separators already have `tabindex="0"` and keyboard handlers. Verify:
1. Tab through the activity panel — separators are focusable
2. Press Enter on a focused separator — scrolls to message
3. Focus styling is visible (the existing `:focus-visible` styles should apply)

- [ ] **Step 2: Add ARIA labels for screen readers**

The turn separator already has `aria-label`. Add `role="navigation"` and `aria-label` to the breadcrumb:

```javascript
    return html`
      <nav class="activity-breadcrumb" aria-label="Current turn context" data-turn-id=${turn.turnId}>
```

(Change the outer `div` to `nav`.)

- [ ] **Step 3: Verify reduced motion**

1. Enable "Reduce motion" in system preferences
2. Verify: Hover highlights appear instantly (no transition)
3. Verify: Click-to-scroll jumps instantly (no smooth scroll)
4. Verify: Pulse uses static highlight instead of animation

For smooth scroll to respect reduced motion, wrap the `scrollIntoView` calls:

```javascript
const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
el.scrollIntoView({ behavior: prefersReducedMotion ? 'instant' : 'smooth', block: 'center' });
```

Apply this to both the separator click handler and the breadcrumb navigate handler.

- [ ] **Step 4: Commit**

```bash
git add src/chat_plugin/static/index.html
git commit -m "feat: accessibility pass for turn correlation

Add ARIA labels, ensure keyboard navigation, respect reduced
motion preferences for scroll and animation."
```

---

### Task 10: Final Integration Verification

- [ ] **Step 1: Full walkthrough test**

Open the app and perform a complete test:

1. Start in chat mode — verify no turn UI is visible
2. Switch to workspace mode — verify turn separators appear in activity panel
3. Hover a user message — verify corresponding activities highlight with blue wash + left border
4. Hover an activity item — verify the user message highlights
5. Move mouse between messages — verify smooth crossfade highlight transition
6. Click a user message — verify activity panel scrolls to turn, pulse animation plays
7. Click a turn separator — verify main panel scrolls to message, pulse plays
8. Scroll the activity panel — verify breadcrumb updates to show current turn
9. Click breadcrumb ↗ — verify main panel scrolls to message
10. Switch sessions — verify clean state reset
11. New streaming message — verify new turn appears dynamically
12. Switch back to chat mode — verify all turn UI disappears cleanly

- [ ] **Step 2: Performance check**

With a large session (20+ turns, 50+ tool calls):
1. Verify no perceptible lag on hover (should be <16ms)
2. Verify smooth scrolling (no jank)
3. Check Chrome DevTools Performance tab during hover interaction — confirm no layout thrashing

- [ ] **Step 3: Final commit**

```bash
git add src/chat_plugin/static/index.html
git commit -m "feat: message-activity correlation in workspace mode

Add visual correlation between conversation messages and activities
in workspace mode. Features:
- Turn separators in the activity panel with message previews
- Sticky breadcrumb showing current turn context
- Cross-panel hover highlighting (50ms debounce)
- Bidirectional click-to-navigate with smooth scroll + pulse
- Keyboard accessible, reduced motion safe
- Clean state management across session switches"
```

---

## Summary

| Task | What It Delivers | Approx Size |
|------|-----------------|-------------|
| 1 | CSS foundation (variables, styles, animations) | ~120 lines CSS |
| 2 | Turn derivation logic | ~30 lines JS |
| 3 | TurnSeparator component | ~20 lines JS |
| 4 | ActivityBreadcrumb component | ~25 lines JS |
| 5 | Wire separators + breadcrumb into MessageList + layout | ~80 lines JS |
| 6 | Bidirectional click-to-navigate | ~30 lines JS |
| 7 | Hover debouncing | ~15 lines JS |
| 8 | Edge case handling | ~10 lines JS |
| 9 | Accessibility pass | ~15 lines JS |
| 10 | Final verification | 0 lines (test only) |

**Total estimated additions:** ~250 lines CSS + ~225 lines JS = ~475 lines added to the 6150-line file.
