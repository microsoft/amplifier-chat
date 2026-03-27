# PR 2: Backend Reliability — Implementation Plan

> **Execution:** Use the subagent-driven-development workflow to implement this plan.

**Goal:** Fix 10 backend reliability bugs spanning race conditions, atomicity, thread safety, logging, and correctness in the Python backend.

**Architecture:** All changes are in the Python backend (`src/chat_plugin/`). Fixes are independent and ordered to minimize conflicts — simple renames/deletions first, then correctness fixes, then atomicity/thread-safety, then the largest refactor (S-15), and finally the feedback flow change (S-17). Each task produces a self-contained commit.

**Tech Stack:** Python 3.12+, FastAPI, pytest, `tmp_path` fixtures for disk-based tests.

**Branch:** `fix/backend-reliability` (branch from `main` after PR 1 is merged)

**Design doc:** `docs/superpowers/specs/2026-03-26-amplifier-chat-comprehensive-bugfix-design.md` (PR 2 section)

**Test runner:** `uv run pytest tests/ -x` (293 tests baseline)

---

## Preliminary: Create the branch

```bash
git checkout main && git pull
git checkout -b fix/backend-reliability
```

---

## Task 1: S-02 — Dev Mode Attribute Mismatch

**Bug:** `__main__.py` defines `_MockSettings.sessions_dir` but `create_router()` reads `settings.projects_dir`. The dev server's `--sessions-dir` flag silently does nothing.

**Files:**
- Modify: `src/chat_plugin/__main__.py` (lines 19, 34, 50)
- Test: `tests/test_main_dev_mode.py` (create)

**Step 1: Write the failing test**

Create `tests/test_main_dev_mode.py`:

```python
"""Tests for __main__.py dev server configuration."""


def test_mock_settings_has_projects_dir():
    """S-02: _MockSettings must expose projects_dir, not sessions_dir."""
    from chat_plugin.__main__ import _MockSettings

    settings = _MockSettings()
    assert hasattr(settings, "projects_dir"), (
        "_MockSettings should have 'projects_dir' attribute "
        "(not 'sessions_dir') to match what create_router() reads"
    )
    assert settings.projects_dir is None


def test_mock_settings_no_sessions_dir():
    """S-02: The old sessions_dir attribute should not exist."""
    from chat_plugin.__main__ import _MockSettings

    settings = _MockSettings()
    assert not hasattr(settings, "sessions_dir"), (
        "_MockSettings should NOT have 'sessions_dir' — "
        "it was renamed to 'projects_dir'"
    )
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_main_dev_mode.py -v
```

Expected: FAIL — `_MockSettings` currently has `sessions_dir`, not `projects_dir`.

**Step 3: Apply the fix**

In `src/chat_plugin/__main__.py`, make these 3 changes:

1. **Line 19** — class attribute rename:
   - Old: `sessions_dir: Path | None = None`
   - New: `projects_dir: Path | None = None`

2. **Line 34** — argparse flag rename:
   - Old: `"--sessions-dir",`
   - New: `"--projects-dir",`

3. **Line 49-50** — argument usage rename:
   - Old: `if args.sessions_dir:` / `state.settings.sessions_dir = args.sessions_dir`
   - New: `if args.projects_dir:` / `state.settings.projects_dir = args.projects_dir`

Also update the help text on line 37:
   - Old: `help="Path to sessions directory for history scanning",`
   - New: `help="Path to projects directory for history scanning",`

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_main_dev_mode.py -v
```

Expected: PASS

**Step 5: Run full suite**

```bash
uv run pytest tests/ -x
```

Expected: All 293+ tests pass.

**Step 6: Commit**

```bash
git add src/chat_plugin/__main__.py tests/test_main_dev_mode.py
git commit -m "fix(S-02): rename sessions_dir to projects_dir in dev server

_MockSettings.sessions_dir did not match what create_router() reads
(settings.projects_dir), so the --sessions-dir CLI flag silently did nothing.
Rename in 3 places: class attribute, argparse flag, and args usage."
```

---

## Task 2: S-23 — Stale Docstring Removal

**Bug:** `scan_sessions()` docstring references a removed `ensure_ids` parameter (lines 290-292).

**Files:**
- Modify: `src/chat_plugin/session_history.py` (lines 290-292)

**Step 1: Delete the stale paragraph**

In `src/chat_plugin/session_history.py`, delete these 3 lines (290-292):

```python
    If *ensure_ids* is provided, any session IDs in that set that fall outside
    the pagination window are appended so they are always returned (e.g. pinned
    sessions whose mtime has drifted past the page boundary).
```

These lines are between the `pinned_ids` parameter doc and the `Returns:` section. After deletion, the `Returns:` section follows directly after the `pinned_ids` parameter doc.

**Step 2: Verify no tests break**

```bash
uv run pytest tests/test_session_history.py -v
```

Expected: All session history tests pass (docstring-only change).

**Step 3: Commit**

```bash
git add src/chat_plugin/session_history.py
git commit -m "fix(S-23): remove stale ensure_ids docstring from scan_sessions

