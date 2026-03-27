# PR 1: Security Hardening — Implementation Plan

> **Execution:** Use the subagent-driven-development workflow to implement this plan.

**Goal:** Fix 5 security vulnerabilities in the Python backend: path traversal (S-01), SSRF (S-25), missing input validation (S-16), regex inconsistency (S-03), and event-loop blocking (S-04).

**Architecture:** Each fix adds input validation or corrects an unsafe pattern at the HTTP request boundary. All changes are in 4 Python backend files. No API behavior changes for valid input — invalid input now gets HTTP 400 instead of unpredictable behavior.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, pytest, pytest-asyncio

**Design doc:** `docs/superpowers/specs/2026-03-26-amplifier-chat-comprehensive-bugfix-design.md` (PR 1 section)

---

### Task 1: Create the feature branch

**Step 1: Create and switch to the branch**

```bash
cd /Users/samule/repo/amplifier-chat
git checkout main
git pull origin main
git checkout -b fix/security-hardening
```

**Step 2: Verify clean baseline**

```bash
pytest tests/ -x -q
```

Expected: All 277 tests pass. No failures. If there are pre-existing failures (the 13 TDD spec failures in `test_preserve_input_on_send_failure.py` and 3 string-mismatch failures), note them and move on — those are pre-existing and not our concern.

**Step 3: Commit (nothing to commit yet — just verification)**

No commit needed. Proceed to Task 2.

---

### Task 2: S-01 — Fix path traversal in voice model endpoints

**Bug:** Three voice endpoints (`/transcribe`, `/voice/download-model`, `/voice/delete-model`) accept a user-supplied `model` name and interpolate it into a file path (`ggml-{model_name}.bin`) without checking it against the `STT_MODELS` allowlist. An attacker can pass `"../../etc/passwd"` to read/delete arbitrary files.

**Fix:** Add `if model_name not in STT_MODELS: raise HTTPException(400)` to all 3 endpoints. This pattern already exists in `update_voice_settings` at line 326 of `voice.py`.

**Files:**
- Create: `tests/test_voice_model_validation.py`
- Modify: `src/chat_plugin/voice.py` (lines ~192, ~355, ~406)

**Step 1: Write the failing tests**

Create `tests/test_voice_model_validation.py` with this exact content:

```python
"""Tests for S-01: voice model name validation against STT_MODELS allowlist."""

from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import chat_plugin.voice as voice_mod


def _make_voice_client() -> TestClient:
    """Create a TestClient with only the voice router mounted."""
    app = FastAPI()
    app.include_router(voice_mod.create_voice_routes())
    return TestClient(app)


# -- /voice/delete-model (no whisper gate — always reachable) --


def test_delete_model_rejects_path_traversal():
    client = _make_voice_client()
    resp = client.post(
        "/chat/voice/delete-model",
        json={"model": "../../../etc/passwd"},
    )
    assert resp.status_code == 400
    assert "Unknown model" in resp.json()["detail"]


def test_delete_model_rejects_unknown_model():
    client = _make_voice_client()
    resp = client.post(
        "/chat/voice/delete-model",
        json={"model": "nonexistent-model"},
    )
    assert resp.status_code == 400
    assert "Unknown model" in resp.json()["detail"]


# -- /voice/download-model (whisper gate — must mock _whisper_available) --


def test_download_model_rejects_path_traversal(monkeypatch):
    monkeypatch.setattr(voice_mod, "_whisper_available", True)
    client = _make_voice_client()
    resp = client.post(
        "/chat/voice/download-model",
        json={"model": "../../../etc/passwd"},
    )
    assert resp.status_code == 400
    assert "Unknown model" in resp.json()["detail"]


def test_download_model_rejects_unknown_model(monkeypatch):
    monkeypatch.setattr(voice_mod, "_whisper_available", True)
    client = _make_voice_client()
    resp = client.post(
        "/chat/voice/download-model",
        json={"model": "not-a-real-model"},
    )
    assert resp.status_code == 400
    assert "Unknown model" in resp.json()["detail"]


# -- /transcribe (whisper gate — must mock _whisper_available) --


def test_transcribe_rejects_path_traversal(monkeypatch):
    monkeypatch.setattr(voice_mod, "_whisper_available", True)
    client = _make_voice_client()
    resp = client.post(
        "/chat/transcribe",
        json={
            "audio_data": "dGVzdA==",  # base64("test")
            "model": "../../../etc/passwd",
        },
    )
    assert resp.status_code == 400
    assert "Unknown model" in resp.json()["detail"]


def test_transcribe_rejects_unknown_model(monkeypatch):
    monkeypatch.setattr(voice_mod, "_whisper_available", True)
    client = _make_voice_client()
    resp = client.post(
        "/chat/transcribe",
        json={
            "audio_data": "dGVzdA==",
            "model": "not-a-real-model",
        },
    )
    assert resp.status_code == 400
    assert "Unknown model" in resp.json()["detail"]


# -- Allowlisted models should still be accepted --


def test_delete_model_accepts_valid_model():
    """A valid model name should NOT get a 400. It may get 200 (not_found) or
    another status, but never 400 for model validation."""
    client = _make_voice_client()
    resp = client.post(
        "/chat/voice/delete-model",
        json={"model": "base"},
    )
    assert resp.status_code != 400
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_voice_model_validation.py -v
```

