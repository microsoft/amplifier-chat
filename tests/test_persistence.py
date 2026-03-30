"""Tests for asyncio.to_thread wrapping in MetadataSaveHook.__call__().

Verifies that MetadataSaveHook calls write_metadata via asyncio.to_thread
instead of calling it directly (blocking the event loop).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers / Fakes
# ---------------------------------------------------------------------------


def _make_session(messages: list | None = None) -> MagicMock:
    """Build a minimal session mock with coordinator."""
    if messages is None:
        messages = [{"role": "user", "content": "hello"}]

    context = MagicMock()
    context.get_messages = AsyncMock(return_value=messages)

    coordinator = MagicMock()
    coordinator.get.return_value = context
    coordinator.hooks = MagicMock()
    coordinator.hooks.emit = AsyncMock(return_value=None)

    session = MagicMock()
    session.coordinator = coordinator
    session.session_id = "sess-test-001"
    return session


# ---------------------------------------------------------------------------
# TestMetadataSaveHookUsesAsyncioToThread
# ---------------------------------------------------------------------------


class TestMetadataSaveHookUsesAsyncioToThread:
    """MetadataSaveHook.__call__() must use asyncio.to_thread for write_metadata."""

    @pytest.mark.asyncio
    async def test_metadata_save_hook_uses_to_thread_for_write_metadata(
        self, tmp_path: Path
    ):
        """write_metadata inside MetadataSaveHook is invoked via asyncio.to_thread."""
        from amplifierd.persistence import MetadataSaveHook

        session_dir = tmp_path / "sess-001"
        session_dir.mkdir()

        session = _make_session()
        hook = MetadataSaveHook(session, session_dir)

        mock_to_thread = AsyncMock(return_value=None)

        with patch("asyncio.to_thread", mock_to_thread):
            await hook("orchestrator:complete", {})

        assert mock_to_thread.called, "asyncio.to_thread was never called"
        # First positional arg to to_thread should be write_metadata (a callable)
        first_call_args = mock_to_thread.call_args_list[0][0]
        assert callable(first_call_args[0]), (
            "First argument to asyncio.to_thread should be callable (write_metadata)"
        )

    @pytest.mark.asyncio
    async def test_metadata_save_hook_passes_correct_args_to_to_thread(
        self, tmp_path: Path
    ):
        """asyncio.to_thread receives (write_metadata, session_dir, updates)."""
        from amplifierd.persistence import MetadataSaveHook, write_metadata

        session_dir = tmp_path / "sess-002"
        session_dir.mkdir()

        session = _make_session()
        hook = MetadataSaveHook(session, session_dir)

        mock_to_thread = AsyncMock(return_value=None)

        with patch("asyncio.to_thread", mock_to_thread):
            await hook("orchestrator:complete", {})

        assert mock_to_thread.called, "asyncio.to_thread was never called"
        call_args = mock_to_thread.call_args_list[0][0]
        # call_args: (write_metadata, session_dir, updates_dict)
        assert call_args[0] is write_metadata, (
            "First argument to asyncio.to_thread should be write_metadata"
        )
        assert call_args[1] == session_dir, (
            "Second argument to asyncio.to_thread should be session_dir"
        )
        assert isinstance(call_args[2], dict), (
            "Third argument to asyncio.to_thread should be a dict (metadata updates)"
        )
        assert "turn_count" in call_args[2], (
            "Metadata updates dict must contain 'turn_count'"
        )
        assert "last_updated" in call_args[2], (
            "Metadata updates dict must contain 'last_updated'"
        )

    @pytest.mark.asyncio
    async def test_metadata_save_hook_does_not_call_write_metadata_directly(
        self, tmp_path: Path
    ):
        """write_metadata must NOT be called directly (only via asyncio.to_thread)."""
        from amplifierd.persistence import MetadataSaveHook

        session_dir = tmp_path / "sess-003"
        session_dir.mkdir()

        session = _make_session()
        hook = MetadataSaveHook(session, session_dir)

        mock_to_thread = AsyncMock(return_value=None)
        mock_write_metadata = MagicMock()

        with (
            patch("asyncio.to_thread", mock_to_thread),
            patch("amplifierd.persistence.write_metadata", mock_write_metadata),
        ):
            await hook("orchestrator:complete", {})

        # write_metadata should not be called directly — only via to_thread
        mock_write_metadata.assert_not_called()
