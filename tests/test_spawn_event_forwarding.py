"""Tests for wrap_tools_for_threading wiring in _spawn_with_event_forwarding.

Verifies that task-5 (Wire wrap_tools_for_threading into spawn.py) correctly
wires the threading wrapper into the spawn event-forwarding path so that tool
execute() calls run off the main event loop, preventing blocking SSE streams.
"""

from __future__ import annotations

import pathlib

SPAWN_PY = pathlib.Path(__file__).parent.parent / "src" / "amplifierd" / "spawn.py"


def source() -> str:
    return SPAWN_PY.read_text()


# ---------------------------------------------------------------------------
# Structural placement: wrap_tools_for_threading after child_session.initialize()
# ---------------------------------------------------------------------------


class TestWrapToolsPlacement:
    """wrap_tools_for_threading must be called immediately after child_session.initialize()
    inside _spawn_with_event_forwarding."""

    def test_wrap_tools_call_exists_in_spawn(self):
        """wrap_tools_for_threading(child_session) call must exist in spawn.py."""
        content = source()
        assert "wrap_tools_for_threading(child_session)" in content, (
            "wrap_tools_for_threading(child_session) not found in spawn.py; "
            "task-5 wiring is missing"
        )

    def test_wrap_tools_called_after_initialize(self):
        """wrap_tools_for_threading must appear AFTER child_session.initialize() in the source."""
        content = source()
        init_pos = content.find("await child_session.initialize()")
        assert init_pos != -1, "child_session.initialize() not found in spawn.py"

        wrap_pos = content.find("wrap_tools_for_threading(child_session)", init_pos)
        assert wrap_pos != -1, (
            "wrap_tools_for_threading(child_session) must appear after "
            "child_session.initialize() — call not found in that position"
        )

    def test_wrap_tools_import_is_local(self):
        """The wrap_tools_for_threading import must be a local inline import
        (inside the function body, not at module level)."""
        content = source()
        # Find the inline import line
        import_line = "from amplifierd.threading import wrap_tools_for_threading"
        assert import_line in content, (
            f"Local import '{import_line}' not found in spawn.py"
        )
        # Verify the import is NOT at the top level (before the first function def)
        first_def_pos = content.find("\ndef ") or content.find("\nasync def ")
        import_pos = content.find(import_line)
        # If the import appears before any function definition, it's a module-level import
        # (which would be wrong per the spec — it should be inline)
        if first_def_pos != -1:
            assert import_pos > first_def_pos, (
                "wrap_tools_for_threading import must be inline (inside the function body), "
                "not at module level"
            )


class TestWrapToolsComment:
    """The required spec comment must document WHY threading is applied."""

    def test_comment_prevents_blocking_sse_exists(self):
        """Comment '# 8b. Wrap tools to run execute() off the event loop ...' must exist."""
        content = source()
        assert "8b. Wrap tools to run execute() off the event loop" in content, (
            "Required spec comment '8b. Wrap tools...' not found in spawn.py"
        )

    def test_comment_mentions_prevents_blocking_sse(self):
        """The comment must mention 'prevents blocking SSE'."""
        content = source()
        assert "prevents blocking SSE" in content, (
            "'prevents blocking SSE' not found in spawn.py comment; "
            "the comment explains WHY threading is needed"
        )


class TestWrapToolsOrdering:
    """wrap_tools_for_threading must appear before self-delegation-depth registration
    (step 9) so tools are wrapped before any further setup that might use them."""

    def test_wrap_tools_before_self_delegation_depth(self):
        """wrap_tools_for_threading must be called before '# 9. Register self-delegation depth'."""
        content = source()
        wrap_pos = content.find("wrap_tools_for_threading(child_session)")
        assert wrap_pos != -1, "wrap_tools_for_threading(child_session) not found"

        step9_pos = content.find("# 9. Register self-delegation depth")
        assert step9_pos != -1, (
            "'# 9. Register self-delegation depth' comment not found"
        )

        assert wrap_pos < step9_pos, (
            "wrap_tools_for_threading must appear before step 9 "
            "(self-delegation depth registration) in spawn.py"
        )
