"""
Tests for path traversal vulnerabilities in voice endpoints (S-01).

These tests are written in the TDD RED phase — they are expected to FAIL
against the current (unfixed) code, confirming the vulnerability exists.

Current behaviour that causes failures:
  transcribe: accepts any model string, eventually returns 503 (model not
              downloaded) instead of 400 (invalid model).
  download:   accepts any model string, attempts real HTTP download, returns
              502/other instead of 400 (invalid model).
  delete:     accepts any model string, returns 200 {"status": "not_found"}
              instead of 400 (invalid model).

After the security fix is applied, all 7 tests should PASS.
"""

from __future__ import annotations

import base64
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from chat_plugin.voice import create_voice_routes


# ---------------------------------------------------------------------------
# Test app factory
# ---------------------------------------------------------------------------


def _make_voice_app() -> FastAPI:
    """Create a minimal FastAPI app mounting only the voice routes."""
    app = FastAPI()
    router = create_voice_routes()
    app.include_router(router)
    return app


# ---------------------------------------------------------------------------
# Transcribe endpoint — POST /chat/transcribe
# ---------------------------------------------------------------------------


@patch("chat_plugin.voice._whisper_available", True)
@patch("chat_plugin.voice._convert_audio_to_wav", return_value=b"fake wav bytes")
def test_transcribe_rejects_traversal_model(mock_convert):
    """Path traversal model name must be rejected with 400, not 503/500."""
    client = TestClient(_make_voice_app())
    audio_data = base64.b64encode(b"fake audio bytes").decode()

    resp = client.post(
        "/chat/transcribe",
        json={"audio_data": audio_data, "model": "../../evil"},
    )

    # CURRENTLY FAILS: returns 503 (model not downloaded) instead of 400
    assert resp.status_code == 400, (
        f"Expected 400 for traversal model '../../evil', "
        f"got {resp.status_code}: {resp.text}"
    )


@patch("chat_plugin.voice._whisper_available", True)
@patch("chat_plugin.voice._convert_audio_to_wav", return_value=b"fake wav bytes")
def test_transcribe_rejects_unknown_model(mock_convert):
    """Unknown model name must be rejected with 400, not 503/500."""
    client = TestClient(_make_voice_app())
    audio_data = base64.b64encode(b"fake audio bytes").decode()

    resp = client.post(
        "/chat/transcribe",
        json={"audio_data": audio_data, "model": "nonexistent"},
    )

    # CURRENTLY FAILS: returns 503 (model not downloaded) instead of 400
    assert resp.status_code == 400, (
        f"Expected 400 for unknown model 'nonexistent', "
        f"got {resp.status_code}: {resp.text}"
    )


# ---------------------------------------------------------------------------
# Download endpoint — POST /chat/voice/download-model
# ---------------------------------------------------------------------------


@patch("chat_plugin.voice._whisper_available", True)
def test_download_rejects_traversal_model():
    """Path traversal model name must be rejected with 400 before any download attempt."""
    client = TestClient(_make_voice_app())

    # Prevent real network calls — the fix should validate the model BEFORE
    # httpx is ever reached, so patching httpx is only a safety net here.
    with patch("httpx.AsyncClient", side_effect=RuntimeError("no network in tests")):
        resp = client.post(
            "/chat/voice/download-model",
            json={"model": "../../evil"},
        )

    # CURRENTLY FAILS: reaches httpx/download path and returns 502 instead of 400
    assert resp.status_code == 400, (
        f"Expected 400 for traversal model '../../evil', "
        f"got {resp.status_code}: {resp.text}"
    )


@patch("chat_plugin.voice._whisper_available", True)
def test_download_rejects_unknown_model():
    """Unknown model name must be rejected with 400 before any download attempt."""
    client = TestClient(_make_voice_app())

    with patch("httpx.AsyncClient", side_effect=RuntimeError("no network in tests")):
        resp = client.post(
            "/chat/voice/download-model",
            json={"model": "nonexistent"},
        )

    # CURRENTLY FAILS: reaches httpx/download path and returns 502 instead of 400
    assert resp.status_code == 400, (
        f"Expected 400 for unknown model 'nonexistent', "
        f"got {resp.status_code}: {resp.text}"
    )


# ---------------------------------------------------------------------------
# Delete endpoint — POST /chat/voice/delete-model
# ---------------------------------------------------------------------------


def test_delete_rejects_traversal_model():
    """Path traversal model name must be rejected with 400, not silently ignored."""
    client = TestClient(_make_voice_app())

    resp = client.post(
        "/chat/voice/delete-model",
        json={"model": "../../evil"},
    )

    # CURRENTLY FAILS: current code returns 200 {"status": "not_found"} — the
    # traversal is silently accepted and the file just happens not to exist.
    assert resp.status_code == 400, (
        f"Expected 400 for traversal model '../../evil', "
        f"got {resp.status_code}: {resp.text}"
    )


def test_delete_rejects_unknown_model():
    """Unknown model name must be rejected with 400, not silently ignored."""
    client = TestClient(_make_voice_app())

    resp = client.post(
        "/chat/voice/delete-model",
        json={"model": "nonexistent"},
    )

    # CURRENTLY FAILS: current code returns 200 {"status": "not_found"} instead
    # of 400 — callers cannot distinguish "valid model not downloaded" from
    # "completely invalid model name".
    assert resp.status_code == 400, (
        f"Expected 400 for unknown model 'nonexistent', "
        f"got {resp.status_code}: {resp.text}"
    )


# ---------------------------------------------------------------------------
# Happy-path regression guard
# ---------------------------------------------------------------------------


@patch("chat_plugin.voice._whisper_available", True)
@patch(
    "chat_plugin.voice._transcribe_sync",
    return_value={"text": "hello world", "segments": [], "language": "en"},
)
@patch("chat_plugin.voice._convert_audio_to_wav", return_value=b"fake wav bytes")
def test_transcribe_accepts_valid_model(mock_convert, mock_transcribe):
    """Valid model 'base' must NOT be rejected with 400 'Unknown model'.

    This is a regression guard: after the security fix adds model validation,
    'base' (a known good model) must still be accepted.
    """
    client = TestClient(_make_voice_app())
    audio_data = base64.b64encode(b"fake audio bytes").decode()

    resp = client.post(
        "/chat/transcribe",
        json={"audio_data": audio_data, "model": "base"},
    )

    # The response may be 200 (success) or some other status, but must NOT
    # be a 400 with "Unknown model" in the detail.
    if resp.status_code == 400:
        assert "Unknown model" not in resp.text, (
            f"Valid model 'base' should never be rejected as unknown: {resp.text}"
        )