The ensure_ids parameter was replaced by pinned_ids but the old docstring
paragraph was never removed."
```

---

## Task 3: S-24 — Add Logging to Command Handlers

**Bug:** Five command handlers in `commands.py` silently swallow exceptions with bare `except: pass`. Failures are invisible.

**Files:**
- Modify: `src/chat_plugin/commands.py` (lines 2, 162, 180, 204, 216, 304)
- Test: `tests/test_commands.py` (add test)

**Step 1: Write the failing test**

Add to `tests/test_commands.py`:

```python
def test_tools_command_logs_exception_on_failure(processor_with_mock_session, caplog):
    """S-24: Command handlers must log exceptions, not swallow silently."""
    import logging

    # Make coordinator.get("tools") raise
    processor_with_mock_session._session_manager.get.return_value.session.coordinator.get.side_effect = (
        RuntimeError("kaboom")
    )
    with caplog.at_level(logging.ERROR, logger="chat_plugin.commands"):
        processor_with_mock_session.handle_command("tools", [], session_id="abc")

    assert any("kaboom" in r.message for r in caplog.records), (
        "Expected the exception to be logged via logger.exception()"
    )
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_commands.py::test_tools_command_logs_exception_on_failure -v
```

Expected: FAIL — no logging happens because exceptions are silently swallowed.

**Step 3: Add logging to commands.py**

In `src/chat_plugin/commands.py`:

1. **Add import and logger** near the top (after `from pathlib import Path`):

```python
import logging

logger = logging.getLogger(__name__)
```

2. **`_cmd_clear` (line 162)** — use `logger.warning()` (AttributeError from missing context service is normal flow):

Replace:
```python
        except Exception:
            pass  # best effort
```
With:
```python
        except Exception:
            logger.warning(
                "Could not clear context for session %s", session_id, exc_info=True
            )
```

3. **`_cmd_tools` (line 180)** — use `logger.exception()`:

Replace:
```python
        except Exception:
            tool_list = []
```
With:
```python
        except Exception:
            logger.exception("Failed to list tools for session %s", session_id)
            tool_list = []
```

4. **`_cmd_agents` (line 204)** — use `logger.exception()`:

Replace:
```python
        except Exception:
            agent_list = []
```
With:
```python
        except Exception:
            logger.exception("Failed to list agents for session %s", session_id)
            agent_list = []
```

5. **`_cmd_config` (line 216)** — use `logger.exception()`:

Replace:
```python
        except Exception:
            cfg = {}
```
With:
```python
        except Exception:
            logger.exception("Failed to read config for session %s", session_id)
            cfg = {}
```

6. **`_cmd_modes` (line 304)** — use `logger.exception()`:

Replace:
```python
        except Exception:
            return {"type": "modes", "modes": [], "active_mode": None}
```
With:
```python
        except Exception:
            logger.exception("Failed to list modes for session %s", session_id)
            return {"type": "modes", "modes": [], "active_mode": None}
```

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_commands.py::test_tools_command_logs_exception_on_failure -v
```

Expected: PASS

**Step 5: Run full command tests**

```bash
uv run pytest tests/test_commands.py -v
```

Expected: All command tests pass.

**Step 6: Commit**

```bash
git add src/chat_plugin/commands.py tests/test_commands.py
git commit -m "fix(S-24): add logging to command handlers that silently swallow exceptions

Add logger.exception() to _cmd_tools, _cmd_agents, _cmd_config, _cmd_modes.
Use logger.warning() for _cmd_clear (AttributeError from missing context
service is expected normal flow)."
```

---

## Task 4: S-13 — Hidden Session Leak in Revisions

**Bug:** `scan_session_revisions()` returns hidden sessions. The history endpoint filters them out, but the revisions endpoint doesn't — so hidden analysis sessions appear in the frontend's revision poll.

**Files:**
- Modify: `src/chat_plugin/session_history.py` (line ~378)
- Test: `tests/test_session_history.py` (add test)

**Step 1: Write the failing test**

Add to `tests/test_session_history.py`:

```python
def test_scan_session_revisions_excludes_hidden(tmp_path):
    """S-13: Hidden sessions must not appear in revision results."""
    _make_session(
        tmp_path,
        "visible-sess",
        transcript='{"role": "user", "content": "hi"}\n',
    )
    _make_session(
        tmp_path,
        "hidden-sess",
        transcript='{"role": "user", "content": "secret"}\n',
        metadata={"hidden": True},
    )
    rows = scan_session_revisions(tmp_path)
    ids = {r["session_id"] for r in rows}
    assert "visible-sess" in ids
    assert "hidden-sess" not in ids, (
        "Hidden sessions must be excluded from revision results"
    )
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_session_history.py::test_scan_session_revisions_excludes_hidden -v
```

Expected: FAIL — `hidden-sess` currently appears in results.

**Step 3: Add the hidden check**

In `src/chat_plugin/session_history.py`, in the `scan_session_revisions` function, find this block (around line 378):

```python
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if isinstance(metadata, dict):
                if isinstance(metadata.get("name"), str) and metadata["name"]:
```

Add the hidden check right after `if isinstance(metadata, dict):` and before the name check:

