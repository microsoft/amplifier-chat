# Per-Session Input Drafts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Each session remembers its own input draft (text + pending images) independently, so switching sessions saves the current draft and restores the target session's draft instantly.

**Architecture:** Self-contained inside the `InputArea` component. A `draftsRef` (Map<sessionKey, DraftState>) stores drafts in memory. The existing `useEffect([activeKey])` is extended to save the outgoing draft and restore the incoming draft on every session switch. A `pendingImagesRef` mirrors the `pendingImages` state to avoid stale closures.

**Tech Stack:** Preact + HTM (inline, no build step), uncontrolled textarea via ref

---

## File Structure

**Single file modified:** `src/chat_plugin/static/index.html`

All changes are inside the `InputArea` function component (lines 4813-5185).

| Change Area | Lines | What Changes |
|-------------|-------|--------------|
| InputArea refs | ~4814-4816 | Add `draftsRef`, `prevKeyRef`, `pendingImagesRef` |
| InputArea useEffect([activeKey]) | ~4829-4838 | Extend to save/restore drafts |
| InputArea doSend | ~4869-4894 | Clear draft for active session after send |

---

### Task 1: Add Draft Infrastructure (refs)

**Files:**
- Modify: `src/chat_plugin/static/index.html` (inside `InputArea`, after line 4816)

- [ ] **Step 1: Add three refs after the existing `pendingImages` state declaration (line 4816)**

After `const [pendingImages, setPendingImages] = useState([]);` add:

```javascript
    const draftsRef = useRef(new Map());
    const prevKeyRef = useRef(activeKey);
    const pendingImagesRef = useRef(pendingImages);
    pendingImagesRef.current = pendingImages;
```

- `draftsRef`: Map<sessionKey, { text: string, images: string[], cursorPos: number }>
- `prevKeyRef`: Tracks the outgoing session key so the useEffect knows which draft to save
- `pendingImagesRef`: Mirrors `pendingImages` state to avoid stale closure in the useEffect (which only depends on `[activeKey]`, not `pendingImages`)

The `pendingImagesRef.current = pendingImages` line runs on every render, keeping the ref fresh.

- [ ] **Step 2: Verify no syntax errors**

Open the app in browser, confirm it loads without console errors. Input area should render normally.

- [ ] **Step 3: Commit**

```bash
git add src/chat_plugin/static/index.html
git commit -m "feat(drafts): add draft infrastructure refs to InputArea"
```

---

### Task 2: Save and Restore Drafts on Session Switch

**Files:**
- Modify: `src/chat_plugin/static/index.html` (InputArea useEffect, ~lines 4829-4838)

- [ ] **Step 1: Replace the existing `useEffect([activeKey])` with draft-aware version**

Replace the current effect (lines 4829-4838):
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

With:
```javascript
    useEffect(() => {
      const ta = textareaRef.current;
      if (!ta) return;

      // Save outgoing session's draft
      const prevKey = prevKeyRef.current;
      if (prevKey && prevKey !== activeKey) {
        const text = ta.value;
        const images = pendingImagesRef.current;
        if (text || images.length > 0) {
          draftsRef.current.set(prevKey, {
            text,
            images: [...images],
            cursorPos: ta.selectionStart,
          });
        } else {
          draftsRef.current.delete(prevKey);
        }
      }

      // Restore incoming session's draft
      const draft = draftsRef.current.get(activeKey);
      if (draft) {
        ta.value = draft.text || '';
        setPendingImages(draft.images || []);
      } else {
        ta.value = '';
        setPendingImages([]);
      }

      prevKeyRef.current = activeKey;

      // Auto-resize textarea to fit restored content, then focus
      const rafId = window.requestAnimationFrame(() => {
        ta.style.height = 'auto';
        ta.style.height = Math.min(ta.scrollHeight, 200) + 'px';
        try { ta.focus(); } catch {}
        // Restore cursor position after focus
        if (draft && draft.cursorPos != null) {
          ta.selectionStart = ta.selectionEnd = Math.min(draft.cursorPos, ta.value.length);
        }
      });
      return () => window.cancelAnimationFrame(rafId);
    }, [activeKey]);
```