Expected: 6 tests FAIL. The `delete_model` tests will get 200 (status `not_found`) instead of 400. The `download_model` tests will get 502 (failed download) or timeout instead of 400. The `transcribe` tests will get a different error instead of 400. The `accepts_valid_model` test should PASS (no 400 returned).

**Step 3: Add model name validation to all 3 endpoints**

Edit `src/chat_plugin/voice.py`. Make these 3 changes:

**Change 1** — In `transcribe_audio`, add validation right after `model_name` is assigned (after line 192, before the `audio_data` check):

Find this block:
```python
        model_name = body.get("model", settings.get("stt_model", DEFAULT_STT_MODEL))

        if not audio_data_b64:
```

Replace with:
```python
        model_name = body.get("model", settings.get("stt_model", DEFAULT_STT_MODEL))

        if model_name not in STT_MODELS:
            raise HTTPException(
                status_code=400, detail=f"Unknown model: {model_name}"
            )

        if not audio_data_b64:
```

**Change 2** — In `download_stt_model`, add validation right after `model_name` is assigned (after line 355, before `models_dir`):

Find this block:
```python
        model_name = body.get("model", DEFAULT_STT_MODEL)

        models_dir = _models_dir()
```

Replace with:
```python
        model_name = body.get("model", DEFAULT_STT_MODEL)

        if model_name not in STT_MODELS:
            raise HTTPException(
                status_code=400, detail=f"Unknown model: {model_name}"
            )

        models_dir = _models_dir()
```

**Change 3** — In `delete_stt_model`, add validation right after `model_name` is assigned (after line 406, before `model_file`):

Find this block:
```python
        model_name = body.get("model", DEFAULT_STT_MODEL)

        model_file = _models_dir() / f"ggml-{model_name}.bin"
```

Replace with:
```python
        model_name = body.get("model", DEFAULT_STT_MODEL)

        if model_name not in STT_MODELS:
            raise HTTPException(
                status_code=400, detail=f"Unknown model: {model_name}"
            )

        model_file = _models_dir() / f"ggml-{model_name}.bin"
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/test_voice_model_validation.py -v
```

Expected: All 7 tests PASS.

**Step 5: Run full test suite to check for regressions**

```bash
pytest tests/ -x -q
```

Expected: Same pass count as baseline. No new failures.

**Step 6: Commit**

```bash
git add tests/test_voice_model_validation.py src/chat_plugin/voice.py
git commit -m "fix(security): validate voice model names against STT_MODELS allowlist (S-01)

Add model_name not in STT_MODELS check to transcribe_audio,
download_stt_model, and delete_stt_model endpoints. Prevents path
traversal via crafted model names like '../../etc/passwd'.

Pattern copied from existing update_voice_settings:326."
```

---

### Task 3: S-25 — Fix SSRF via Host header in feedback loopback

**Bug:** The feedback analysis endpoint at `POST /chat/api/feedback/analyze` derives its loopback `base_url` from `request.base_url`, which reads the `Host` HTTP header. An attacker can set `Host: evil.com:9999` to redirect the internal HTTP call to an attacker-controlled server.

