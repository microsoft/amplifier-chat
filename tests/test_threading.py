"""Tests for ThreadedToolWrapper and wrap_tools_for_threading.

Uses pytest-asyncio in auto mode: all async test functions are treated as
asyncio tests without needing the @pytest.mark.asyncio decorator.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import MagicMock

import pytest

from amplifierd.threading import ThreadedToolWrapper, wrap_tools_for_threading

# ---------------------------------------------------------------------------
# Helpers / fake tools
# ---------------------------------------------------------------------------


class FakeTool:
    """Returns f"result:{input['x']}" from execute."""

    async def execute(self, input):  # noqa: A002
        return f"result:{input['x']}"


class LoopSniffingTool:
    """Captures the id() of the running event loop inside execute."""

    captured_loop_id: int | None = None

    async def execute(self, input):  # noqa: A002
        LoopSniffingTool.captured_loop_id = id(asyncio.get_running_loop())
        return "done"


class ExplodingTool:
    """Raises ValueError('kaboom') from execute."""

    async def execute(self, input):  # noqa: A002
        raise ValueError("kaboom")


class RichTool:
    """Has name, description, and input_schema attributes."""

    name = "rich_tool"
    description = "A tool with many attributes"
    input_schema = {"type": "object", "properties": {"x": {"type": "integer"}}}

    async def execute(self, input):  # noqa: A002
        return "ok"


class SlowTool:
    """Blocks the calling thread for 0.1 s via time.sleep."""

    async def execute(self, input):  # noqa: A002
        time.sleep(0.1)
        return "slow_done"


# ---------------------------------------------------------------------------
# TestThreadedToolWrapper
# ---------------------------------------------------------------------------


class TestThreadedToolWrapper:
    """Unit tests for the ThreadedToolWrapper proxy class."""

    @pytest.mark.asyncio
    async def test_execute_returns_tool_result(self):
        """Wrapper passes through the tool's return value unchanged."""
        wrapper = ThreadedToolWrapper(FakeTool())
        result = await wrapper.execute({"x": 42})
        assert result == "result:42"

    @pytest.mark.asyncio
    async def test_execute_runs_off_event_loop(self):
        """Tool runs in a worker thread with its own event loop."""
        LoopSniffingTool.captured_loop_id = None
        wrapper = ThreadedToolWrapper(LoopSniffingTool())
        main_loop_id = id(asyncio.get_running_loop())

        await wrapper.execute({})

        assert LoopSniffingTool.captured_loop_id is not None
        # asyncio.run() in the worker thread creates a NEW loop
        assert LoopSniffingTool.captured_loop_id != main_loop_id

    @pytest.mark.asyncio
    async def test_execute_propagates_exceptions(self):
        """Exceptions raised inside the tool are re-raised to the caller."""
        wrapper = ThreadedToolWrapper(ExplodingTool())
        with pytest.raises(ValueError, match="kaboom"):
            await wrapper.execute({})

    def test_getattr_proxies_tool_attributes(self):
        """Attribute access on the wrapper is forwarded to the wrapped tool."""
        wrapper = ThreadedToolWrapper(RichTool())
        assert wrapper.name == "rich_tool"
        assert wrapper.description == "A tool with many attributes"
        assert wrapper.input_schema == {
            "type": "object",
            "properties": {"x": {"type": "integer"}},
        }

    def test_repr(self):
        """repr() includes 'ThreadedToolWrapper' and the inner tool's repr."""
        tool = RichTool()
        wrapper = ThreadedToolWrapper(tool)
        r = repr(wrapper)
        assert "ThreadedToolWrapper" in r
        assert repr(tool) in r

    @pytest.mark.asyncio
    async def test_does_not_block_event_loop(self):
        """A blocking tool does not stall the event loop for other coroutines."""

        async def fast_coro():
            return "fast_done"

        wrapper = ThreadedToolWrapper(SlowTool())
        results = await asyncio.gather(wrapper.execute({}), fast_coro())
        assert "slow_done" in results
        assert "fast_done" in results


# ---------------------------------------------------------------------------
# TestWrapToolsForThreading
# ---------------------------------------------------------------------------


class _NamedTool:
    """Minimal stand-in for a tool with a given name."""

    def __init__(self, name: str) -> None:
        self.name = name

    async def execute(self, input):  # noqa: A002
        return "ok"