Key behaviors:
- **Save outgoing**: Only when switching (prevKey !== activeKey). Captures text, images (shallow copy), cursor position. Deletes entry if draft is empty (no text, no images).
- **Restore incoming**: If a draft exists, sets textarea value and pendingImages. If no draft, clears both (clean slate for new sessions).
- **Auto-resize**: After restoring content, adjusts textarea height so multi-line drafts display correctly.
- **Cursor restore**: Puts cursor back where user left it, clamped to content length.

- [ ] **Step 2: Manual verification**

1. Open app, create/open two sessions (A and B)
2. Type "hello from A" in session A's input
3. Switch to session B -- input should be empty
4. Type "hello from B" in session B's input
5. Switch back to A -- should see "hello from A"
6. Switch to B -- should see "hello from B"
7. Clear B's input, switch away, switch back -- input should be empty (draft cleaned up)
8. Create a new session -- input should be empty

- [ ] **Step 3: Commit**

```bash
git add src/chat_plugin/static/index.html
git commit -m "feat(drafts): save and restore drafts on session switch"
```

---

### Task 3: Clear Draft After Successful Send

**Files:**
- Modify: `src/chat_plugin/static/index.html` (InputArea doSend, ~lines 4869-4894)

- [ ] **Step 1: Add draft cleanup to doSend**

In the `doSend` callback, after the lines that clear the textarea and pendingImages (both the queue path and the normal send path), add a draft cleanup call.

In the queue send path (after line 4881 `setPendingImages([])`), add:
```javascript
          draftsRef.current.delete(activeKey);
```

In the normal send path (after line 4892 `setPendingImages([])`), add:
```javascript
      draftsRef.current.delete(activeKey);
```

Also add `activeKey` to the `useCallback` dependency array (line 4894):
```javascript
    }, [onSend, onQueueMessage, pendingImages, shouldQueue, activeKey]);
```

This ensures that after sending a message, the draft for that session is cleaned up so it doesn't zombie-restore on next switch.

- [ ] **Step 2: Manual verification**

1. Type "test message" in session A
2. Switch to B (draft saved for A)
3. Switch back to A -- see "test message" restored
4. Send the message
5. Switch to B, then back to A -- input should be empty (draft was cleared on send)

- [ ] **Step 3: Commit**

```bash
git add src/chat_plugin/static/index.html
git commit -m "feat(drafts): clear draft after successful send or queue"
```

---

## Edge Cases (Handled by Design)

| Scenario | Behavior | Why |
|----------|----------|-----|
| New session created | Input clears (no draft exists for new key) | `draftsRef.current.get(newKey)` returns undefined -> clears |
| Session deleted | N/A -- no delete feature exists | No cleanup needed |
| Empty draft | Not stored (Map.delete on save) | Prevents unbounded memory growth |
| History session resumed | Same `activeKey` change path | `resumeHistorySession` sets new `activeKey` -> triggers same effect |
| Voice transcription appends text | Captured naturally on next switch | DOM value includes transcribed text; saved on switch |
| Image pasted then switch | Images saved in draft.images | `pendingImagesRef.current` captures current images |
| Send clears draft | `draftsRef.current.delete(activeKey)` in doSend | No zombie restoration |

## Future Extensions

- **Draft indicator in sidebar**: Add `onDraftChange` callback prop. InputArea calls it whenever draftsRef changes. SessionCard shows a pencil icon.
- **localStorage persistence**: Serialize draftsRef.current to localStorage on save, hydrate on app load. Note: images are base64 data URLs which can be large -- consider storing text-only drafts in localStorage and discarding image drafts.
- **File attachment drafts**: When file attachments are added alongside images, extend the draft shape: `{ text, images, files, cursorPos }`.