**Fix:** Replace the `request.base_url`-derived URL with `request.scope["server"]`, which returns the actual ASGI socket bind address from uvicorn. The loopback always goes to `127.0.0.1:{port}`.

**Files:**
- Modify: `tests/test_feedback.py` (add test)
- Modify: `src/chat_plugin/feedback.py` (lines 268–280)

**Step 1: Write the failing test**

Add this test to the bottom of `tests/test_feedback.py`:

```python
# ---------------------------------------------------------------------------
# S-25: SSRF — loopback base_url must not come from Host header
# ---------------------------------------------------------------------------


def test_analyze_ignores_host_header_for_loopback(tmp_path):
    """base_url passed to _create_analysis_session must use the ASGI server
    address, NOT the Host header.  A malicious Host: evil.com:9999 must not
    redirect the internal loopback call."""
    sess_dir = tmp_path / "-Users-test" / "sessions" / "sess-target"
    sess_dir.mkdir(parents=True)
    (sess_dir / "transcript.jsonl").write_text(
        json.dumps({"role": "user", "content": "hello"}) + "\n"
    )

    app = _make_feedback_app(
        projects_dir=tmp_path, daemon_session_path="/tmp/daemon"
    )
    client = TestClient(app)

    mock_create = AsyncMock(return_value="analysis-001")
    mock_hide = AsyncMock()
    mock_kick = AsyncMock()

    with (
        patch("chat_plugin.feedback._create_analysis_session", mock_create),
        patch("chat_plugin.feedback._mark_session_hidden", mock_hide),
        patch("chat_plugin.feedback._kick_off_execution", mock_kick),
    ):
        resp = client.post(
            "/chat/api/feedback/analyze",
            json={"session_id": "sess-target"},
            headers={"Host": "evil.com:9999"},
        )

    assert resp.status_code == 200

    # The base_url passed to _create_analysis_session must be 127.0.0.1,
    # NOT evil.com from the spoofed Host header.
    call_args = mock_create.call_args
    actual_base_url = call_args[0][0] if call_args[0] else call_args[1]["base_url"]
    assert "evil.com" not in actual_base_url
    assert "127.0.0.1" in actual_base_url
```

**Step 2: Run the test to verify it fails**

```bash
pytest tests/test_feedback.py::test_analyze_ignores_host_header_for_loopback -v
```

Expected: FAIL. The current code derives `base_url` from `request.base_url` (which uses the Host header), so `actual_base_url` will contain `evil.com`.

**Step 3: Replace the base_url derivation**

Edit `src/chat_plugin/feedback.py`. Find this block (lines 268–280):

```python
        _burl = request.base_url
        _host = _burl.hostname or "127.0.0.1"
        # Normalise bind-all wildcard addresses to loopback so that httpx can
        # actually connect.  amplifierd always listens on the same host, so
        # 127.0.0.1 is always correct for intra-process calls.
        if _host in ("0.0.0.0", "::"):
            _host = "127.0.0.1"
        _port = _burl.port
        base_url = (
            f"{_burl.scheme}://{_host}:{_port}"
            if _port
            else f"{_burl.scheme}://{_host}"
        )
```

Replace with:

```python
        # Use the real ASGI socket bind address, not the Host header.
        # request.scope["server"] returns (host, port) from uvicorn's
        # actual listener — immune to Host header spoofing (S-25).
        _host, _port = request.scope["server"]
        base_url = f"http://127.0.0.1:{_port}"
```

**Step 4: Run the test to verify it passes**

```bash
pytest tests/test_feedback.py::test_analyze_ignores_host_header_for_loopback -v
```

Expected: PASS.

**Step 5: Run all feedback tests**

```bash
pytest tests/test_feedback.py -v
```

Expected: All tests in `test_feedback.py` PASS (including the pre-existing ones).

**Step 6: Commit**

```bash
git add tests/test_feedback.py src/chat_plugin/feedback.py
git commit -m "fix(security): use ASGI server scope for feedback loopback URL (S-25)

Replace request.base_url (derived from Host header) with
request.scope['server'] (actual uvicorn bind address). Prevents SSRF
via spoofed Host header redirecting internal analysis calls."
```

---

### Task 4: S-16 — Add input validation to routes.py endpoints

