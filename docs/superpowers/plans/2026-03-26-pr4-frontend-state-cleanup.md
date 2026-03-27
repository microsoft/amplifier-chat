# PR 4: Frontend State + Cleanup — Implementation Plan

> **Execution:** Use the subagent-driven-development workflow to implement this plan.

**Goal:** Fix 10 frontend state management bugs and integrate DOMPurify into the vendor bundle, replacing the hand-rolled HTML sanitizer with a battle-tested library and committing reproducible build tooling.

**Architecture:** Nine fixes are surgical edits (1–8 lines each) in the single-file Preact SPA (`index.html`). One fix renames 3 attributes in the Python dev server (`__main__.py`). The largest change (S-26) adds DOMPurify to the vendored JS bundle, replaces the `sanitizeHtml` function body, and commits the build tooling that should have existed from day one. All changes are backwards-compatible — no new UI, no API changes.

**Tech Stack:** JavaScript (Preact SPA in `index.html`), Python 3.12 (dev server), esbuild (vendor bundling), pytest (structural string-match tests), bash (build script)

**Design doc:** `docs/superpowers/specs/2026-03-26-amplifier-chat-comprehensive-bugfix-design.md` (PR 4 section)

**Branch dependency:** Branch from `main` after PR 3 (`fix/event-pipeline`) is merged. PR 3 adds `child_session_id` guards to `index.html` that PR 4 builds on top of.

---

### Task 1: Create the feature branch and verify baseline

**Step 1: Create and switch to the branch**

```bash
cd /Users/samule/repo/amplifier-chat
git checkout main
git pull origin main
git checkout -b fix/frontend-state-cleanup
```

**Step 2: Verify clean baseline**

```bash
pytest tests/ -x -q
```

Expected: All 277 tests pass (plus the 13 pre-existing TDD spec failures in `test_preserve_input_on_send_failure.py` and 3 string-mismatch failures — those are pre-existing and not our concern).

No commit needed. Proceed to Task 2.

---

### Task 2: S-06 — Save/restore `toolMapRef` in `switchSession`

**Bug:** When you switch sessions during a delegation, `toolMapRef` is not saved with the outgoing session's state and not restored when switching back. This means tool call cards lose their mapping and can't match incoming `tool_result` events to the correct UI element. The `blockMapRef` is already saved/restored correctly (lines 9371 and 9403) — `toolMapRef` was simply missed.

**Fix:** Add `savedToolMap` to the save object and restore it alongside `blockMapRef`. 2 lines total.

**Files:**
- Modify: `src/chat_plugin/static/index.html` (lines ~9371 and ~9403)
- Create: `tests/test_pr4_frontend_state.py`

**Step 1: Write the failing test**

Create `tests/test_pr4_frontend_state.py` with this exact content:

```python
"""
Structural tests for PR 4: Frontend State + Cleanup.

Uses string-matching against index.html (same pattern as test_delegate_ref_counting.py).
These tests verify that specific code patterns exist in the right locations.
"""

import pathlib

INDEX_HTML = (
    pathlib.Path(__file__).parent.parent
    / "src"
    / "chat_plugin"
    / "static"
    / "index.html"
)


def html():
    return INDEX_HTML.read_text()


# ---------------------------------------------------------------------------
# S-06 — toolMapRef saved/restored in switchSession
# ---------------------------------------------------------------------------


class TestToolMapRefSaveRestore:
    def test_switch_session_saves_tool_map(self):
        """switchSession must save toolMapRef alongside blockMapRef."""
        content = html()
        # Find the save block in switchSession (where savedBlockMap is set)
        save_marker = "savedBlockMap: { ...blockMapRef.current }"
        save_pos = content.find(save_marker)
        assert save_pos != -1, "savedBlockMap save not found in switchSession"
        # savedToolMap must appear near savedBlockMap (within same object literal)
        nearby = content[save_pos - 200 : save_pos + 200]
        assert "savedToolMap" in nearby, (
            "savedToolMap not found near savedBlockMap in switchSession save block"
        )

    def test_switch_session_restores_tool_map(self):
        """switchSession must restore toolMapRef from target.savedToolMap."""
        content = html()
        # Find the restore line for blockMapRef
        restore_marker = "blockMapRef.current = target.savedBlockMap"
        restore_pos = content.find(restore_marker)
        assert restore_pos != -1, "blockMapRef restore not found in switchSession"
        # toolMapRef restore must appear near blockMapRef restore
        nearby = content[restore_pos - 200 : restore_pos + 400]
        assert "toolMapRef.current = target.savedToolMap" in nearby, (
            "toolMapRef restore not found near blockMapRef restore in switchSession"
        )
```

**Step 2: Run the test to verify it fails**

```bash
pytest tests/test_pr4_frontend_state.py::TestToolMapRefSaveRestore -v
```

Expected: 2 FAILED — `savedToolMap not found` and `toolMapRef restore not found`.

**Step 3: Implement the fix**

In `src/chat_plugin/static/index.html`, find the session save block (line ~9371) inside `switchSession`. The object literal currently ends with `savedBlockMap`. Add `savedToolMap` right after it:

Find this exact code around line 9366–9372:
```javascript
          next.set(currentKey, {
            ...cur,
            savedItems: chronoItemsRef.current,
            savedTurnCount: turnCountRef.current,
            savedPlaceholderId: placeholderIdRef.current,
            savedBlockMap: { ...blockMapRef.current },
          });
```

Replace with:
```javascript
          next.set(currentKey, {
            ...cur,
            savedItems: chronoItemsRef.current,
            savedTurnCount: turnCountRef.current,
            savedPlaceholderId: placeholderIdRef.current,
            savedBlockMap: { ...blockMapRef.current },
            savedToolMap: { ...toolMapRef.current },
          });
```

Then find the restore line (line ~9403):
```javascript
      blockMapRef.current = target.savedBlockMap || {};
```

Add the `toolMapRef` restore immediately after it:
```javascript
      blockMapRef.current = target.savedBlockMap || {};
      toolMapRef.current = target.savedToolMap || {};
```

**Step 4: Run the test to verify it passes**

```bash
pytest tests/test_pr4_frontend_state.py::TestToolMapRefSaveRestore -v
```

Expected: 2 PASSED.

**Step 5: Commit**

```bash
git add src/chat_plugin/static/index.html tests/test_pr4_frontend_state.py
git commit -m "fix(S-06): save/restore toolMapRef in switchSession

toolMapRef was not saved when switching away from a session and not
restored when switching back. This caused tool_result events to lose
their mapping to ToolCallCard UI elements during delegation.

Mirrors the existing blockMapRef save/restore pattern."
```

