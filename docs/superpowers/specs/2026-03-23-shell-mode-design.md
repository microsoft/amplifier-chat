# Shell Mode for Amplifier Chat

**Date:** 2026-03-23
**Status:** Design

## Summary

Add direct shell command execution to Amplifier Chat via a `!` prefix. When the user types `!` as the first character, the input area transforms into a terminal-like mode. On send, the command bypasses the AI entirely and executes directly. The output renders using the existing `ToolCallCard` component as a synthetic bash tool call, making the command and its output part of the session transcript so the AI can reference them on subsequent turns.

## Motivation

Users frequently need to run quick shell commands (git status, ls, grep) without waiting for an AI round-trip. Currently they must switch to a separate terminal. This feature keeps them in the chat flow while clearly distinguishing shell interactions from AI conversations.

## Prior Art

Research across Claude Code, Codex CLI, Cursor, Windsurf, and GitHub Copilot CLI showed two existing patterns:

1. **AI-mediated execution** (Claude Code, Codex): The AI runs bash as tool calls. Output is part of the transcript. No user-initiated bypass.
2. **Separate terminal pane** (Cursor, Windsurf): Terminal is a different view with optional "add to context" bridges.

This design is novel: user-initiated shell execution rendered inline as synthetic tool calls, combining the contextual awareness of pattern 1 with the direct control of pattern 2.

## Design

### 1. Input Detection and Mode Switching

When the user types `!` as the first character in the textarea, the input area immediately transitions into "shell mode."