**Bug:** Four entry points in `routes.py` accept `session_id` without validation: `POST /chat/pins/{session_id}` (line 48), `DELETE /chat/pins/{session_id}` (line 53), `POST /chat/command` body `session_id` (line 298), and `POST /chat/api/sessions/{session_id}/shell` (line 459). The newer API-style pin endpoints (lines 64, 71) already have validation — the legacy ones don't.

**Fix:** Add `_VALID_SESSION_ID.fullmatch(session_id)` checks matching the existing pattern at lines 64 and 71.

**Files:**
- Create: `tests/test_input_validation.py`
- Modify: `src/chat_plugin/routes.py` (lines ~48, ~53, ~298, ~459)

**Step 1: Write the failing tests**

Create `tests/test_input_validation.py` with this exact content:

```python
"""Tests for S-16: input validation on all session_id entry points."""


# -- Legacy pin endpoints (routes.py) --


def test_legacy_pin_rejects_invalid_session_id(client):
    resp = client.post("/chat/pins/bad.session" )
    assert resp.status_code == 400


def test_legacy_unpin_rejects_invalid_session_id(client):
    resp = client.delete("/chat/pins/bad.session")
    assert resp.status_code == 400


def test_legacy_pin_accepts_valid_session_id(client):
    """Valid IDs like 'my-session_123' must still work."""
    resp = client.post("/chat/pins/my-session_123")
    assert resp.status_code == 200


# -- dispatch_command (routes.py) --


def test_dispatch_command_rejects_invalid_session_id(client):
    resp = client.post(
        "/chat/command",
        json={"command": "/help", "session_id": "../../../etc/passwd"},
    )
    assert resp.status_code == 400


def test_dispatch_command_allows_null_session_id(client):
    """session_id is optional for commands like /help."""
    resp = client.post(
        "/chat/command",
        json={"command": "/help"},
    )
    assert resp.status_code == 200


# -- execute_shell (routes.py) --


def test_shell_rejects_invalid_session_id(client):
    resp = client.post(
        "/chat/api/sessions/bad.session/shell",
        json={"command": "ls", "cwd": "/tmp"},
    )
    assert resp.status_code == 400
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_input_validation.py -v
```

Expected: 4 tests FAIL (the rejection tests get 200 instead of 400). 2 tests PASS (valid ID and null session_id).

**Step 3: Add validation to all 4 entry points**

Edit `src/chat_plugin/routes.py`. Make these 4 changes:

**Change 1** — In `pin_session` (line 48), add validation:

Find:
```python
    @router.post("/pins/{session_id}")
    async def pin_session(session_id: str):
        pin_storage.add(session_id)
```

Replace with:
```python
    @router.post("/pins/{session_id}")
    async def pin_session(session_id: str):
        if not _VALID_SESSION_ID.fullmatch(session_id):
            raise HTTPException(status_code=400, detail="Invalid session ID")
        pin_storage.add(session_id)
```

**Change 2** — In `unpin_session` (line 53), add validation:

Find:
```python
    @router.delete("/pins/{session_id}")
    async def unpin_session(session_id: str):
        pin_storage.remove(session_id)
```

Replace with:
```python
    @router.delete("/pins/{session_id}")
    async def unpin_session(session_id: str):
        if not _VALID_SESSION_ID.fullmatch(session_id):
            raise HTTPException(status_code=400, detail="Invalid session ID")
        pin_storage.remove(session_id)
```

**Change 3** — In `dispatch_command` (line 298), add validation after `session_id` is extracted. `session_id` is optional (can be None), so only validate when present:

Find:
```python
    @router.post("/command")
    async def dispatch_command(body: dict):
        session_id = body.get("session_id")
        text = body.get("command", body.get("text", ""))
```

Replace with:
```python
    @router.post("/command")
    async def dispatch_command(body: dict):
        session_id = body.get("session_id")
        if session_id is not None and not _VALID_SESSION_ID.fullmatch(session_id):
            raise HTTPException(status_code=400, detail="Invalid session ID")
        text = body.get("command", body.get("text", ""))
```

**Change 4** — In `execute_shell` (line 459), add validation at the top of the function:

Find:
```python
    @router.post("/api/sessions/{session_id}/shell")
    async def execute_shell(session_id: str, body: dict):
        command = body.get("command", "").strip()
```