---

### Task 3: S-05 — Defensive `cancelCountdown` in `resumeHistorySession`

**Bug:** `resumeHistorySession` (line ~9059) does not call `cancelCountdown()` before switching to the history session. If a countdown timer is active from the previous session, it keeps running and may fire `tryDrainQueue` for the wrong session. Both `newSession` (line 9029) and `switchSession` (line 9353) already call `cancelCountdown` — `resumeHistorySession` was missed.

**Fix:** Add `cancelCountdown()` call early in `resumeHistorySession`, before any state transitions.

**Files:**
- Modify: `src/chat_plugin/static/index.html` (line ~9064, inside `resumeHistorySession`)
- Modify: `tests/test_pr4_frontend_state.py`

**Step 1: Write the failing test**

Append this class to `tests/test_pr4_frontend_state.py`:

```python
# ---------------------------------------------------------------------------
# S-05 — cancelCountdown in resumeHistorySession
# ---------------------------------------------------------------------------


class TestCancelCountdownInResumeHistory:
    def test_resume_history_session_calls_cancel_countdown(self):
        """resumeHistorySession must call cancelCountdown() before state transitions."""
        content = html()
        fn_start = content.find("const resumeHistorySession = useCallback((key) => {")
        assert fn_start != -1, "resumeHistorySession function not found"
        # Scan the function body (first ~2000 chars)
        body = content[fn_start : fn_start + 2000]
        assert "cancelCountdown" in body, (
            "cancelCountdown() not called in resumeHistorySession"
        )

    def test_resume_history_cancel_countdown_before_active_key_set(self):
        """cancelCountdown must appear before activeKeyRef.current = key."""
        content = html()
        fn_start = content.find("const resumeHistorySession = useCallback((key) => {")
        assert fn_start != -1
        body = content[fn_start : fn_start + 2000]
        cancel_pos = body.find("cancelCountdown")
        key_set_pos = body.find("activeKeyRef.current = key")
        assert cancel_pos != -1, "cancelCountdown not found"
        assert key_set_pos != -1, "activeKeyRef assignment not found"
        assert cancel_pos < key_set_pos, (
            "cancelCountdown must come before activeKeyRef.current = key"
        )
```

**Step 2: Run the test to verify it fails**

```bash
pytest tests/test_pr4_frontend_state.py::TestCancelCountdownInResumeHistory -v
```

Expected: At least 1 FAILED — `cancelCountdown() not called in resumeHistorySession`.

**Step 3: Implement the fix**

In `src/chat_plugin/static/index.html`, find line ~9063 inside `resumeHistorySession`:

```javascript
      if (!target || !target.sessionId) return;

      if (transcriptFetchAbortRef.current) {
```

Replace with:

```javascript
      if (!target || !target.sessionId) return;

      // S-05: cancel any active countdown from the previous session before
      // transitioning state (mirrors cancelCountdown in newSession/switchSession)
      cancelCountdown();

      if (transcriptFetchAbortRef.current) {
```

**Step 4: Run the test to verify it passes**

```bash
pytest tests/test_pr4_frontend_state.py::TestCancelCountdownInResumeHistory -v
```

Expected: 2 PASSED.

**Step 5: Run full test suite**

```bash
pytest tests/ -x -q
```

Expected: Same pass count as baseline.

**Step 6: Commit**

```bash
git add src/chat_plugin/static/index.html tests/test_pr4_frontend_state.py
git commit -m "fix(S-05): add cancelCountdown to resumeHistorySession

resumeHistorySession was the only session-transition function that did
not cancel the countdown timer. A timer from the previous session could
fire tryDrainQueue after switching to a history session."
```

---

### Task 4: S-08 — Pass explicit `sourceKey` in buffered child event replay

**Bug:** When `session_fork` flushes buffered child events (line ~7768), it calls `handleWsMessage(bufferedMsg)` without passing a `sourceKey`. The function signature is `handleWsMessage(msg, sourceKey = null)`. Without the second argument, `ownerKey` defaults to `activeKeyRef.current`, which could be a different session if the user switched tabs while events were buffering.

**Fix:** Pass the parent session's key as `sourceKey` so events are routed to the correct session even if the user switched away.

**Files:**
- Modify: `src/chat_plugin/static/index.html` (line ~7768)
- Modify: `tests/test_pr4_frontend_state.py`

**Step 1: Write the failing test**

Append this class to `tests/test_pr4_frontend_state.py`:

```python
# ---------------------------------------------------------------------------
# S-08 — buffered child event replay passes sourceKey
# ---------------------------------------------------------------------------


class TestBufferedChildReplaySourceKey:
    def test_buffered_child_replay_passes_source_key(self):
        """Buffered child events must be replayed with an explicit sourceKey (2nd arg)."""
        content = html()
        # Find the buffered event flush in session_fork handler
        flush_marker = "pendingChildEventsRef.current.has(childId)"
        flush_pos = content.find(flush_marker)
        assert flush_pos != -1, "pendingChildEventsRef flush block not found"
        # Get the replay block (next ~300 chars)
        block = content[flush_pos : flush_pos + 300]
        # The handleWsMessage call must have a second argument (sourceKey)
        # It should NOT be just "handleWsMessage(bufferedMsg)" with no 2nd arg
        assert "handleWsMessage(bufferedMsg, " in block, (
            "handleWsMessage in buffered child replay must pass a sourceKey. "
            f"Found: {block!r}"
        )
```

**Step 2: Run the test to verify it fails**

```bash
pytest tests/test_pr4_frontend_state.py::TestBufferedChildReplaySourceKey -v
```

Expected: 1 FAILED — `handleWsMessage in buffered child replay must pass a sourceKey`.

**Step 3: Implement the fix**

In `src/chat_plugin/static/index.html`, find line ~7768:

```javascript
              handleWsMessage(bufferedMsg);
```

Replace with:

```javascript
              handleWsMessage(bufferedMsg, ownerKey);
```

The `ownerKey` variable is already available in scope — it's computed at line 7116 as `const ownerKey = sourceKey || activeKeyRef.current;` and represents the parent session that owns this `session_fork` event.

**Step 4: Run the test to verify it passes**

```bash
pytest tests/test_pr4_frontend_state.py::TestBufferedChildReplaySourceKey -v
```

Expected: 1 PASSED.

**Step 5: Commit**

