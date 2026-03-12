"""Tests for the feedback analysis endpoint."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from fastapi import FastAPI
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Unit tests for _find_transcript_path
# ---------------------------------------------------------------------------


def test_find_transcript_path(tmp_path):
    """Creates a session dir with transcript.jsonl, verifies it's found."""
    from chat_plugin.feedback import _find_transcript_path

    # Two-level layout: projects_dir/{slug}/sessions/{id}/transcript.jsonl
    sess_dir = tmp_path / "-Users-test" / "sessions" / "sess-123"
    sess_dir.mkdir(parents=True)
    (sess_dir / "transcript.jsonl").write_text(
        json.dumps({"role": "user", "content": "hi"}) + "\n"
    )

    result = _find_transcript_path(tmp_path, "sess-123")
    assert result is not None
    assert result == sess_dir / "transcript.jsonl"


def test_find_transcript_path_missing(tmp_path):
    """Returns None for a session that doesn't exist."""
    from chat_plugin.feedback import _find_transcript_path

    result = _find_transcript_path(tmp_path, "nonexistent-session")
    assert result is None


def test_find_transcript_path_none_dir():
    """Returns None when projects_dir is None."""
    from chat_plugin.feedback import _find_transcript_path

    result = _find_transcript_path(None, "any-session")
    assert result is None


# ---------------------------------------------------------------------------
# Integration tests for the POST /chat/api/feedback/analyze endpoint
# ---------------------------------------------------------------------------


def _make_feedback_app(projects_dir=None, daemon_session_path=None):
    """Create a minimal FastAPI app with only the feedback router."""
    from chat_plugin.feedback import create_feedback_routes

    app = FastAPI()
    router = create_feedback_routes(projects_dir, daemon_session_path)
    app.include_router(router)
    return app


def test_analyze_returns_503_without_projects_dir():
    """Endpoint returns 503 when projects_dir is not configured."""
    app = _make_feedback_app(projects_dir=None)
    client = TestClient(app)

    resp = client.post(
        "/chat/api/feedback/analyze",
        json={"session_id": "sess-123"},
    )
    assert resp.status_code == 503


def test_analyze_returns_404_for_missing_session(tmp_path):
    """Endpoint returns 404 when transcript is not found."""
    app = _make_feedback_app(projects_dir=tmp_path)
    client = TestClient(app)

    resp = client.post(
        "/chat/api/feedback/analyze",
        json={"session_id": "nonexistent-session"},
    )
    assert resp.status_code == 404


def test_analyze_creates_hidden_session(tmp_path):
    """Happy path: mocks async helpers, verifies 200 with analysis_session_id."""
    # Set up a session with a transcript
    sess_dir = tmp_path / "-Users-test" / "sessions" / "sess-abc"
    sess_dir.mkdir(parents=True)
    (sess_dir / "transcript.jsonl").write_text(
        json.dumps({"role": "user", "content": "hello"}) + "\n"
    )

    app = _make_feedback_app(
        projects_dir=tmp_path, daemon_session_path="/tmp/daemon-session"
    )
    client = TestClient(app)

    mock_create = AsyncMock(return_value="analysis-sess-001")
    mock_hide = AsyncMock()
    mock_kick = AsyncMock()

    with (
        patch("chat_plugin.feedback._create_analysis_session", mock_create),
        patch("chat_plugin.feedback._mark_session_hidden", mock_hide),
        patch("chat_plugin.feedback._kick_off_execution", mock_kick),
    ):
        resp = client.post(
            "/chat/api/feedback/analyze",
            json={"session_id": "sess-abc"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["analysis_session_id"] == "analysis-sess-001"

    mock_create.assert_called_once()
    mock_hide.assert_called_once()
    mock_kick.assert_called_once()


def test_analyze_rejects_invalid_body():
    """Empty JSON body returns 422."""
    app = _make_feedback_app(projects_dir="/tmp")
    client = TestClient(app)

    resp = client.post(
        "/chat/api/feedback/analyze",
        json={},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Unit tests for _safe_kick_off
# ---------------------------------------------------------------------------


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