Replace with:
```python
    @router.post("/api/sessions/{session_id}/shell")
    async def execute_shell(session_id: str, body: dict):
        if not _VALID_SESSION_ID.fullmatch(session_id):
            raise HTTPException(status_code=400, detail="Invalid session ID")
        command = body.get("command", "").strip()
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/test_input_validation.py -v
```

Expected: All 6 tests PASS.

**Step 5: Run full test suite**

```bash
pytest tests/ -x -q
```

Expected: Same pass count as baseline plus the new tests. The existing `test_pin_session` test in `test_routes.py` uses `"session-abc"` (valid) so it still passes.

**Step 6: Commit**

```bash
git add tests/test_input_validation.py src/chat_plugin/routes.py
git commit -m "fix(security): validate session_id on all unprotected entry points (S-16)

Add _VALID_SESSION_ID.fullmatch() checks to legacy pin endpoints,
dispatch_command, and execute_shell. Matches existing validation on
the API-style pin endpoints at lines 64/71."
```

---

### Task 5: S-16 — Add Pydantic validator to AnalyzeRequest

**Bug:** `AnalyzeRequest.session_id` in `feedback.py` accepts any string. While the session_id is used in a filesystem path lookup (`_find_transcript_path`), it should be validated at the Pydantic layer before reaching any business logic.

**Fix:** Add a `field_validator` to `AnalyzeRequest` that checks session_id format.

**Files:**
- Modify: `tests/test_feedback.py` (add test)
- Modify: `src/chat_plugin/feedback.py` (add validator to `AnalyzeRequest`)

**Step 1: Write the failing test**

Add this test to `tests/test_feedback.py`, right after the existing `test_analyze_rejects_invalid_body`:

```python
def test_analyze_rejects_invalid_session_id_format(tmp_path):
    """AnalyzeRequest should reject session IDs with path traversal chars."""
    app = _make_feedback_app(projects_dir=tmp_path)
    client = TestClient(app)

    resp = client.post(
        "/chat/api/feedback/analyze",
        json={"session_id": "../../../etc/passwd"},
    )
    assert resp.status_code == 422  # Pydantic validation error
```

**Step 2: Run the test to verify it fails**

```bash
pytest tests/test_feedback.py::test_analyze_rejects_invalid_session_id_format -v
```

Expected: FAIL. Current code accepts any string, so it will return 404 (transcript not found) instead of 422.

**Step 3: Add the Pydantic field_validator**

Edit `src/chat_plugin/feedback.py`.

**Change 1** — Add `re` to imports. Find:

```python
import asyncio
import logging
from pathlib import Path
```

Replace with:

```python
import asyncio
import logging
import re
from pathlib import Path
```

**Change 2** — Add `field_validator` to the Pydantic import. Find:

```python
from pydantic import BaseModel
```

Replace with:

```python
from pydantic import BaseModel, field_validator
```

**Change 3** — Add the validator to `AnalyzeRequest`. Find:

```python
class AnalyzeRequest(BaseModel):
    session_id: str
```

Replace with:

```python
class AnalyzeRequest(BaseModel):
    session_id: str

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, v: str) -> str:
        if not re.fullmatch(r"[a-zA-Z0-9_\-]+", v):
            raise ValueError("Invalid session ID format")
        return v
```

**Step 4: Run the test to verify it passes**

```bash
pytest tests/test_feedback.py::test_analyze_rejects_invalid_session_id_format -v
```

Expected: PASS.

**Step 5: Run all feedback tests**

```bash
pytest tests/test_feedback.py -v
```

Expected: All tests PASS. The existing `test_analyze_creates_hidden_session` uses `"sess-abc"` which matches the regex.

**Step 6: Commit**

```bash
git add tests/test_feedback.py src/chat_plugin/feedback.py
git commit -m "fix(security): add Pydantic session_id validator to AnalyzeRequest (S-16)

Reject invalid session ID formats at the Pydantic validation layer
before any filesystem access occurs in the feedback analysis endpoint."
```

---

### Task 6: S-03 — Unify session ID regex across modules

**Bug:** Two different session ID regexes exist:
- `session_history.py:43`: `r"^[a-zA-Z0-9_:\-]+$"` (allows colons)
- `routes.py:21`: `r"^[a-zA-Z0-9_\-]+$"` (no colons)