```bash
git add src/chat_plugin/static/index.html tests/test_pr4_frontend_state.py
git commit -m "fix(S-08): pass ownerKey when replaying buffered child events

Buffered child events were replayed with handleWsMessage(bufferedMsg)
without a sourceKey, causing ownerKey to fall back to activeKeyRef.current.
If the user switched sessions while events were buffering, they'd be
routed to the wrong session."
```

---

### Task 5: S-10 — Remove duplicate `activeKeyRef` assignment in `switchSession`

**Bug:** `switchSession` sets `activeKeyRef.current = key` twice — once at line 9376 (before the save block) and again at line 9394 (in the restore block). The second assignment is redundant and confusing.

**Fix:** Delete the first (early) assignment at line 9376. Keep the one at line 9394 which is in the correct location (during the restore/activation phase).

**Files:**
- Modify: `src/chat_plugin/static/index.html` (line ~9376)
- Modify: `tests/test_pr4_frontend_state.py`

**Step 1: Write the failing test**

Append this class to `tests/test_pr4_frontend_state.py`:

```python
# ---------------------------------------------------------------------------
# S-10 — no duplicate activeKeyRef assignment in switchSession
# ---------------------------------------------------------------------------


class TestNoDuplicateActiveKeyRef:
    def test_switch_session_has_single_active_key_ref_assignment(self):
        """switchSession must set activeKeyRef.current = key exactly once."""
        content = html()
        fn_start = content.find("const switchSession = useCallback((key) => {")
        assert fn_start != -1, "switchSession function not found"
        # Find the end of switchSession (the closing }, [deps])
        fn_end = content.find("], [sessions, handleWsMessage, resumeHistorySession])", fn_start)
        if fn_end == -1:
            fn_end = fn_start + 5000
        body = content[fn_start:fn_end]
        count = body.count("activeKeyRef.current = key;")
        assert count == 1, (
            f"activeKeyRef.current = key appears {count} times in switchSession, expected 1"
        )
```

**Step 2: Run the test to verify it fails**

```bash
pytest tests/test_pr4_frontend_state.py::TestNoDuplicateActiveKeyRef -v
```

Expected: 1 FAILED — `activeKeyRef.current = key appears 2 times`.

**Step 3: Implement the fix**

In `src/chat_plugin/static/index.html`, find the FIRST occurrence of `activeKeyRef.current = key;` inside `switchSession`. It's at line ~9376, right after the save block closes (after `});` closing the `setSessions` call):

```javascript
      });
      }
      activeKeyRef.current = key;

      // Load target session
```

Remove the `activeKeyRef.current = key;` line so it becomes:

```javascript
      });
      }

      // Load target session
```

Keep the second occurrence at line ~9394, which is the real assignment in the restore phase.

**Step 4: Run the test to verify it passes**

```bash
pytest tests/test_pr4_frontend_state.py::TestNoDuplicateActiveKeyRef -v
```

Expected: 1 PASSED.

**Step 5: Commit**

```bash
git add src/chat_plugin/static/index.html tests/test_pr4_frontend_state.py
git commit -m "fix(S-10): remove duplicate activeKeyRef assignment in switchSession

activeKeyRef.current = key was set twice in switchSession. Removed the
first (early) assignment, keeping the one in the restore phase."
```

---

### Task 6: S-11 — Clear delegate refs in session lifecycle

**Bug:** `childToToolRef` and `childAgentRef` (declared at lines 6534 and 6536) accumulate entries across sessions and are never cleared. `resetSubSessionState` (line 6581) clears `subSessionsRef`, `subBlockMapRef`, and `subNextIndexRef` but not these two refs. Over many delegate-heavy sessions, this is a memory leak and can cause stale mappings.

**Fix:** Clear both refs in `resetSubSessionState`. This function is called by `newSession`, `switchSession`, and `resumeHistorySession` — so all session transitions are covered.

**Files:**
- Modify: `src/chat_plugin/static/index.html` (line ~6585, inside `resetSubSessionState`)
- Modify: `tests/test_pr4_frontend_state.py`

**Step 1: Write the failing test**

Append this class to `tests/test_pr4_frontend_state.py`:

```python
# ---------------------------------------------------------------------------
# S-11 — delegate refs cleared in resetSubSessionState
# ---------------------------------------------------------------------------


class TestDelegateRefsClearedOnReset:
    def test_reset_sub_session_state_clears_child_to_tool_ref(self):
        """resetSubSessionState must clear childToToolRef."""
        content = html()
        fn_start = content.find("function resetSubSessionState()")
        assert fn_start != -1, "resetSubSessionState not found"
        body = content[fn_start : fn_start + 500]
        assert "childToToolRef.current" in body, (
            "childToToolRef not cleared in resetSubSessionState"
        )

    def test_reset_sub_session_state_clears_child_agent_ref(self):
        """resetSubSessionState must clear childAgentRef."""
        content = html()
        fn_start = content.find("function resetSubSessionState()")
        assert fn_start != -1, "resetSubSessionState not found"
        body = content[fn_start : fn_start + 500]
        assert "childAgentRef.current" in body, (
            "childAgentRef not cleared in resetSubSessionState"
        )
```

**Step 2: Run the test to verify it fails**

```bash
pytest tests/test_pr4_frontend_state.py::TestDelegateRefsClearedOnReset -v
```

Expected: 2 FAILED.

**Step 3: Implement the fix**

In `src/chat_plugin/static/index.html`, find `resetSubSessionState` at line ~6581:

```javascript
    function resetSubSessionState() {
      subSessionsRef.current = new Map();
      subBlockMapRef.current = new Map();
      subNextIndexRef.current = new Map();
      if (subSessionRafRef.current) { cancelAnimationFrame(subSessionRafRef.current); subSessionRafRef.current = null; }
    }
```

Replace with:

```javascript
    function resetSubSessionState() {
      subSessionsRef.current = new Map();
      subBlockMapRef.current = new Map();
      subNextIndexRef.current = new Map();
      childToToolRef.current = {};
      childAgentRef.current = {};
      if (subSessionRafRef.current) { cancelAnimationFrame(subSessionRafRef.current); subSessionRafRef.current = null; }
    }
```

**Step 4: Run the test to verify it passes**

```bash
pytest tests/test_pr4_frontend_state.py::TestDelegateRefsClearedOnReset -v
```

Expected: 2 PASSED.

**Step 5: Commit**

```bash
git add src/chat_plugin/static/index.html tests/test_pr4_frontend_state.py
git commit -m "fix(S-11): clear childToToolRef/childAgentRef in resetSubSessionState

These refs accumulated entries across sessions and were never cleared.
resetSubSessionState now clears them, preventing memory growth and
stale delegate-to-tool mappings."
```