```python
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if isinstance(metadata, dict):
                if metadata.get("hidden") is True:
                    continue
                if isinstance(metadata.get("name"), str) and metadata["name"]:
```

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_session_history.py::test_scan_session_revisions_excludes_hidden -v
```

Expected: PASS

**Step 5: Run full session history tests**

```bash
uv run pytest tests/test_session_history.py -v
```

Expected: All pass.

**Step 6: Commit**

```bash
git add src/chat_plugin/session_history.py tests/test_session_history.py
git commit -m "fix(S-13): exclude hidden sessions from scan_session_revisions

Hidden analysis sessions (created by the feedback endpoint) were leaking
into the revisions poll. Add metadata.get('hidden') check in the revision
scan loop, matching the filter already used by scan_sessions."
```

---

## Task 5: S-14 — `has_more` Pagination Bug

**Bug:** `has_more` uses `offset + limit < total_count`, but `total_count` counts ALL session directories on disk (before content filtering). After filtering removes empty/hidden sessions, the client may paginate past the actual end.

**Files:**
- Modify: `src/chat_plugin/routes.py` (line 121)
- Test: `tests/test_routes.py` (add test)

**Step 1: Write the failing test**

Add to `tests/test_routes.py`:

```python
def test_has_more_accounts_for_filtering(client, tmp_path, state):
    """S-14: has_more should reflect filtered results, not raw disk count."""
    import json

    state.settings.projects_dir = tmp_path

    # Create 3 sessions: 2 with content, 1 empty (will be filtered out)
    for name in ["sess-with-content-1", "sess-with-content-2"]:
        sess_dir = tmp_path / "-Users-test" / "sessions" / name
        sess_dir.mkdir(parents=True, exist_ok=True)
        (sess_dir / "transcript.jsonl").write_text(
            json.dumps({"role": "user", "content": "hi"}) + "\n",
            encoding="utf-8",
        )

    # Empty session — no transcript content, will be filtered out
    empty_dir = tmp_path / "-Users-test" / "sessions" / "sess-empty"
    empty_dir.mkdir(parents=True, exist_ok=True)
    (empty_dir / "transcript.jsonl").write_text("", encoding="utf-8")

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from chat_plugin import create_router

    app = FastAPI()
    router = create_router(state)
    app.include_router(router)
    c = TestClient(app)

    # Request with limit=2: we get exactly 2 content sessions
    # has_more should be False because there are only 2 visible sessions
    resp = c.get("/chat/api/sessions/history?limit=2&offset=0")
    assert resp.status_code == 200
    data = resp.json()
    visible = [s for s in data["sessions"] if not s.get("pinned")]
    assert len(visible) == 2
    assert data["has_more"] is False, (
        "has_more should be False when filtered results < limit"
    )
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_routes.py::test_has_more_accounts_for_filtering -v
```

Expected: FAIL — `has_more` is currently True because `total_count` is 3 (includes the empty session).

**Step 3: Fix the has_more formula**

In `src/chat_plugin/routes.py`, line 121, change:

```python
            "has_more": offset + limit < total_count,
```

to:

```python
            "has_more": len(sessions) == limit,
```

**IMPORTANT:** The `sessions` variable here is the one from line 110 — the filtered regular (non-pinned) sessions list. NOT the combined `pinned_sessions + sessions` list. This is correct because `sessions` is reassigned on line 110 to the filtered version.

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_routes.py::test_has_more_accounts_for_filtering -v
```

Expected: PASS

**Step 5: Run full route tests**

```bash
uv run pytest tests/test_routes.py -v
```

Expected: All pass.

**Step 6: Commit**

```bash
git add src/chat_plugin/routes.py tests/test_routes.py
git commit -m "fix(S-14): has_more pagination uses filtered count instead of raw total

has_more was computed as offset+limit < total_count, but total_count
includes empty/hidden sessions that get filtered out. Changed to
len(sessions) == limit which correctly reflects whether more filtered
results exist beyond the current page."
```

---

## Task 6: S-21 — Search Results Missing Pinned Flag

**Bug:** The search endpoint (`/api/sessions/search`) returns results without a `pinned` field, unlike the history endpoint. The frontend can't show pin indicators on search results.

**Files:**
- Modify: `src/chat_plugin/routes.py` (lines 131-140)
- Test: `tests/test_routes.py` (add test)

**Step 1: Write the failing test**

Add to `tests/test_routes.py`:

```python
def test_search_results_include_pinned_flag(client, tmp_path, state):
    """S-21: Search results must include a 'pinned' boolean flag."""
    import json

    state.settings.projects_dir = tmp_path

    # Create two sessions with searchable content
    for name in ["sess-pinned", "sess-unpinned"]:
        sess_dir = tmp_path / "-Users-test" / "sessions" / name
        sess_dir.mkdir(parents=True, exist_ok=True)
        (sess_dir / "transcript.jsonl").write_text(
            json.dumps({"role": "user", "content": "searchable content"}) + "\n",
            encoding="utf-8",
        )
        (sess_dir / "metadata.json").write_text(
            json.dumps({"name": f"Session {name}"}),
            encoding="utf-8",
        )

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from chat_plugin import create_router

    app = FastAPI()
    router = create_router(state)
    app.include_router(router)
    c = TestClient(app)

    # Pin one session
    c.post("/chat/api/sessions/sess-pinned/pin")

    # Search for both
    resp = c.get("/chat/api/sessions/search?q=searchable")
    assert resp.status_code == 200
    data = resp.json()
    sessions = data["sessions"]
    assert len(sessions) >= 2

    pinned_row = next(s for s in sessions if s["session_id"] == "sess-pinned")
    unpinned_row = next(s for s in sessions if s["session_id"] == "sess-unpinned")

    assert pinned_row["pinned"] is True, "Pinned session should have pinned=True"
    assert unpinned_row["pinned"] is False, "Unpinned session should have pinned=False"
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_routes.py::test_search_results_include_pinned_flag -v
```

Expected: FAIL — `pinned` key doesn't exist on search results.

**Step 3: Add pinned flag to search results**

In `src/chat_plugin/routes.py`, in the `search_session_history` function, find:

```python
        results = [row for row in results if _has_content(row)]
        return {"sessions": results, "query": q}
```

Replace with:

```python
        results = [row for row in results if _has_content(row)]
        pinned_ids = pin_storage.list_pins()
        for row in results:
            row["pinned"] = row["session_id"] in pinned_ids
        return {"sessions": results, "query": q}
```

Note: `pin_storage` is already in scope — it's a parameter of `create_history_routes()` which encloses the `search_session_history` function.

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_routes.py::test_search_results_include_pinned_flag -v
```

Expected: PASS

**Step 5: Run full route tests**

```bash
uv run pytest tests/test_routes.py -v
```

Expected: All pass.

**Step 6: Commit**

```bash
git add src/chat_plugin/routes.py tests/test_routes.py
git commit -m "fix(S-21): add pinned flag to search results

The search endpoint (/api/sessions/search) was missing the 'pinned'
boolean that the history endpoint includes. Added pin_storage.list_pins()
lookup and tagging to search results."
```

---

## Task 7: S-19 — Atomic Voice Settings Write

**Bug:** `_save_voice_settings()` uses a direct `write_text()`, which can produce a truncated file on crash. Should use the tmp+rename pattern like `PinStorage._save()`.

**Files:**
- Modify: `src/chat_plugin/voice.py` (lines 73-78)
- Test: `tests/test_voice_settings.py` (create)

**Step 1: Write the failing test**

Create `tests/test_voice_settings.py`:

```python
"""Tests for voice settings atomicity."""

import json
from pathlib import Path
from unittest.mock import patch


def test_save_voice_settings_uses_atomic_write(tmp_path):
    """S-19: _save_voice_settings must use tmp+rename for atomicity."""
    settings_file = tmp_path / "voice-settings.json"

    with (
        patch("chat_plugin.voice._SETTINGS_DIR", tmp_path),
        patch("chat_plugin.voice._VOICE_SETTINGS_FILE", settings_file),
    ):
        from chat_plugin.voice import _save_voice_settings

        _save_voice_settings({"stt_model": "base", "tts_voice": "en-US-AriaNeural"})

    # File should exist with correct content
    assert settings_file.exists()
    data = json.loads(settings_file.read_text())
    assert data["stt_model"] == "base"

    # No .tmp file should be left behind
    tmp_files = list(tmp_path.glob("*.tmp"))
    assert tmp_files == [], f"Leftover .tmp files found: {tmp_files}"
```

**Step 2: Run test to verify it passes (baseline — the test checks correctness, not atomicity directly)**

```bash
uv run pytest tests/test_voice_settings.py -v
```

Expected: PASS (current code writes correctly, just not atomically). The real protection is against crash-time corruption, which we can't easily test. The test validates the contract.

**Step 3: Apply the atomic write fix**

In `src/chat_plugin/voice.py`, replace the `_save_voice_settings` function (lines 73-78):

```python
def _save_voice_settings(settings: dict) -> None:
    """Persist voice settings."""
    import json

    _SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    _VOICE_SETTINGS_FILE.write_text(json.dumps(settings, indent=2))
```

With:

```python
def _save_voice_settings(settings: dict) -> None:
    """Persist voice settings atomically (tmp + rename)."""
    import json

    _SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _VOICE_SETTINGS_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    os.rename(tmp, _VOICE_SETTINGS_FILE)
```

Note: `os` is already imported at the top of `voice.py` (line 9).

**Step 4: Run test to verify it still passes**

```bash
uv run pytest tests/test_voice_settings.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/chat_plugin/voice.py tests/test_voice_settings.py
git commit -m "fix(S-19): use atomic tmp+rename for voice settings persistence