The colon in `session_history.py` is incorrect — session IDs never contain colons. Also, `session_history.py` uses `.match()` at line 242, which is weaker than `.fullmatch()`.

**Fix:** Drop the colon from `session_history.py`, make it the canonical definition, import in `routes.py`. Change `.match()` to `.fullmatch()`.

**Files:**
- Modify: `src/chat_plugin/session_history.py` (line 43, line 242)
- Modify: `src/chat_plugin/routes.py` (lines 13–17, line 21)

**Step 1: Write the failing test**

Add this test to `tests/test_input_validation.py` (the file created in Task 4):

```python
# -- S-03: unified regex rejects colons --


def test_session_history_regex_rejects_colons():
    """The session_history regex must NOT allow colons in session IDs."""
    from chat_plugin.session_history import _VALID_SESSION_ID_RE

    assert _VALID_SESSION_ID_RE.fullmatch("normal-session_123") is not None
    assert _VALID_SESSION_ID_RE.fullmatch("session:with:colons") is None
```

**Step 2: Run the test to verify it fails**

```bash
pytest tests/test_input_validation.py::test_session_history_regex_rejects_colons -v
```

Expected: FAIL. The current regex allows colons, so `fullmatch("session:with:colons")` returns a match instead of `None`.

**Step 3: Fix session_history.py regex and match method**

Edit `src/chat_plugin/session_history.py`.

**Change 1** — Drop the colon from the regex at line 43:

Find:
```python
_VALID_SESSION_ID_RE = re.compile(r"^[a-zA-Z0-9_:\-]+$")
```

Replace with:
```python
_VALID_SESSION_ID_RE = re.compile(r"^[a-zA-Z0-9_\-]+$")
```

**Change 2** — Change `.match()` to `.fullmatch()` at line 242 in `_iter_session_dirs`:

Find:
```python
                if not _VALID_SESSION_ID_RE.match(session_dir.name):
```

Replace with:
```python
                if not _VALID_SESSION_ID_RE.fullmatch(session_dir.name):
```

**Step 4: Update routes.py to import from session_history**

Edit `src/chat_plugin/routes.py`.

**Change 1** — Add `_VALID_SESSION_ID_RE` to the session_history import (lines 13–17):

Find:
```python
from chat_plugin.session_history import (
    scan_session_revisions,
    scan_sessions,
    search_sessions,
)
```

Replace with:
```python
from chat_plugin.session_history import (
    _VALID_SESSION_ID_RE,
    scan_session_revisions,
    scan_sessions,
    search_sessions,
)
```

**Change 2** — Replace the local regex definition with an alias (line 21):

Find:
```python
_VALID_SESSION_ID = re.compile(r"^[a-zA-Z0-9_\-]+$")
```

Replace with:
```python
_VALID_SESSION_ID = _VALID_SESSION_ID_RE  # canonical regex from session_history
```

**Step 5: Run the regex test**

```bash
pytest tests/test_input_validation.py::test_session_history_regex_rejects_colons -v
```

Expected: PASS.

**Step 6: Run full test suite**

```bash
pytest tests/ -x -q
```

Expected: All tests PASS. The `re` import in `routes.py` is still needed (used nowhere else after this change — actually check: `re` is imported at line 5 and only used for the old `_VALID_SESSION_ID` compile). After this change, `re` is no longer used directly in `routes.py`. You can remove the `import re` from line 5 of `routes.py` if you want, but it's not required — unused imports are a linting issue, not a bug. Leave it for now; the linter can catch it later.

**Step 7: Commit**

```bash
git add src/chat_plugin/session_history.py src/chat_plugin/routes.py tests/test_input_validation.py
git commit -m "fix(security): unify session ID regex, drop colon, use fullmatch (S-03)

Remove colon from session_history._VALID_SESSION_ID_RE (session IDs
never contain colons). Import canonical regex in routes.py instead of
defining a duplicate. Change .match() to .fullmatch() in
_iter_session_dirs for consistency."
```

---

### Task 7: S-04 — Fix event loop blocking in command dispatch

**Bug:** `POST /chat/command` calls `processor.handle_command()` synchronously on the async event loop (line 302 in `routes.py`). The `/fork` command does heavy filesystem I/O, blocking the event loop for seconds.