---

### Task 7: S-12 — Remove redundant `pinnedSet` filter guards

**Bug:** The keyboard navigation computation (lines ~9672–9686) builds `pinnedKeys` as a separate list, creates a `pinnedSet` from it, then filters group items with `.filter(k => !pinnedSet.has(k))`. But `directoryGroups`, `activityGroups`, and `ageGroups` are already built from `rootSessionEntries` which are filtered to exclude pinned sessions upstream. The `pinnedSet.has(k)` filter is redundant.

**Fix:** Remove the 3 redundant `.filter(k => !pinnedSet.has(k))` calls. The logic is `flatMap(g => g.items.map(([key]) => key))` — no filter needed.

**Files:**
- Modify: `src/chat_plugin/static/index.html` (lines ~9674, 9679, 9684)
- Modify: `tests/test_pr4_frontend_state.py`

**Step 1: Write the failing test**

Append this class to `tests/test_pr4_frontend_state.py`:

```python
# ---------------------------------------------------------------------------
# S-12 — redundant pinnedSet filter guards removed
# ---------------------------------------------------------------------------


class TestNoPinnedSetFilterGuards:
    def test_no_redundant_pinned_set_filter_in_keyboard_nav(self):
        """Keyboard nav block should not filter group items through pinnedSet."""
        content = html()
        # Find the keyboard navigation block
        marker = "Compute flat visual order of root session keys for keyboard navigation"
        block_start = content.find(marker)
        assert block_start != -1, "Keyboard navigation block not found"
        block = content[block_start : block_start + 800]
        # Count occurrences of the redundant filter pattern
        count = block.count(".filter(k => !pinnedSet.has(k))")
        assert count == 0, (
            f"Found {count} redundant .filter(k => !pinnedSet.has(k)) in keyboard nav block"
        )
```

**Step 2: Run the test to verify it fails**

```bash
pytest tests/test_pr4_frontend_state.py::TestNoPinnedSetFilterGuards -v
```

Expected: 1 FAILED — `Found 3 redundant .filter(k => !pinnedSet.has(k))`.

**Step 3: Implement the fix**

In `src/chat_plugin/static/index.html`, make three replacements in the keyboard navigation block (lines ~9673–9685).

Replace each of these three lines:

Line ~9674:
```javascript
          g.items.map(([key]) => key).filter(k => !pinnedSet.has(k))
```
with:
```javascript
          g.items.map(([key]) => key)
```

Line ~9679:
```javascript
          g.items.map(([key]) => key).filter(k => !pinnedSet.has(k))
```
with:
```javascript
          g.items.map(([key]) => key)
```

Line ~9684:
```javascript
          g.items.map(([key]) => key).filter(k => !pinnedSet.has(k))
```
with:
```javascript
          g.items.map(([key]) => key)
```

All three are the same change — remove `.filter(k => !pinnedSet.has(k))` from each.

**Step 4: Run the test to verify it passes**

```bash
pytest tests/test_pr4_frontend_state.py::TestNoPinnedSetFilterGuards -v
```

Expected: 1 PASSED.

**Step 5: Commit**

```bash
git add src/chat_plugin/static/index.html tests/test_pr4_frontend_state.py
git commit -m "fix(S-12): remove redundant pinnedSet filter guards in keyboard nav

directoryGroups, activityGroups, and ageGroups already exclude pinned
sessions upstream. The .filter(k => !pinnedSet.has(k)) calls were
redundant no-ops that added confusion."
```

---

### Task 8: S-09 — Chain toast on pin promise

**Bug:** The `'pin-session'` command palette handler (line ~10031) calls `handleTogglePin()` and `showToast()` sequentially. `handleTogglePin` is `async` (declared at line 8427), so it returns a Promise. The toast fires immediately, before the API call resolves. If the API call fails, the user sees "Session pinned" with no pin.

**Fix:** Chain the toast on the returned promise: `handleTogglePin(...).then(() => showToast(...))`.

**Files:**
- Modify: `src/chat_plugin/static/index.html` (lines ~10031–10032)

**Step 1: Implement the fix**

In `src/chat_plugin/static/index.html`, find the `pin-session` handler around line 10028–10033:

```javascript
          handler: () => {
            if (sessionIdRef.current) {
              const isPinned = cmdCtxRef.current.pinnedSessionIds.has(sessionIdRef.current);
              handleTogglePin(sessionIdRef.current, isPinned);
              showToast(isPinned ? 'Session unpinned' : 'Session pinned');
            }
          },
```

Replace with:

```javascript
          handler: () => {
            if (sessionIdRef.current) {
              const isPinned = cmdCtxRef.current.pinnedSessionIds.has(sessionIdRef.current);
              handleTogglePin(sessionIdRef.current, isPinned)
                .then(() => showToast(isPinned ? 'Session unpinned' : 'Session pinned'));
            }
          },
```

**Step 2: Run full test suite**

```bash
pytest tests/ -x -q
```

Expected: Same pass count as baseline.

**Step 3: Commit**

```bash
git add src/chat_plugin/static/index.html
git commit -m "fix(S-09): chain toast on pin/unpin promise resolution

The toast was firing before handleTogglePin's API call resolved. Now
the success toast only appears after the pin/unpin operation completes."
```

---

### Task 9: S-07 — Cache thinking item ID for `thinking_delta` sub-session lookup

**Bug:** The `thinking_delta` sub-session handler (line ~7584) uses `sub.content.slice().reverse().find(c => c.type === 'thinking' && c.streaming)` to locate the current thinking item. This copies the entire content array and reverses it on every delta event — O(n) per delta. For long sessions with many thinking blocks, this is unnecessarily expensive.

**Fix:** Add a `subLastThinkingIdRef` that maps `subKey → last thinking item ID`. Set it when a thinking block is created in `content_start` (line ~7347). Use it for direct lookup in `thinking_delta` instead of the reverse-find. Keep the reverse-find as a fallback.

**Files:**
- Modify: `src/chat_plugin/static/index.html` (lines ~6534 for ref declaration, ~7351 for content_start, ~7584 for thinking_delta)
- Modify: `tests/test_pr4_frontend_state.py`

**Step 1: Write the failing test**

Append this class to `tests/test_pr4_frontend_state.py`:

