"""Tests for SessionHandle — asyncio.Lock serialisation and status tracking."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amplifierd.state.session_handle import SessionHandle, SessionStatus


# ---------------------------------------------------------------------------
# Helpers / Fakes
# ---------------------------------------------------------------------------


def _make_fake_session(session_id: str = "sess-001") -> MagicMock:
    session = MagicMock()
    session.session_id = session_id
    session.parent_id = None
    # Silence coordinator.hooks/set access
    session.coordinator = MagicMock()
    session.coordinator.hooks = None
    return session


def _make_handle(session_id: str = "sess-001") -> SessionHandle:
    session = _make_fake_session(session_id)
    event_bus = MagicMock()
    event_bus.publish = MagicMock()
    event_bus.register_child = MagicMock()
    with patch("amplifierd.state.session_handle.SessionHandle._wire_display"):
        handle = SessionHandle(
            session=session,
            prepared_bundle=None,
            bundle_name="test-bundle",
            event_bus=event_bus,
            working_dir=None,
        )
    return handle


# ---------------------------------------------------------------------------
# Tests: asyncio.Lock exists on the handle
# ---------------------------------------------------------------------------


class TestExecuteLockExists:
    """SessionHandle.__init__ must create an asyncio.Lock on _execute_lock."""

    def test_execute_lock_is_asyncio_lock(self):
        handle = _make_handle()
        assert hasattr(handle, "_execute_lock"), "_execute_lock attribute missing"
        assert isinstance(handle._execute_lock, asyncio.Lock), (
            "_execute_lock must be an asyncio.Lock"
        )


# ---------------------------------------------------------------------------
# Tests: execute() status management
# ---------------------------------------------------------------------------


class TestExecuteSetsStatus:
    """execute() must transition status IDLE → EXECUTING → IDLE on success."""

    @pytest.mark.asyncio
    async def test_execute_sets_status(self):
        handle = _make_handle()
        handle._session.execute = AsyncMock(return_value="ok")

        assert handle.status == SessionStatus.IDLE
        result = await handle.execute("hello")
        assert result == "ok"
        assert handle.status == SessionStatus.IDLE

    @pytest.mark.asyncio
    async def test_execute_failure_sets_failed_status(self):
        handle = _make_handle()
        handle._session.execute = AsyncMock(side_effect=RuntimeError("boom"))

        with pytest.raises(RuntimeError, match="boom"):
            await handle.execute("hello")

        assert handle.status == SessionStatus.FAILED


class TestTurnCounter:
    """execute() must increment _turn_count on each call."""

    @pytest.mark.asyncio
    async def test_turn_counter(self):
        handle = _make_handle()
        handle._session.execute = AsyncMock(return_value="ok")

        assert handle.turn_count == 0
        await handle.execute("first")
        assert handle.turn_count == 1
        await handle.execute("second")
        assert handle.turn_count == 2


# ---------------------------------------------------------------------------
# Tests: asyncio.Lock serialisation / fast-fail
# ---------------------------------------------------------------------------


class TestExecuteLockSerialisation:
    """execute() must raise RuntimeError when called while lock is already held."""

    @pytest.mark.asyncio
    async def test_concurrent_execute_raises_runtime_error(self):
        """Second execute() while first is running must raise RuntimeError immediately."""
        handle = _make_handle()

        # Simulate a long-running execute
        gate = asyncio.Event()

        async def slow_execute(prompt: str):
            await gate.wait()
            return "done"

        handle._session.execute = slow_execute

        # Start the first execute (won't finish until gate is set)
        first_task = asyncio.ensure_future(handle.execute("first"))
        # Give event loop a chance to start executing
        await asyncio.sleep(0)

        # Second call should raise because lock is locked
        with pytest.raises(RuntimeError, match="already executing"):
            await handle.execute("second")

        # Clean up
        gate.set()
        await first_task

    @pytest.mark.asyncio
    async def test_execute_uses_lock_locked_check(self):
        """execute() fast-fail uses lock.locked() not status flag comparison."""
        handle = _make_handle()
        handle._session.execute = AsyncMock(return_value="ok")

        # Manually acquire the lock to simulate concurrent execution
        async with handle._execute_lock:
            with pytest.raises(RuntimeError, match="already executing"):
                await handle.execute("should fail")