_save_voice_settings() used a direct write_text() that could produce a
truncated file on crash. Now uses the same tmp+rename pattern as
PinStorage._save()."
```

---

## Task 8: S-18 — Whisper Model Thread Safety

**Bug:** `_get_whisper_model()` has a check-then-act race: two concurrent requests can both see `_whisper_model is None` and create duplicate model instances (each ~150 MB). Same issue with `update_voice_settings` and `delete_stt_model` clearing the cached model.

**Files:**
- Modify: `src/chat_plugin/voice.py` (lines 38-39, 86-110, 336-338, 417-419)
- Test: `tests/test_voice_settings.py` (add test)

**Step 1: Write the test**

Add to `tests/test_voice_settings.py`:

```python
def test_whisper_lock_exists():
    """S-18: voice.py must have a module-level _whisper_lock for thread safety."""
    import threading

    from chat_plugin import voice

    assert hasattr(voice, "_whisper_lock"), (
        "voice.py must define _whisper_lock = threading.Lock()"
    )
    assert isinstance(voice._whisper_lock, type(threading.Lock()))
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_voice_settings.py::test_whisper_lock_exists -v
```

Expected: FAIL — `_whisper_lock` doesn't exist yet.

**Step 3: Add thread safety**

In `src/chat_plugin/voice.py`:

1. **Add threading import** at the top (after `import os`, line 9):

```python
import threading
```

2. **Add lock** after the model cache variables (after line 39):

```python
_whisper_lock = threading.Lock()
```

3. **Double-check locking in `_get_whisper_model`** — replace the entire function (lines 86-110):

```python
def _get_whisper_model(model_name: str) -> WhisperModel:
    """Get or create the whisper model (thread-safe singleton)."""
    global _whisper_model, _whisper_model_name

    # Fast path — no lock needed for the common case
    if _whisper_model is not None and _whisper_model_name == model_name:
        return _whisper_model

    with _whisper_lock:
        # Re-check after acquiring the lock (double-check locking)
        if _whisper_model is not None and _whisper_model_name == model_name:
            return _whisper_model

        # Check if model file exists, download if not
        models_dir = _models_dir()
        model_file = models_dir / f"ggml-{model_name}.bin"

        if not model_file.exists():
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "model_not_downloaded",
                    "model": model_name,
                    "message": f"Whisper model '{model_name}' not found. Use POST /chat/voice/download-model to download it first.",
                },
            )

        _whisper_model = WhisperModel(
            str(model_file), n_threads=min(os.cpu_count() or 4, 8)
        )
        _whisper_model_name = model_name
        return _whisper_model
```

4. **Guard `update_voice_settings` cache clear** (lines 336-338 inside the route function). Find:

```python
            global _whisper_model, _whisper_model_name
            _whisper_model = None
            _whisper_model_name = ""
```

Replace with:

```python
            with _whisper_lock:
                global _whisper_model, _whisper_model_name
                _whisper_model = None
                _whisper_model_name = ""
```

Note: The `global` declaration must stay inside the function but can go inside the `with` block. If the linter complains about `global` placement, move the `global` declaration to the top of the enclosing function body and keep only the assignments inside the `with` block.

5. **Guard `delete_stt_model` cache clear** (lines 417-419 inside the route function). Find:

```python
        if _whisper_model_name == model_name:
            _whisper_model = None
            _whisper_model_name = ""
```

Replace with:

```python
        with _whisper_lock:
            if _whisper_model_name == model_name:
                _whisper_model = None
                _whisper_model_name = ""
```

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_voice_settings.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/chat_plugin/voice.py tests/test_voice_settings.py
git commit -m "fix(S-18): add thread safety to whisper model singleton

_get_whisper_model() had a check-then-act race where concurrent requests
could create duplicate model instances (~150 MB each). Added double-check
locking with threading.Lock. Also guarded the cache clear in
update_voice_settings and delete_stt_model."
```

---

## Task 9: S-15 — Extract Shared Helpers (Atomic Write + Patch Forked Metadata)

**Bug:** `_patch_forked_metadata` is duplicated in `routes.py` and `commands.py` with slightly different signatures. Both use a non-atomic `write_text()` for metadata. Extract to a shared module with atomic writes.

**Files:**
- Create: `src/chat_plugin/session_utils.py`
- Modify: `src/chat_plugin/routes.py` (lines 318-363)
- Modify: `src/chat_plugin/commands.py` (lines 63-105)
- Test: `tests/test_session_utils.py` (create)

**Step 1: Write the failing test**

Create `tests/test_session_utils.py`:

```python
"""Tests for shared session utilities."""

import json
from pathlib import Path


def test_atomic_write_json(tmp_path):
    """S-15: atomic_write_json must use tmp+rename pattern."""
    from chat_plugin.session_utils import atomic_write_json

    target = tmp_path / "test.json"
    atomic_write_json(target, {"key": "value"})

    assert target.exists()
    data = json.loads(target.read_text())
    assert data == {"key": "value"}

    # No leftover .tmp files
    tmp_files = list(tmp_path.glob("*.tmp"))
    assert tmp_files == []


def test_atomic_write_json_creates_parent_dirs(tmp_path):
    """atomic_write_json should create parent directories if needed."""
    from chat_plugin.session_utils import atomic_write_json

    target = tmp_path / "nested" / "deep" / "test.json"
    atomic_write_json(target, {"nested": True})
    assert target.exists()


def test_patch_forked_metadata_sets_working_dir(tmp_path):
    """S-15: patch_forked_metadata should set working_dir from cwd param."""
    from chat_plugin.session_utils import patch_forked_metadata

    forked_dir = tmp_path / "forked"
    forked_dir.mkdir()
    (forked_dir / "metadata.json").write_text("{}")

    parent_dir = tmp_path / "parent"
    parent_dir.mkdir()
    (parent_dir / "metadata.json").write_text(
        json.dumps({"bundle": "test-bundle", "model": "gpt-4"})
    )

    patch_forked_metadata(forked_dir, parent_dir, cwd="/Users/test/project")

    meta = json.loads((forked_dir / "metadata.json").read_text())
    assert meta["working_dir"] == "/Users/test/project"
    assert meta["bundle"] == "test-bundle"
    assert meta["model"] == "gpt-4"


def test_patch_forked_metadata_falls_back_to_parent_cwd(tmp_path):
    """patch_forked_metadata should use parent's working_dir when cwd is None."""
    from chat_plugin.session_utils import patch_forked_metadata

    forked_dir = tmp_path / "forked"
    forked_dir.mkdir()
    (forked_dir / "metadata.json").write_text("{}")

    parent_dir = tmp_path / "parent"
    parent_dir.mkdir()
    (parent_dir / "metadata.json").write_text(
        json.dumps({"working_dir": "/parent/cwd"})
    )

    patch_forked_metadata(forked_dir, parent_dir, cwd=None)

    meta = json.loads((forked_dir / "metadata.json").read_text())
    assert meta["working_dir"] == "/parent/cwd"


def test_patch_forked_metadata_no_change_when_nothing_to_patch(tmp_path):
    """patch_forked_metadata should not write if nothing changed."""
    from chat_plugin.session_utils import patch_forked_metadata

    forked_dir = tmp_path / "forked"
    forked_dir.mkdir()
    (forked_dir / "metadata.json").write_text(
        json.dumps({"bundle": "existing", "model": "existing"})
    )

    parent_dir = tmp_path / "parent"
    parent_dir.mkdir()
    (parent_dir / "metadata.json").write_text("{}")

    mtime_before = (forked_dir / "metadata.json").stat().st_mtime_ns
    patch_forked_metadata(forked_dir, parent_dir, cwd=None)
    mtime_after = (forked_dir / "metadata.json").stat().st_mtime_ns

    assert mtime_before == mtime_after, "File should not be rewritten when nothing changed"
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_session_utils.py -v
```

Expected: FAIL — `chat_plugin.session_utils` module doesn't exist yet.

**Step 3: Create the shared module**

Create `src/chat_plugin/session_utils.py`:

```python
"""Shared session utilities — atomic writes and forked metadata patching.

Extracted from routes.py and commands.py to deduplicate the
_patch_forked_metadata logic and provide atomic JSON writes using
the same tmp+rename pattern as PinStorage._save().
"""

from __future__ import annotations

import json
import os
from pathlib import Path


def atomic_write_json(path: Path, data: dict) -> None:
    """Atomically write JSON data to a file using tmp + os.rename.

    Creates parent directories if needed. Uses the same pattern as
    PinStorage._save(): write to a .tmp sibling, then os.rename()
    to the target path. This prevents half-written files on crash.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.rename(tmp, path)


def patch_forked_metadata(
    forked_dir: Path,
    parent_dir: Path,
    cwd: str | None,
) -> None:
    """Patch a forked session's metadata.json with working_dir and any
    fields that fork_session() left as null (e.g. bundle, model).

    Uses atomic_write_json for crash safety.

    Args:
        forked_dir: Path to the forked session directory.
        parent_dir: Path to the parent session directory.
        cwd: Working directory to set. If None, falls back to parent's
            working_dir or cwd field.
    """
    meta_path = forked_dir / "metadata.json"
    try:
        meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    except (json.JSONDecodeError, OSError):
        meta = {}

    # Read parent metadata for fallback values
    parent_meta: dict = {}
    parent_meta_path = parent_dir / "metadata.json"
    try:
        parent_meta = json.loads(parent_meta_path.read_text())
    except (json.JSONDecodeError, OSError, FileNotFoundError):
        pass

    changed = False

    # Patch working_dir
    if not cwd:
        cwd = parent_meta.get("working_dir") or parent_meta.get("cwd")
    if cwd:
        meta["working_dir"] = cwd
        changed = True

    # Patch bundle if null
    if not meta.get("bundle") and parent_meta.get("bundle"):
        meta["bundle"] = parent_meta["bundle"]
        changed = True

    # Patch model if null
    if not meta.get("model") and parent_meta.get("model"):
        meta["model"] = parent_meta["model"]
        changed = True

    if changed:
        try:
            atomic_write_json(meta_path, meta)
        except OSError:
            pass  # best-effort
```

**Step 4: Run tests to verify the new module works**

```bash
uv run pytest tests/test_session_utils.py -v
```

Expected: PASS

**Step 5: Update routes.py to use the shared function**

In `src/chat_plugin/routes.py`:

1. **Add import** at the top (after existing imports):

```python
from chat_plugin.session_utils import patch_forked_metadata
```

2. **Delete the local `_patch_forked_metadata` function** (lines 318-363 inside `create_fork_routes`).