```python
# ---------------------------------------------------------------------------
# S-07 — thinking_delta cached lookup via subLastThinkingIdRef
# ---------------------------------------------------------------------------


class TestThinkingDeltaCachedLookup:
    def test_sub_last_thinking_id_ref_declared(self):
        """subLastThinkingIdRef must be declared as a useRef(new Map())."""
        assert "subLastThinkingIdRef" in html()

    def test_thinking_content_start_stores_id(self):
        """content_start for thinking blocks must store itemId in subLastThinkingIdRef."""
        content = html()
        # Find the thinking block creation in content_start sub-session path
        marker = "msg.block_type === 'thinking'"
        think_start = content.find(marker)
        assert think_start != -1, "thinking block_type check not found in content_start"
        nearby = content[think_start : think_start + 400]
        assert "subLastThinkingIdRef" in nearby, (
            "subLastThinkingIdRef not updated when creating thinking block"
        )

    def test_thinking_delta_uses_cached_id(self):
        """thinking_delta sub-session path must use subLastThinkingIdRef for lookup."""
        content = html()
        # Find the thinking_delta sub-session block
        delta_case = "case 'thinking_delta':"
        delta_pos = content.find(delta_case)
        assert delta_pos != -1, "thinking_delta case not found"
        block = content[delta_pos : delta_pos + 500]
        assert "subLastThinkingIdRef" in block, (
            "thinking_delta does not use subLastThinkingIdRef for cached lookup"
        )
```

**Step 2: Run the test to verify it fails**

```bash
pytest tests/test_pr4_frontend_state.py::TestThinkingDeltaCachedLookup -v
```

Expected: 3 FAILED — `subLastThinkingIdRef` doesn't exist yet.

**Step 3: Implement the fix**

**3a. Declare the ref.**

In `src/chat_plugin/static/index.html`, find the ref declarations around line 6536:

```javascript
    const childAgentRef = useRef({});
    const sessionParentByIdRef = useRef({});
```

Add the new ref between them:

```javascript
    const childAgentRef = useRef({});
    const subLastThinkingIdRef = useRef(new Map()); // subKey -> last thinking item ID
    const sessionParentByIdRef = useRef({});
```

**3b. Store the ID in content_start.**

In `src/chat_plugin/static/index.html`, find the thinking block creation in the sub-session `content_start` handler (line ~7346–7354):

```javascript
              } else if (msg.block_type === 'thinking') {
                const itemId = makeId();
                const subIdx = subNextIndexRef.current.get(subKey) ?? 0;
                subNextIndexRef.current.set(subKey, subIdx + 1);
                const blockMap = subBlockMapRef.current.get(subKey);
                if (blockMap) blockMap.set('thinking-id-' + subIdx, itemId);
                addSubSessionContent(subKey, {
                  id: itemId, type: 'thinking', content: '', streaming: true,
                });
```

Add the caching line after the `blockMap.set` and before `addSubSessionContent`:

```javascript
              } else if (msg.block_type === 'thinking') {
                const itemId = makeId();
                const subIdx = subNextIndexRef.current.get(subKey) ?? 0;
                subNextIndexRef.current.set(subKey, subIdx + 1);
                const blockMap = subBlockMapRef.current.get(subKey);
                if (blockMap) blockMap.set('thinking-id-' + subIdx, itemId);
                subLastThinkingIdRef.current.set(subKey, itemId);
                addSubSessionContent(subKey, {
                  id: itemId, type: 'thinking', content: '', streaming: true,
                });
```

**3c. Use cached ID in thinking_delta.**

Find the `thinking_delta` sub-session handler (line ~7581–7589):

```javascript
          {
            const subKey = resolveSubSessionKey(msg);
            if (subKey) {
              updateSubSessionContent(subKey, sub => {
                const item = sub.content.slice().reverse().find(c => c.type === 'thinking' && c.streaming);
                if (item) item.content += msg.delta;
              });
              break;
            }
          }
```

Replace with:

```javascript
          {
            const subKey = resolveSubSessionKey(msg);
            if (subKey) {
              const thinkItemId = subLastThinkingIdRef.current.get(subKey);
              updateSubSessionContent(subKey, sub => {
                // Use cached ID for O(1) lookup; fall back to reverse-find for edge cases
                const item = thinkItemId
                  ? sub.content.find(c => c.id === thinkItemId)
                  : sub.content.slice().reverse().find(c => c.type === 'thinking' && c.streaming);
                if (item) item.content += msg.delta;
              });
              break;
            }
          }
```

**3d. Clear the ref in resetSubSessionState.**

Find `resetSubSessionState` (which you modified in Task 6):

```javascript
    function resetSubSessionState() {
      subSessionsRef.current = new Map();
      subBlockMapRef.current = new Map();
      subNextIndexRef.current = new Map();
      childToToolRef.current = {};
      childAgentRef.current = {};
      if (subSessionRafRef.current) { cancelAnimationFrame(subSessionRafRef.current); subSessionRafRef.current = null; }
    }
```

Add the clear for the new ref:

```javascript
    function resetSubSessionState() {
      subSessionsRef.current = new Map();
      subBlockMapRef.current = new Map();
      subNextIndexRef.current = new Map();
      subLastThinkingIdRef.current = new Map();
      childToToolRef.current = {};
      childAgentRef.current = {};
      if (subSessionRafRef.current) { cancelAnimationFrame(subSessionRafRef.current); subSessionRafRef.current = null; }
    }
```

**Step 4: Run the test to verify it passes**

```bash
pytest tests/test_pr4_frontend_state.py::TestThinkingDeltaCachedLookup -v
```

Expected: 3 PASSED.

**Step 5: Run full test suite**

```bash
pytest tests/ -x -q
```

Expected: Same pass count as baseline.

**Step 6: Commit**

```bash
git add src/chat_plugin/static/index.html tests/test_pr4_frontend_state.py
git commit -m "fix(S-07): cache thinking item ID for O(1) sub-session delta lookup

thinking_delta used slice().reverse().find() to locate the current
thinking item on every delta — O(n) per event. Now caches the last
thinking item ID per sub-session in subLastThinkingIdRef and looks
it up directly. Falls back to reverse-find for edge cases."
```

---

### Task 10: S-02 — Dev mode attribute rename `sessions_dir` → `projects_dir`

**Bug:** The dev server (`__main__.py`) has a `_MockSettings` class with attribute `sessions_dir` (line 19). The actual codebase (`__init__.py` line 33) reads `projects_dir` from `state.settings`. The mismatch means the dev server's `--sessions-dir` CLI flag has no effect — the extracted value is always `None`.

**Fix:** Rename in 3 places: the class attribute, the argparse flag, and the `args` access.

**Files:**
- Modify: `src/chat_plugin/__main__.py` (lines 19, 34, 49–50)
- Create: `tests/test_dev_server_settings.py`