**Fix:** Wrap the call in `asyncio.to_thread()`. One-line change. The `asyncio` module is already imported at line 3 of `routes.py`.

**Files:**
- Modify: `src/chat_plugin/routes.py` (line 302)
- Modify: `tests/test_input_validation.py` (add regression test)

**Step 1: Add a regression test**

Add this test to the bottom of `tests/test_input_validation.py`:

```python
# -- S-04: command dispatch regression test --


def test_dispatch_command_returns_help(client):
    """Verify /help command still works after to_thread wrapping."""
    resp = client.post(
        "/chat/command",
        json={"command": "/help"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("type") == "command"
```

**Step 2: Run the regression test to verify it passes BEFORE the change**

```bash
pytest tests/test_input_validation.py::test_dispatch_command_returns_help -v
```

Expected: PASS. The `/help` command works fine currently.

**Step 3: Wrap handle_command in asyncio.to_thread()**

Edit `src/chat_plugin/routes.py`. Find the `dispatch_command` function body. Locate this block:

```python
        if action == "command":
            result = processor.handle_command(
                data["command"], data["args"], session_id=session_id
            )
            return result
```

Replace with:

```python
        if action == "command":
            result = await asyncio.to_thread(
                processor.handle_command,
                data["command"],
                data["args"],
                session_id=session_id,
            )
            return result
```

**Step 4: Run the regression test to verify it still passes**

```bash
pytest tests/test_input_validation.py::test_dispatch_command_returns_help -v
```

Expected: PASS.

**Step 5: Run full test suite**

```bash
pytest tests/ -x -q
```

Expected: All tests PASS. No regressions.

**Step 6: Commit**

```bash
git add src/chat_plugin/routes.py tests/test_input_validation.py
git commit -m "fix(reliability): wrap command dispatch in asyncio.to_thread (S-04)

processor.handle_command() does filesystem I/O (especially /fork).
Wrapping in to_thread prevents blocking the async event loop."
```

---

### Task 8: Full integration verification

**Step 1: Run the complete test suite**

```bash
pytest tests/ -v
```

Expected: All tests pass. Count the total and compare to the baseline from Task 1. You should have the baseline count plus the new tests:
- 7 new tests in `test_voice_model_validation.py`
- 1 new test in `test_feedback.py` (SSRF)
- 1 new test in `test_feedback.py` (Pydantic validator)
- 7 new tests in `test_input_validation.py` (4 routes + 1 valid + 1 regex + 1 command regression)

That's **17 new tests** total.

**Step 2: Run type checking**

```bash
python -m pyright src/chat_plugin/voice.py src/chat_plugin/feedback.py src/chat_plugin/routes.py src/chat_plugin/session_history.py 2>/dev/null || echo "pyright not available, skipping"
```

Expected: No new type errors introduced.

**Step 3: Verify the git log looks right**

```bash
git log --oneline main..HEAD
```

Expected: 6 commits (one per fix, plus the branch may have started with 0 commits):
```
<hash> fix(reliability): wrap command dispatch in asyncio.to_thread (S-04)
<hash> fix(security): unify session ID regex, drop colon, use fullmatch (S-03)
<hash> fix(security): add Pydantic session_id validator to AnalyzeRequest (S-16)
<hash> fix(security): validate session_id on all unprotected entry points (S-16)
<hash> fix(security): use ASGI server scope for feedback loopback URL (S-25)
<hash> fix(security): validate voice model names against STT_MODELS allowlist (S-01)
```

**Step 4: Review changed files**

```bash
git diff --stat main..HEAD
```

Expected files changed:
```
 src/chat_plugin/feedback.py         |  ~15 lines changed
 src/chat_plugin/routes.py           |  ~15 lines changed
 src/chat_plugin/session_history.py  |   2 lines changed
 src/chat_plugin/voice.py            |  12 lines changed
 tests/test_feedback.py              |  ~40 lines added
 tests/test_input_validation.py      |  ~60 lines added (new file)
 tests/test_voice_model_validation.py|  ~90 lines added (new file)
```

**Step 5: Confirm branch is ready for PR**

The branch `fix/security-hardening` is ready. It contains 5 security fixes with 17 new tests and 0 regressions. Push and create PR when ready:

```bash
git push origin fix/security-hardening
```