**Trigger:** `handleInput` detects the textarea value starts with `!` (and it's the first character, not mid-text).

**Revert:** When the user deletes back past the `!` (textarea value no longer starts with `!`), the input reverts to normal chat mode.

### 2. Input Area Visual Transformation ("Terminal Morph")

The transition is animated with CSS transitions (~200ms ease-out) to feel responsive but not jarring.

**Changes when shell mode activates:**

| Element | Normal Mode | Shell Mode |
|---------|-------------|------------|
| Textarea border | `var(--border)`, blue on focus | `var(--accent-green)` with faint glow: `box-shadow: 0 0 8px rgba(34,197,94,0.15)` |
| Textarea font | System font (inherited) | Monospace: `'SF Mono', 'Cascadia Code', 'Fira Code', monospace` |
| Textarea content | User sees their text | The `!` prefix is hidden/consumed; a `$` prompt indicator appears to the left of the textarea (or as a pseudo-element/badge) |
| Send button label | "Send" | "Run" |
| Send button color | `var(--accent-blue)` | `var(--accent-green)` |
| Placeholder | "Message... (/ for commands)" | "command..." |

**CSS tokens (new):**

```css
:root {
  --shell-border: var(--accent-green);
  --shell-glow: rgba(34, 197, 94, 0.15);
  --shell-font: 'SF Mono', 'Cascadia Code', 'Fira Code', monospace;
}
```

**Light theme:** Same structure. The green border (`--accent-green` light variant: `#16a34a`) provides sufficient contrast on light backgrounds. Glow is reduced: `rgba(22, 163, 74, 0.1)`.

**Animation spec:**

- All properties transition with `200ms ease-out` on activation
- Revert transitions with `150ms ease-in` (slightly faster feels natural)
- Rapid toggling (type `!` then immediately delete): the shorter revert duration prevents visual stutter
- Properties animated: `border-color`, `box-shadow`, `font-family`, `background-color` (send button), `color` (send button)

### 3. Command Execution Flow

When the user hits Enter (or clicks "Run") in shell mode:

1. **Strip prefix:** Remove the `!` from the textarea value to get the raw command
2. **Clear input:** Reset textarea, revert to normal mode
3. **Send to backend:** POST to a new endpoint (or reuse `/command`) with the shell command
4. **Inject synthetic SSE events:** The backend emits:
   - `tool:pre` event with `{ name: 'bash', arguments: { command: '<the command>' } }`
   - Execute the command
   - `tool:post` event with the command output as the result
5. **UI renders via existing `ToolCallCard`:** The command appears as a collapsible tool call card, identical to AI-initiated bash calls

### 4. Output Rendering

The output uses the existing `ToolCallCard` component with one addition:

**User-initiated indicator:** The tool card header shows a small badge or label to distinguish user-initiated commands from AI-initiated ones.

| Origin | Tool Header Display |
|--------|-------------------|
| AI-initiated bash | `bash` + arg preview |
| User-initiated shell | `bash` + arg preview + `(user)` badge in `--text-muted` |

The `(user)` badge is a `<span>` styled with muted color and smaller font, positioned after the tool name.

**Existing rendering handles:**
- Collapsible expand/collapse (click header to toggle)
- `tool-result-text` for plain text output
- `tool-result-smart` for markdown-formatted output
- Error styling (`.tool-error-text`) for failed commands
- Max-height with scroll for long output (`max-height: 300px; overflow: auto`)

**Error states:** Non-zero exit codes render with the existing `tool-error-text` styling (red-tinted). The tool status icon shows error state.

### 5. Transcript Integration

The synthetic tool call events are injected into the session's event stream, making them part of the transcript. This means:

- The AI can reference previous shell output on subsequent turns ("I see you ran `git status` and there are unstaged changes...")
- Shell commands appear in session history when revisiting the session
- The `transcriptToChronoItems` function already handles `tool_call` type items, so no changes needed to the transcript parser

**Transcript structure of a shell command:**

```json
{
  "role": "assistant",
  "content": [
    {
      "type": "tool_use",
      "name": "bash",
      "input": { "command": "ls -la" },
      "id": "user_shell_<uuid>",
      "user_initiated": true
    }
  ]
}
```

Followed by a tool result:

```json
{
  "role": "tool",
  "tool_use_id": "user_shell_<uuid>",
  "content": "<command output>"
}
```

The `user_initiated: true` flag allows the frontend to render the `(user)` badge and allows the backend to distinguish these from AI-initiated calls if needed.

### 6. Backend Endpoint

**Option A (preferred): New dedicated endpoint**

```
POST /api/sessions/{session_id}/shell
Body: { "command": "ls -la" }
Response: SSE stream with tool:pre, tool:post events
```

This keeps shell execution separate from the AI execution path (`/execute/stream`) while reusing the same SSE event format.

**Option B: Extend the existing `/command` endpoint**

Add a `shell` command type alongside existing slash commands. Less clean separation but fewer new routes.

Recommendation: Option A for clean architecture.

### 7. Additional Behaviors

**Working directory:** Shell commands execute in the active session's CWD (the value shown in the CWD picker at the top of the chat). The backend passes this as the `cwd` parameter when spawning the subprocess.

**Streaming output:** For long-running commands (e.g., `!npm install`, `!pytest`), output streams to the UI in real-time via SSE chunks rather than buffering until completion. Each chunk appends to the `ToolCallCard` result area. The tool status shows "running" (spinner) until the command exits.

**Multi-line commands:** Shift+Enter in shell mode inserts a newline (same as normal mode). The full multi-line text is sent as a single bash command. This supports small inline scripts.

**The `$` prompt implementation:** The `!` character remains in the textarea value (it's the mode trigger). It is visually hidden using CSS (`text-indent` or `padding-left` to make room for the `$` pseudo-element). On send, the `!` is stripped programmatically. This avoids complex value manipulation while the user is typing.

### 8. Security Considerations

- Shell commands execute with the same permissions as the Amplifier Chat backend process
- The same safety guardrails that apply to AI-initiated bash calls should apply here (blocked destructive commands, timeouts)
- Commands should have a default timeout (30 seconds) with the output streamed as it arrives
- No elevated privileges beyond what the user already has in their terminal

### 8. Scope and Non-Goals

**In scope:**
- `!` prefix detection and input mode switching
- Animated input transformation
- Direct command execution (no AI round-trip)
- Output rendering via existing `ToolCallCard`
- Transcript integration
- Backend shell execution endpoint
- Light and dark theme support

**Not in scope (future work):**
- Command history / autocomplete in shell mode
- Persistent shell session (each command is independent)
- piping shell output to AI ("Share with AI" action)
- Custom shell selection (always uses default shell)
- Tab completion

## Known Gaps (v1 → v2)

These are identified limitations in the initial implementation that should be addressed in a follow-up iteration.

### P0: Transcript Persistence
Shell commands and output are **not persisted** to the session's `events.jsonl`. They exist only in frontend memory and vanish on page refresh or session revisit. The AI cannot reference previous shell output on subsequent turns. Fix requires the backend to inject synthetic events into the session event log via amplifierd's session system.

### P0: Kill / Cancel Running Commands
There is no way for the user to cancel a running shell command. Long-running commands (`npm install`, `pytest`) block until the 30-second timeout fires. Need a "Kill" button on the tool card while status is `running`, wired to a `DELETE /api/sessions/{id}/shell/{tool_call_id}` endpoint that kills the subprocess.

### P1: Interactive Command Detection
Commands that require stdin (`vim`, `python3`, `ssh`) hang silently until timeout. Should detect common interactive commands and either warn the user before execution or refuse with a helpful message.

### P1: Dangerous Command Guardrails
No safety checks on user-initiated shell commands. The AI-initiated bash tool blocks destructive commands (`rm -rf /`, etc.) -- shell mode should apply the same blocklist, or at minimum show a confirmation prompt for flagged commands.

### P2: Concurrent Command Prevention
Nothing prevents firing a second shell command while one is already running. Both would stream simultaneously. Should either queue commands or disable the shell input while a command is in-flight.

### P2: Environment Variable Persistence
Each `!` command spawns a fresh subprocess. `export FOO=bar` followed by `echo $FOO` in the next `!` won't work. Consider a persistent shell session or at minimum document this limitation clearly.

### P2: Large Output Memory
Output accumulates as a string in frontend memory. A `cat` of a very large file could bloat the page. Consider truncating output beyond a threshold (e.g., 100KB) with a "Show full output" toggle.

### P3: Binary Output Handling
Commands producing binary output (`cat image.png`) show garbled text. Should detect non-UTF-8 output and display a message like "Binary output (N bytes)" instead.

## Component Changes

| File | Change |
|------|--------|
| `index.html` (CSS) | Add `.shell-mode` styles, CSS transitions, `$` prompt badge, new CSS tokens |
| `index.html` (InputArea) | Detect `!` prefix in `handleInput`, toggle shell mode state, modify `doSend` to route shell commands |
| `index.html` (ToolCallCard) | Add `(user)` badge rendering when `user_initiated` flag is present |
| `routes.py` | New `/api/sessions/{session_id}/shell` endpoint |
| Backend (new) | Shell execution logic with SSE event injection |