**Step 1: Write the failing test**

Create `tests/test_dev_server_settings.py` with this exact content:

```python
"""Tests for S-02: dev mode attribute mismatch (_MockSettings uses wrong name)."""

import pathlib

MAIN_PY = (
    pathlib.Path(__file__).parent.parent
    / "src"
    / "chat_plugin"
    / "__main__.py"
)


def source():
    return MAIN_PY.read_text()


class TestDevServerProjectsDir:
    def test_mock_settings_uses_projects_dir(self):
        """_MockSettings must have projects_dir attribute, not sessions_dir."""
        content = source()
        assert "projects_dir" in content, "projects_dir not found in __main__.py"
        # Verify sessions_dir is NOT used as an attribute
        assert "sessions_dir" not in content, (
            "sessions_dir still found in __main__.py — should be renamed to projects_dir"
        )

    def test_argparse_flag_is_projects_dir(self):
        """CLI flag must be --projects-dir, not --sessions-dir."""
        content = source()
        assert "--projects-dir" in content, "--projects-dir flag not found"
        assert "--sessions-dir" not in content, (
            "--sessions-dir flag still present — rename to --projects-dir"
        )
```

**Step 2: Run the test to verify it fails**

```bash
pytest tests/test_dev_server_settings.py -v
```

Expected: 2 FAILED — `sessions_dir still found` and `--sessions-dir flag still present`.

**Step 3: Implement the fix**

In `src/chat_plugin/__main__.py`, make these 3 changes:

**Line 19** — change the class attribute:
```python
    sessions_dir: Path | None = None
```
to:
```python
    projects_dir: Path | None = None
```

**Lines 33–35** — change the argparse flag:
```python
    parser.add_argument(
        "--sessions-dir",
        type=Path,
        default=None,
        help="Path to sessions directory for history scanning",
    )
```
to:
```python
    parser.add_argument(
        "--projects-dir",
        type=Path,
        default=None,
        help="Path to projects directory for history scanning",
    )
```

**Lines 49–50** — change the args access:
```python
    if args.sessions_dir:
        state.settings.sessions_dir = args.sessions_dir
```
to:
```python
    if args.projects_dir:
        state.settings.projects_dir = args.projects_dir
```

**Step 4: Run the test to verify it passes**

```bash
pytest tests/test_dev_server_settings.py -v
```

Expected: 2 PASSED.

**Step 5: Run full test suite**

```bash
pytest tests/ -x -q
```

Expected: Same pass count as baseline.

**Step 6: Commit**

```bash
git add src/chat_plugin/__main__.py tests/test_dev_server_settings.py
git commit -m "fix(S-02): rename sessions_dir to projects_dir in dev server

_MockSettings.sessions_dir didn't match the real settings attribute
name (projects_dir), so the --sessions-dir CLI flag had no effect.
Renamed to projects_dir in all 3 places."
```

---

### Task 11: S-26 — Add DOMPurify to vendor bundle and replace `sanitizeHtml`

This is the largest task. It has 6 sub-steps: create the build tooling, rebuild vendor.js, swap the sanitizer, update .gitignore, create AGENTS.md, and verify.

**Bug:** The `sanitizeHtml` function (line 3527) is a hand-rolled HTML sanitizer that strips dangerous tags and event handlers via DOM manipulation. It's fragile and will miss edge cases that a battle-tested library like DOMPurify handles. The `TODO` comment on line 3526 already says "Replace with DOMPurify in vendor.js for production use".

**Fix:** Add DOMPurify to the vendor bundle, replace `sanitizeHtml`'s body with a one-liner that calls `DOMPurify.sanitize()`, and commit the build tooling so the vendor process is reproducible.

**Files:**
- Create: `scripts/vendor-entry.js`
- Create: `scripts/build-vendor.sh`
- Modify: `src/chat_plugin/static/vendor.js` (rebuilt by script)
- Modify: `src/chat_plugin/static/index.html` (line ~3525–3546)
- Modify: `.gitignore`
- Create: `AGENTS.md`

**Step 1: Create `scripts/vendor-entry.js`**

Create the file `scripts/vendor-entry.js` with this exact content:

```javascript
/**
 * vendor-entry.js — declares all frontend dependencies for the vendor bundle.
 *
 * To add a new dependency:
 *   1. npm install <package>
 *   2. Add an import + window assignment below
 *   3. Run ./scripts/build-vendor.sh
 *   4. Commit the updated vendor.js
 *
 * See AGENTS.md for the full process.
 */

// --- Preact (UI framework) ---
import * as preact from 'preact';
import * as preactHooks from 'preact/hooks';
window.preact = preact;
window.preactHooks = preactHooks;

// --- htm (tagged template JSX alternative) ---
import { html } from 'htm/preact';
window.html = html;

// --- marked (Markdown parser) ---
import { marked } from 'marked';
window.marked = marked;

// --- DOMPurify (HTML sanitizer) ---
import DOMPurify from 'dompurify';
window.DOMPurify = DOMPurify;
```

**Step 2: Create `scripts/build-vendor.sh`**

Create the file `scripts/build-vendor.sh` with this exact content:

```bash
#!/bin/bash
# build-vendor.sh — rebuild vendor.js with all frontend dependencies.
#
# Usage:
#   npm install          # one-time, installs preact/htm/marked/dompurify
#   ./scripts/build-vendor.sh
#
# This produces the minified vendor.js that index.html loads via <script> tag.
# The vendor.js file is committed to the repo. node_modules/ is not.
#
# See AGENTS.md "Frontend Dependencies" for the full process.
set -euo pipefail
cd "$(dirname "$0")/.."

OUTFILE="src/chat_plugin/static/vendor.js"

# Check that dependencies are installed
if [ ! -d "node_modules/preact" ]; then
  echo "Error: node_modules not found. Run 'npm install' first."
  echo "  npm install preact@10 htm@3 marked@9 dompurify@3 esbuild"
  exit 1
fi

npx --yes esbuild \
  scripts/vendor-entry.js \
  --bundle \
  --outfile="$OUTFILE" \
  --format=iife \
  --minify \
  --banner:js="// vendor.js — vendored frontend bundle for amplifier-chat
// Libraries: preact@10.x, htm@3.x, marked@9.x, dompurify@3.x
// Built: $(date +%Y-%m-%d)
// To rebuild: npm install && ./scripts/build-vendor.sh
// See AGENTS.md for details"

echo "✓ vendor.js rebuilt: $OUTFILE ($(wc -c < "$OUTFILE" | tr -d ' ') bytes)"
```

