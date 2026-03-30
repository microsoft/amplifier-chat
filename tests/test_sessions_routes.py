"""Tests for write_metadata wrapping in sessions.py route handlers.

Verifies that both `patch_session` and `update_metadata` call
`write_metadata` via `asyncio.to_thread` instead of calling it directly.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers / Fakes
# ---------------------------------------------------------------------------


def _make_manager(session_dir: Path | None = None) -> MagicMock:
    """Build a minimal SessionManager mock."""
    manager = MagicMock()
    manager.get.return_value = None  # no live handle by default
    manager.resolve_session_dir.return_value = session_dir
    return manager


def _make_request(manager: MagicMock) -> MagicMock:
    """Build a minimal FastAPI Request mock."""
    request = MagicMock()
    request.app.state.session_manager = manager
    request.app.state.event_bus = None
    request.url.path = "/sessions/test-id"
    return request


# ---------------------------------------------------------------------------
# TestPatchSessionWriteMetadataAsync
# ---------------------------------------------------------------------------


class TestPatchSessionWriteMetadataAsync:
    """patch_session must use asyncio.to_thread when writing metadata."""

    @pytest.mark.asyncio
    async def test_patch_session_uses_to_thread_for_write_metadata(self, tmp_path):
        """write_metadata inside patch_session is invoked via asyncio.to_thread."""
        from amplifierd.routes.sessions import patch_session
        from amplifierd.models.sessions import PatchSessionRequest  # type: ignore[import]

        session_dir = tmp_path / "sess-001"
        session_dir.mkdir()

        manager = _make_manager(session_dir=session_dir)
        request = _make_request(manager)

        body = PatchSessionRequest(name="new-name", working_dir=None)

        mock_to_thread = AsyncMock(return_value=None)

        with (
            patch("asyncio.to_thread", mock_to_thread),
            patch("amplifierd.persistence.write_metadata"),
        ):
            await patch_session(request, "sess-001", body)

        assert mock_to_thread.called, "asyncio.to_thread was never called"
        # First positional arg should be write_metadata (a callable)
        first_call_args = mock_to_thread.call_args_list[0][0]
        assert callable(first_call_args[0]), (
            "First argument to asyncio.to_thread should be callable"
        )

    @pytest.mark.asyncio
    async def test_patch_session_passes_correct_args_to_to_thread(self, tmp_path):
        """asyncio.to_thread receives (write_metadata, session_dir, metadata_updates)."""
        from amplifierd.routes.sessions import patch_session
        from amplifierd.models.sessions import PatchSessionRequest  # type: ignore[import]

        session_dir = tmp_path / "sess-002"
        session_dir.mkdir()

        manager = _make_manager(session_dir=session_dir)
        request = _make_request(manager)

        body = PatchSessionRequest(name="renamed", working_dir=None)

        mock_to_thread = AsyncMock(return_value=None)

        with (
            patch("asyncio.to_thread", mock_to_thread),
            patch("amplifierd.persistence.write_metadata"),
        ):
            await patch_session(request, "sess-002", body)

        assert mock_to_thread.called, "asyncio.to_thread was never called"
        call_args = mock_to_thread.call_args_list[0][0]  # positional args of first call
        # call_args: (write_metadata, session_dir, metadata_updates)
        assert len(call_args) == 3, f"Expected 3 args, got {len(call_args)}"
        assert call_args[1] == session_dir, (
            f"Expected session_dir={session_dir}, got {call_args[1]}"
        )
        assert call_args[2] == {"name": "renamed"}, (
            f"Expected metadata_updates, got {call_args[2]}"
        )

    @pytest.mark.asyncio
    async def test_patch_session_skips_write_when_no_updates(self, tmp_path):
        """No asyncio.to_thread call when body has no name or working_dir."""
        from amplifierd.routes.sessions import patch_session
        from amplifierd.models.sessions import PatchSessionRequest  # type: ignore[import]

        session_dir = tmp_path / "sess-003"
        session_dir.mkdir()

        manager = _make_manager(session_dir=session_dir)
        request = _make_request(manager)

        body = PatchSessionRequest(name=None, working_dir=None)

        mock_to_thread = AsyncMock(return_value=None)

        with (
            patch("asyncio.to_thread", mock_to_thread),
            patch("amplifierd.persistence.write_metadata"),
        ):
            await patch_session(request, "sess-003", body)

        assert not mock_to_thread.called, (
            "asyncio.to_thread should not be called when there are no updates"
        )


# ---------------------------------------------------------------------------
# TestUpdateMetadataWriteMetadataAsync
# ---------------------------------------------------------------------------


class TestUpdateMetadataWriteMetadataAsync:
    """update_metadata must use asyncio.to_thread when writing metadata."""

    @pytest.mark.asyncio
    async def test_update_metadata_uses_to_thread_for_write_metadata(self, tmp_path):
        """write_metadata inside update_metadata is invoked via asyncio.to_thread."""
        from amplifierd.routes.sessions import update_metadata

        session_dir = tmp_path / "sess-010"
        session_dir.mkdir()

        manager = _make_manager(session_dir=session_dir)
        request = _make_request(manager)

        body = {"tag": "important"}

        mock_to_thread = AsyncMock(return_value=None)

        with (
            patch("asyncio.to_thread", mock_to_thread),
            patch("amplifierd.persistence.write_metadata"),
        ):
            await update_metadata(request, "sess-010", body)

        assert mock_to_thread.called, "asyncio.to_thread was never called"
        first_call_args = mock_to_thread.call_args_list[0][0]
        assert callable(first_call_args[0]), (
            "First argument to asyncio.to_thread should be callable"
        )

    @pytest.mark.asyncio
    async def test_update_metadata_passes_correct_args_to_to_thread(self, tmp_path):
        """asyncio.to_thread receives (write_metadata, session_dir, body)."""
        from amplifierd.routes.sessions import update_metadata

        session_dir = tmp_path / "sess-011"
        session_dir.mkdir()

        manager = _make_manager(session_dir=session_dir)
        request = _make_request(manager)

        body = {"priority": "high", "tag": "release"}

        mock_to_thread = AsyncMock(return_value=None)

        with (
            patch("asyncio.to_thread", mock_to_thread),
            patch("amplifierd.persistence.write_metadata"),
        ):
            await update_metadata(request, "sess-011", body)

        assert mock_to_thread.called, "asyncio.to_thread was never called"
        call_args = mock_to_thread.call_args_list[0][0]  # positional args of first call
        # call_args: (write_metadata, session_dir, body)
        assert len(call_args) == 3, f"Expected 3 args, got {len(call_args)}"
        assert call_args[1] == session_dir, (
            f"Expected session_dir={session_dir}, got {call_args[1]}"
        )
        assert call_args[2] == body, f"Expected body={body}, got {call_args[2]}"

    @pytest.mark.asyncio
    async def test_update_metadata_returns_404_when_no_session_dir(self):
        """Returns 404 when session directory cannot be resolved."""
        from amplifierd.routes.sessions import update_metadata
        from fastapi import HTTPException

        manager = _make_manager(session_dir=None)
        request = _make_request(manager)

        body = {"tag": "test"}

        with pytest.raises(HTTPException) as exc_info:
            await update_metadata(request, "nonexistent", body)

        assert exc_info.value.status_code == 404
