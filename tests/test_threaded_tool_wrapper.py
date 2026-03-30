"""Tests for ThreadedToolWrapper and wrap_tools_for_threading."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from amplifierd.threading import ThreadedToolWrapper, wrap_tools_for_threading


class TestThreadedToolWrapperImport:
    """Verify the module and its exports are importable."""

    def test_imports_cleanly(self):
        assert ThreadedToolWrapper is not None
        assert wrap_tools_for_threading is not None


class TestThreadedToolWrapper:
    """Tests for ThreadedToolWrapper proxy class."""

    def _make_tool(self, return_value: Any = "result"):
        """Create a simple mock tool with async execute."""

        class MockTool:
            name = "mock_tool"
            description = "A mock tool for testing"

            async def execute(self, input):
                return return_value

        return MockTool()

    def test_init_stores_tool(self):
        tool = self._make_tool()
        wrapper = ThreadedToolWrapper(tool)
        # The wrapper should store the underlying tool
        assert wrapper._tool is tool

    def test_getattr_proxies_to_tool(self):
        tool = self._make_tool()
        wrapper = ThreadedToolWrapper(tool)
        # Should proxy attribute access to underlying tool
        assert wrapper.name == "mock_tool"
        assert wrapper.description == "A mock tool for testing"

    def test_repr_includes_tool_info(self):
        tool = self._make_tool()
        wrapper = ThreadedToolWrapper(tool)
        r = repr(wrapper)
        assert "ThreadedToolWrapper" in r

    @pytest.mark.asyncio
    async def test_execute_runs_tool_off_event_loop(self):
        """execute() should run the tool's coroutine in a thread via asyncio.to_thread."""
        tool = self._make_tool(return_value="thread_result")
        wrapper = ThreadedToolWrapper(tool)
        result = await wrapper.execute("test_input")
        assert result == "thread_result"

    @pytest.mark.asyncio
    async def test_execute_uses_double_loop_pattern(self):
        """The coroutine is created eagerly on main thread and run in thread pool."""
        execution_loop = None

        class LoopCapturingTool:
            async def execute(self, input):
                nonlocal execution_loop
                # asyncio.run() creates a new event loop in the worker thread
                # so get_running_loop should return a DIFFERENT loop than the main one
                execution_loop = asyncio.get_running_loop()
                return "done"

        tool = LoopCapturingTool()
        wrapper = ThreadedToolWrapper(tool)
        main_loop = asyncio.get_running_loop()
        await wrapper.execute("input")
        # The tool should have run in a different event loop (thread's loop)
        assert execution_loop is not main_loop

    @pytest.mark.asyncio
    async def test_execute_with_none_input(self):
        tool = self._make_tool(return_value=None)
        wrapper = ThreadedToolWrapper(tool)
        result = await wrapper.execute(None)
        assert result is None


class TestWrapToolsForThreading:
    """Tests for wrap_tools_for_threading helper function."""

    def _make_session_with_tools(self, tools):
        """Build a minimal fake session with coordinator and tools."""

        class FakeCoordinator(dict):
            pass

        coordinator = FakeCoordinator()
        coordinator["tools"] = tools

        class FakeSession:
            coordinator: Any = None

        session = FakeSession()
        session.coordinator = coordinator
        return session

    def test_wraps_all_tools(self):
        class FakeTool:
            async def execute(self, input):
                return "ok"

        tools = [FakeTool(), FakeTool()]
        session = self._make_session_with_tools(tools)
        wrap_tools_for_threading(session)
        wrapped = session.coordinator["tools"]
        assert len(wrapped) == 2
        for w in wrapped:
            assert isinstance(w, ThreadedToolWrapper)

    def test_no_coordinator_is_safe(self):
        class FakeSession:
            pass  # No coordinator attribute

        session = FakeSession()
        # Should not raise
        wrap_tools_for_threading(session)

    def test_none_coordinator_is_safe(self):
        class FakeSession:
            coordinator = None

        session = FakeSession()
        # Should not raise
        wrap_tools_for_threading(session)

    def test_empty_tools_list(self):
        # The `if not tools` guard fires for an empty list and returns early,
        # leaving the "tools" key untouched — intentional no-op for empty list.
        session = self._make_session_with_tools([])
        wrap_tools_for_threading(session)
        assert session.coordinator["tools"] == []

    def test_tools_key_missing_is_safe(self):
        class FakeCoordinator(dict):
            pass

        class FakeSession:
            coordinator = FakeCoordinator()  # no 'tools' key

        session = FakeSession()
        # Should not raise
        wrap_tools_for_threading(session)