Make it executable:

```bash
chmod +x scripts/build-vendor.sh
```

**Step 3: Install dependencies and rebuild vendor.js**

```bash
cd /Users/samule/repo/amplifier-chat
npm install preact@10 htm@3 marked@9 dompurify@3 esbuild
./scripts/build-vendor.sh
```

Expected output: `✓ vendor.js rebuilt: src/chat_plugin/static/vendor.js (XXXXX bytes)`

Verify the rebuilt vendor.js works by checking it contains DOMPurify:

```bash
grep -c "DOMPurify" src/chat_plugin/static/vendor.js
```

Expected: A number > 0 (DOMPurify is mentioned in the banner and/or the bundle code).

Also verify the existing dependencies are still exposed:

```bash
grep "window.preact=" src/chat_plugin/static/vendor.js && echo "preact: OK"
grep "window.preactHooks=" src/chat_plugin/static/vendor.js && echo "preactHooks: OK"
grep "window.html=" src/chat_plugin/static/vendor.js && echo "html: OK"
grep "window.marked=" src/chat_plugin/static/vendor.js && echo "marked: OK"
grep "window.DOMPurify=" src/chat_plugin/static/vendor.js && echo "DOMPurify: OK"
```

Expected: All 5 print "OK". If any are missing, the `vendor-entry.js` is wrong — fix it and rebuild.

**Step 4: Replace `sanitizeHtml` function body**

In `src/chat_plugin/static/index.html`, find the `sanitizeHtml` function (lines ~3525–3546):

```javascript
  // Simple HTML sanitizer — strips dangerous tags and event handlers
  // TODO: Replace with DOMPurify in vendor.js for production use
  function sanitizeHtml(html) {
    const div = document.createElement('div');
    div.innerHTML = html;
    // Remove dangerous tags including style, base, meta, form
    const dangerous = div.querySelectorAll('script,iframe,object,embed,link,style,meta,base,form');
    dangerous.forEach(el => el.remove());
    // Remove dangerous attributes (event handlers, unsafe URLs)
    const UNSAFE_ATTRS = ['src', 'href', 'action', 'formaction', 'data', 'xlink:href'];
    const UNSAFE_PROTO = /^\s*(javascript|data|vbscript):/i;  // \s* handles whitespace bypass
    const allEls = div.querySelectorAll('*');
    allEls.forEach(el => {
      Array.from(el.attributes).forEach(attr => {
        if (attr.name.startsWith('on') ||
            (UNSAFE_ATTRS.includes(attr.name) && UNSAFE_PROTO.test(attr.value))) {
          el.removeAttribute(attr.name);
        }
      });
    });
    return div.innerHTML;
  }
```

Replace the entire function with:

```javascript
  // HTML sanitizer — delegates to DOMPurify (vendored in vendor.js)
  function sanitizeHtml(htmlContent) {
    return window.DOMPurify.sanitize(htmlContent);
  }
```

Note: The parameter is renamed to `htmlContent` to avoid shadowing the `html` variable from `htm/preact` that's in the outer scope.

**Step 5: Add `node_modules/` to `.gitignore`**

In `.gitignore`, add `node_modules/` at the end (after the existing entries). The file currently ends with `.worktrees/` at line 35. Add:

```

# Node.js (vendor rebuild tooling)
node_modules/
package-lock.json
package.json
```

**Step 6: Create `AGENTS.md` at project root**

Create `AGENTS.md` in the project root with this exact content:

```markdown
# AGENTS.md — Project Context for AI Agents

## Project Overview

amplifier-chat is a browser-based chat plugin for the Amplifier platform. It consists of:

- **Frontend:** A single-file Preact SPA (`src/chat_plugin/static/index.html`, ~10,600 lines)
- **Backend:** Python FastAPI server (10 `.py` files in `src/chat_plugin/`, ~2,500 lines total)
- **Vendor bundle:** `src/chat_plugin/static/vendor.js` — minified JS bundle of frontend dependencies

## Frontend Dependencies (Vendor Bundle)

**IMPORTANT:** This project vendors its frontend dependencies into a single `vendor.js` file. There is NO webpack, vite, or CI build pipeline. The committed `vendor.js` IS the deliverable.

### Current vendored libraries

| Library | Version | Purpose |
|---------|---------|---------|
| preact | 10.x | UI framework (React-compatible) |
| htm | 3.x | Tagged template JSX alternative |
| marked | 9.x | Markdown parser |
| dompurify | 3.x | HTML sanitizer |

### How to add or update a frontend dependency

1. Edit `scripts/vendor-entry.js` — add/remove/update the import and `window.*` assignment
2. Install the npm package: `npm install <package>@<version>`
3. Rebuild: `./scripts/build-vendor.sh`
4. Verify the build succeeded and the new export appears: `grep "window.YourLib=" src/chat_plugin/static/vendor.js`
5. Commit the updated `vendor.js` (the minified output)

**Do NOT commit `node_modules/`, `package.json`, or `package-lock.json`.** These are in `.gitignore`. The `npm install` step is only needed locally for rebuilding.

### How `vendor.js` works

```
index.html loads vendor.js via <script> tag (line ~2736)
  → vendor.js sets window.preact, window.preactHooks, window.html, window.marked, window.DOMPurify
  → index.html destructures at lines 2739–2742: const { h, render } = window.preact; etc.
  → All SPA code uses these globals directly
```

### Build script details

- `scripts/vendor-entry.js` — declares all imports and window assignments
- `scripts/build-vendor.sh` — runs esbuild to produce the minified bundle
- Output: `src/chat_plugin/static/vendor.js`

## Testing

- **Python tests:** `pytest tests/ -x` (277 passing baseline)
- **Frontend structural tests:** Tests in `tests/test_*.py` that read `index.html` as text and assert code patterns exist (string matching, not execution)
- **Browser testing:** Start daemon with `uv run --extra dev amplifierd serve --log-level debug --port 8410`, navigate to `http://localhost:8410/chat/`

## Key Architecture Notes

- The SPA is a **single file** (`index.html`). All Preact components, state management, API client, and styles are in this one file.
- The backend serves static files and provides REST + SSE endpoints. No server-side rendering.
- Session events arrive via Server-Sent Events (SSE), not WebSocket.
- Sub-session (delegate) events arrive on the parent session's SSE stream with a `child_session_id` field.
```

**Step 7: Write the structural test for DOMPurify integration**

Append this class to `tests/test_pr4_frontend_state.py`:

```python
# ---------------------------------------------------------------------------
# S-26 — DOMPurify integration
# ---------------------------------------------------------------------------