3. **Update the call site** (line 428). Change:

```python
                _patch_forked_metadata(result.session_dir, session_dir, cwd)
```

to:

```python
                patch_forked_metadata(result.session_dir, session_dir, cwd)
```

**Step 6: Update commands.py to use the shared function**

In `src/chat_plugin/commands.py`:

1. **Add import** at the top:

```python
from chat_plugin.session_utils import patch_forked_metadata
```

2. **Delete the local `_patch_forked_metadata` static method** (lines 63-105 in the `CommandProcessor` class).

3. **Update the call site** (line 393 in `_cmd_fork`). Change:

```python
                self._patch_forked_metadata(result.session_dir, session_dir, handle)
```

to:

```python
                cwd = str(handle.working_dir) if getattr(handle, "working_dir", None) else None
                patch_forked_metadata(result.session_dir, session_dir, cwd)
```

**Step 7: Run all affected tests**

```bash
uv run pytest tests/test_session_utils.py tests/test_routes.py tests/test_commands.py -v
```

Expected: All pass.

**Step 8: Run full suite**

```bash
uv run pytest tests/ -x
```

Expected: All 293+ tests pass.

**Step 9: Commit**

```bash
git add src/chat_plugin/session_utils.py src/chat_plugin/routes.py src/chat_plugin/commands.py tests/test_session_utils.py
git commit -m "fix(S-15): extract shared atomic_write_json and patch_forked_metadata

Deduplicated _patch_forked_metadata from routes.py and commands.py into
a shared session_utils.py module. Metadata writes now use atomic
tmp+rename (via atomic_write_json) instead of direct write_text()."
```

---

## Task 10: S-17 — Feedback Hidden-Session Race

**Bug:** The feedback analysis endpoint calls `_mark_session_hidden()` in the request handler, before the background task starts execution. The session directory often doesn't exist on disk yet (created lazily by the daemon), causing a 404 — the session permanently stays visible in the sidebar.

**Fix:** Move the `_mark_session_hidden` call into `_safe_kick_off` (the background task), where the session directory reliably exists. Brief visibility window (<100ms, one poll cycle) is acceptable.

**Files:**
- Modify: `src/chat_plugin/feedback.py` (lines 207-215, 283-284)
- Modify: `tests/test_feedback.py` (update existing test)

**Step 1: Move `_mark_session_hidden` into `_safe_kick_off`**

In `src/chat_plugin/feedback.py`:

1. **Update `_safe_kick_off`** (lines 207-215). Replace:

```python
async def _safe_kick_off(base_url: str, session_id: str, prompt: str) -> None:
    """Wrap _kick_off_execution with logging so failures aren't silent."""
    try:
        await _kick_off_execution(base_url, session_id, prompt)
    except Exception:
        logger.exception(
            "[feedback-analysis] Background analysis FAILED for session %s",
            session_id,
        )
```

With:

```python
async def _safe_kick_off(base_url: str, session_id: str, prompt: str) -> None:
    """Wrap _kick_off_execution with logging so failures aren't silent.

    Also marks the session as hidden. This runs in a background task
    where the session dir reliably exists (created by the daemon after
    POST /sessions returns). Brief visibility window (~one poll cycle)
    between session creation and this task running is acceptable —
    the previous location raced with directory creation, causing 404s
    that left sessions permanently visible.
    """
    try:
        await _mark_session_hidden(base_url, session_id)
        await _kick_off_execution(base_url, session_id, prompt)
    except Exception:
        logger.exception(
            "[feedback-analysis] Background analysis FAILED for session %s",
            session_id,
        )
```

2. **Remove the inline `_mark_session_hidden` call** from `analyze_feedback`. Find line 284:

```python
        analysis_session_id = await _create_analysis_session(base_url)
        await _mark_session_hidden(base_url, analysis_session_id)
```

Replace with:

```python
        analysis_session_id = await _create_analysis_session(base_url)
        # _mark_session_hidden is now called inside _safe_kick_off where
        # the session dir reliably exists on disk. See S-17.
```

**Step 2: Update the existing integration test**

In `tests/test_feedback.py`, update `test_analyze_creates_hidden_session` (line 90). The test currently asserts `mock_hide.assert_called_once()` directly after the request. Since `_mark_session_hidden` is now called inside `_safe_kick_off` (background task), the mock is still called — but from the background task rather than the request handler.