class TestWrapToolsForThreading:
    """Unit tests for the wrap_tools_for_threading helper."""

    def test_wraps_only_blocking_tools(self):
        """Only tools whose names appear in _NEEDS_THREADING are wrapped."""
        blocking = _NamedTool("read_file")
        passthrough = _NamedTool("delegate")

        coordinator = MagicMock()
        coordinator.get.return_value = [blocking, passthrough]

        session = MagicMock()
        session.coordinator = coordinator

        wrap_tools_for_threading(session)

        coordinator.__setitem__.assert_called_once()
        key, wrapped = coordinator.__setitem__.call_args[0]
        assert key == "tools"
        assert len(wrapped) == 2
        assert isinstance(wrapped[0], ThreadedToolWrapper), (
            "read_file should be wrapped"
        )
        assert wrapped[0]._tool is blocking
        assert wrapped[1] is passthrough, "delegate should stay unwrapped"

    def test_delegate_stays_unwrapped(self):
        """Tools that spawn child sessions (delegate, task, recipes) must NOT be wrapped."""
        for name in (
            "delegate",
            "task",
            "recipes",
            "bash",
            "web_search",
            "todo",
            "mode",
        ):
            tool = _NamedTool(name)
            coordinator = MagicMock()
            coordinator.get.return_value = [tool]
            session = MagicMock()
            session.coordinator = coordinator
            wrap_tools_for_threading(session)
            _, wrapped = coordinator.__setitem__.call_args[0]
            assert wrapped[0] is tool, f"{name!r} should not be wrapped"

    def test_idempotency_guard(self):
        """Calling wrap_tools_for_threading twice does not double-wrap a tool."""
        tool = _NamedTool("grep")
        already_wrapped = ThreadedToolWrapper(tool)

        coordinator = MagicMock()
        coordinator.get.return_value = [already_wrapped]

        session = MagicMock()
        session.coordinator = coordinator

        wrap_tools_for_threading(session)

        _, wrapped = coordinator.__setitem__.call_args[0]
        assert wrapped[0] is already_wrapped, "pre-wrapped tool must not be re-wrapped"
        assert not isinstance(wrapped[0]._tool, ThreadedToolWrapper)

    def test_dict_path_wraps_blocking_tools(self):
        """Dict-path coordinator: blocking tools are wrapped, others stay as-is."""
        blocking = _NamedTool("web_fetch")
        passthrough = _NamedTool("delegate")

        coordinator = {"tools": {"web_fetch": blocking, "delegate": passthrough}}

        class _FakeSession:
            pass

        session = _FakeSession()
        session.coordinator = coordinator  # type: ignore[attr-defined]

        wrap_tools_for_threading(session)

        assert isinstance(coordinator["tools"]["web_fetch"], ThreadedToolWrapper)
        assert coordinator["tools"]["delegate"] is passthrough

    def test_dict_path_idempotency(self):
        """Dict-path: already-wrapped tools are not re-wrapped."""
        tool = _NamedTool("glob")
        coordinator = {"tools": {"glob": ThreadedToolWrapper(tool)}}

        class _FakeSession:
            pass

        session = _FakeSession()
        session.coordinator = coordinator  # type: ignore[attr-defined]

        wrap_tools_for_threading(session)

        result = coordinator["tools"]["glob"]
        assert isinstance(result, ThreadedToolWrapper)
        assert not isinstance(result._tool, ThreadedToolWrapper)

    def test_noop_when_no_tools(self):
        """No error when coordinator.get('tools') returns None."""
        coordinator = MagicMock()
        coordinator.get.return_value = None

        session = MagicMock()
        session.coordinator = coordinator

        # Must not raise
        wrap_tools_for_threading(session)
        coordinator.__setitem__.assert_not_called()

    def test_noop_when_no_coordinator(self):
        """No error when the session object has no attributes at all."""
        session = MagicMock(spec=[])
        # spec=[] → no attributes; getattr(session, "coordinator", None) returns None
        wrap_tools_for_threading(session)  # Must not raise

    def test_noop_when_tools_empty(self):
        """No error when coordinator.get('tools') returns an empty dict."""
        coordinator = MagicMock()
        coordinator.get.return_value = {}

        session = MagicMock()
        session.coordinator = coordinator

        # Empty dict is falsy → early return, no wrapping
        wrap_tools_for_threading(session)  # Must not raise
        coordinator.__setitem__.assert_not_called()