class TestDOMPurifyIntegration:
    def test_sanitize_html_uses_dompurify(self):
        """sanitizeHtml must delegate to DOMPurify.sanitize."""
        content = html()
        fn_start = content.find("function sanitizeHtml(")
        assert fn_start != -1, "sanitizeHtml function not found"
        body = content[fn_start : fn_start + 200]
        assert "DOMPurify" in body, (
            "sanitizeHtml does not reference DOMPurify"
        )

    def test_sanitize_html_is_concise(self):
        """sanitizeHtml should be a thin wrapper, not the old hand-rolled version."""
        content = html()
        fn_start = content.find("function sanitizeHtml(")
        assert fn_start != -1
        # The old version had querySelectorAll, UNSAFE_ATTRS, etc.
        body = content[fn_start : fn_start + 500]
        assert "querySelectorAll" not in body, (
            "sanitizeHtml still contains the old hand-rolled DOM manipulation"
        )

    def test_vendor_js_contains_dompurify(self):
        """vendor.js must expose DOMPurify on the window object."""
        import pathlib
        vendor_js = (
            pathlib.Path(__file__).parent.parent
            / "src"
            / "chat_plugin"
            / "static"
            / "vendor.js"
        ).read_text()
        assert "DOMPurify" in vendor_js, "DOMPurify not found in vendor.js"
```

**Step 8: Run all PR 4 tests**

```bash
pytest tests/test_pr4_frontend_state.py tests/test_dev_server_settings.py -v
```

Expected: All tests PASSED.

**Step 9: Run full test suite**

```bash
pytest tests/ -x -q
```

Expected: Same pass count as baseline.

**Step 10: Commit everything**

```bash
git add scripts/vendor-entry.js scripts/build-vendor.sh \
  src/chat_plugin/static/vendor.js src/chat_plugin/static/index.html \
  .gitignore AGENTS.md tests/test_pr4_frontend_state.py
git commit -m "fix(S-26): replace hand-rolled sanitizer with DOMPurify

- Add DOMPurify to vendor.js bundle
- Replace sanitizeHtml body with DOMPurify.sanitize() one-liner
- Commit build tooling: scripts/vendor-entry.js + scripts/build-vendor.sh
- Add AGENTS.md documenting the vendor dependency process
- Add node_modules/ to .gitignore

All 9 existing sanitizeHtml call sites are unchanged — the function
signature is preserved, only the implementation swaps in DOMPurify."
```

---

### Task 12: Final verification and tag

**Step 1: Run the complete test suite**

```bash
pytest tests/ -x -q
```

Expected: Same pass count as baseline (277 passing + pre-existing failures unchanged).

**Step 2: Review the commit log**

```bash
git log --oneline main..HEAD
```

Expected: 10 commits, one per task (branch creation has no commit):

```
HASH fix(S-26): replace hand-rolled sanitizer with DOMPurify
HASH fix(S-02): rename sessions_dir to projects_dir in dev server
HASH fix(S-07): cache thinking item ID for O(1) sub-session delta lookup
HASH fix(S-09): chain toast on pin/unpin promise resolution
HASH fix(S-12): remove redundant pinnedSet filter guards in keyboard nav
HASH fix(S-11): clear childToToolRef/childAgentRef in resetSubSessionState
HASH fix(S-10): remove duplicate activeKeyRef assignment in switchSession
HASH fix(S-08): pass ownerKey when replaying buffered child events
HASH fix(S-05): add cancelCountdown to resumeHistorySession
HASH fix(S-06): save/restore toolMapRef in switchSession
```

**Step 3: Verify no unexpected file changes**

```bash
git diff --stat main..HEAD
```

Expected files changed:
- `AGENTS.md` (new)
- `.gitignore` (modified)
- `scripts/build-vendor.sh` (new)
- `scripts/vendor-entry.js` (new)
- `src/chat_plugin/__main__.py` (modified)
- `src/chat_plugin/static/index.html` (modified)
- `src/chat_plugin/static/vendor.js` (modified)
- `tests/test_dev_server_settings.py` (new)
- `tests/test_pr4_frontend_state.py` (new)

**Step 4: Push and create PR**

```bash
git push -u origin fix/frontend-state-cleanup
```

Then create the PR:

```bash
gh pr create \
  --title "fix: frontend state management + DOMPurify integration (PR 4/4)" \
  --body "## Summary

Fixes 10 frontend bugs identified in the comprehensive bugfix analysis.

### Changes

| ID | Fix | Lines |
|---|---|---|
| S-06 | Save/restore toolMapRef in switchSession | 2 |
| S-05 | Defensive cancelCountdown in resumeHistorySession | 2 |
| S-08 | Pass sourceKey in buffered child event replay | 1 |
| S-10 | Remove duplicate activeKeyRef assignment | -1 |
| S-11 | Clear delegate refs in session lifecycle | 4 |
| S-12 | Remove redundant pinnedSet filter guards | -3 |
| S-09 | Chain toast on pin/unpin promise | 2 |
| S-07 | Cache thinking item ID for delta lookup | ~8 |
| S-02 | Dev mode attribute rename (sessions_dir → projects_dir) | 3 |
| S-26 | DOMPurify integration + vendor build tooling | ~40 |

### Testing
- All existing pytest tests pass
- New structural tests in test_pr4_frontend_state.py and test_dev_server_settings.py
- Browser-operator: session switching during delegation, markdown rendering

### Design doc
docs/superpowers/specs/2026-03-26-amplifier-chat-comprehensive-bugfix-design.md (PR 4 section)

Depends on: PR 3 (fix/event-pipeline) must be merged first." \
  --base main
```

---

## Browser-Operator Verification (Post-PR)

After the PR is merged, run these browser-operator integration tests:

1. **Session switching during delegation (S-06):** Start a multi-delegate prompt, switch to another session, switch back. Verify tool call cards still render correctly and `tool_result` events match their UI elements.

2. **Countdown timer (S-05):** Start a queued session, then click a history session. Verify no countdown fires for the old session.

3. **Markdown rendering (S-26):** Send a prompt that generates markdown with code blocks, links, images, and tables. Verify all render correctly with DOMPurify (no stripped content, no XSS).

4. **Pin/unpin keyboard shortcut (S-09):** Use Cmd+Shift+P to pin a session. Verify the toast appears AFTER the pin indicator shows in the sidebar (not before).

5. **Search after many sessions (S-11, S-12):** Create several delegate-heavy sessions, then search. Verify no stale delegate mappings in search results and keyboard navigation works correctly.