The test should still pass as-is because:
- `_mark_session_hidden` is still patched
- `_safe_kick_off` still calls it (it's not patched away)
- `_kick_off_execution` is patched, so `_safe_kick_off` succeeds
- The background task runs before `client.post()` returns (TestClient behavior)

If the test fails due to timing, update it to patch `_safe_kick_off` directly:

No change needed to the test unless it fails — verify first.

**Step 3: Update the `_safe_kick_off` unit test**

In `tests/test_feedback.py`, update `test_safe_kick_off_logs_on_failure` (line 144). The test currently only patches `_kick_off_execution`. Since `_safe_kick_off` now also calls `_mark_session_hidden`, we need to patch it too:

Replace:

```python
@pytest.mark.asyncio
async def test_safe_kick_off_logs_on_failure(caplog):
    """_safe_kick_off logs via logger.exception when _kick_off_execution raises."""
    from chat_plugin.feedback import _safe_kick_off

    mock_kick = AsyncMock(side_effect=RuntimeError("connection refused"))

    with patch("chat_plugin.feedback._kick_off_execution", mock_kick):
        with caplog.at_level("ERROR", logger="chat_plugin.feedback"):
            await _safe_kick_off("http://localhost:8080", "sess-fail", "prompt")

    assert len(caplog.records) == 1
    assert "Background analysis FAILED" in caplog.records[0].message
    assert "sess-fail" in caplog.records[0].message
```

With:

```python
@pytest.mark.asyncio
async def test_safe_kick_off_logs_on_failure(caplog):
    """_safe_kick_off logs via logger.exception when _kick_off_execution raises."""
    from chat_plugin.feedback import _safe_kick_off

    mock_kick = AsyncMock(side_effect=RuntimeError("connection refused"))
    mock_hide = AsyncMock()

    with (
        patch("chat_plugin.feedback._kick_off_execution", mock_kick),
        patch("chat_plugin.feedback._mark_session_hidden", mock_hide),
    ):
        with caplog.at_level("ERROR", logger="chat_plugin.feedback"):
            await _safe_kick_off("http://localhost:8080", "sess-fail", "prompt")

    assert len(caplog.records) == 1
    assert "Background analysis FAILED" in caplog.records[0].message
    assert "sess-fail" in caplog.records[0].message
```

**Step 4: Run feedback tests**

```bash
uv run pytest tests/test_feedback.py -v
```

Expected: All pass.

**Step 5: Run full suite**

```bash
uv run pytest tests/ -x
```

Expected: All 293+ tests pass.

**Step 6: Commit**

```bash
git add src/chat_plugin/feedback.py tests/test_feedback.py
git commit -m "fix(S-17): move _mark_session_hidden into background task to eliminate 404 race

_mark_session_hidden was called in the request handler before the daemon
had created the session directory on disk, causing intermittent 404s that
left analysis sessions permanently visible in the sidebar. Moved into
_safe_kick_off where the session dir reliably exists. Brief visibility
window (<100ms, one poll cycle) is acceptable."
```

---

## Final Verification

**Step 1: Run the complete test suite**

```bash
uv run pytest tests/ -x -v
```

Expected: All 293+ tests pass, including the new tests added in this PR.

**Step 2: Verify no regressions with type checking**

```bash
uv run pyright src/chat_plugin/ 2>/dev/null || echo "pyright not available, skip"
```

**Step 3: Review the commit log**

```bash
git log --oneline main..HEAD
```

Expected: 10 commits, one per fix:

```
fix(S-17): move _mark_session_hidden into background task to eliminate 404 race
fix(S-15): extract shared atomic_write_json and patch_forked_metadata
fix(S-18): add thread safety to whisper model singleton
fix(S-19): use atomic tmp+rename for voice settings persistence
fix(S-21): add pinned flag to search results
fix(S-14): has_more pagination uses filtered count instead of raw total
fix(S-13): exclude hidden sessions from scan_session_revisions
fix(S-24): add logging to command handlers that silently swallow exceptions
fix(S-23): remove stale ensure_ids docstring from scan_sessions
fix(S-02): rename sessions_dir to projects_dir in dev server
```

**Step 4: Prepare for PR**

```bash
git push -u origin fix/backend-reliability
```

---

## Summary

| Task | Fix ID | What changed | Files |
|------|--------|-------------|-------|
| 1 | S-02 | Rename `sessions_dir` → `projects_dir` in dev server | `__main__.py` |
| 2 | S-23 | Delete stale `ensure_ids` docstring | `session_history.py` |
| 3 | S-24 | Add `logger.exception()`/`warning()` to 5 command handlers | `commands.py` |
| 4 | S-13 | Filter hidden sessions from `scan_session_revisions` | `session_history.py` |
| 5 | S-14 | Fix `has_more` to use `len(sessions) == limit` | `routes.py` |
| 6 | S-21 | Add `pinned` flag to search results | `routes.py` |
| 7 | S-19 | Atomic tmp+rename for voice settings | `voice.py` |
| 8 | S-18 | Thread-safe whisper model singleton with `threading.Lock` | `voice.py` |
| 9 | S-15 | Extract shared `atomic_write_json` + `patch_forked_metadata` | `session_utils.py`, `routes.py`, `commands.py` |
| 10 | S-17 | Move `_mark_session_hidden` into background task | `feedback.py` |

**New files:** `src/chat_plugin/session_utils.py`, `tests/test_main_dev_mode.py`, `tests/test_voice_settings.py`, `tests/test_session_utils.py`

**Modified files:** `src/chat_plugin/__main__.py`, `src/chat_plugin/session_history.py`, `src/chat_plugin/routes.py`, `src/chat_plugin/commands.py`, `src/chat_plugin/voice.py`, `src/chat_plugin/feedback.py`, `tests/test_session_history.py`, `tests/test_routes.py`, `tests/test_commands.py`, `tests/test_feedback.py`