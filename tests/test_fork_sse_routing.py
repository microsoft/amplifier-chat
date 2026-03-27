"""
Tests for fork SSE routing fix.

Bug: When a user forks a session, sessionParentByIdRef[fork_id] = parent_id is set.
Later, when SSE events arrive for the forked session, the SSE router injects
child_session_id: fork_id onto every event. This was designed for delegate
sub-sessions, but fires for user forks too.

With child_session_id injected, every event hits the "Fix A" buffer:
    if (msg.child_session_id && !childToToolRef.current[msg.child_session_id]) {
        buf.push(msg);
        ...
        return;  // ALL EVENTS SWALLOWED
    }

The buffer waits for a session_fork (delegate spawn) event that never comes
for user forks. The UI appears frozen.

Fix: Guard the effectiveMsg injection with isOwnSession -- only inject
child_session_id when routing to a DIFFERENT (parent) session. When the
ownerKey resolves to the session that IS eventSessionId, it's a user-initiated
fork and events must route directly (no injection).
"""

import pathlib

INDEX_HTML = (
    pathlib.Path(__file__).parent.parent
    / "src"
    / "chat_plugin"
    / "static"
    / "index.html"
)


def html() -> str:
    return INDEX_HTML.read_text()


# ---------------------------------------------------------------------------
# SSE fork routing guard
# ---------------------------------------------------------------------------


class TestForkSseRoutingGuard:
    def test_isOwnSession_variable_exists(self):
        """The isOwnSession guard variable must exist in index.html."""
        content = html()
        assert "isOwnSession" in content, (
            "isOwnSession guard variable not found in index.html; "
            "the fork SSE routing fix has not been applied"
        )

    def test_effectiveMsg_excludes_own_session(self):
        """effectiveMsg condition must include !isOwnSession guard."""
        content = html()
        # Locate the effectiveMsg assignment near the SSE router
        effective_pos = content.find("const effectiveMsg = ")
        assert effective_pos != -1, "effectiveMsg assignment not found in index.html"
        # Extract a window large enough to contain the full ternary expression
        block = content[effective_pos : effective_pos + 400]
        assert "!isOwnSession" in block, (
            "!isOwnSession guard not found in effectiveMsg condition; "
            "user-fork events will incorrectly have child_session_id injected"
        )

    def test_user_fork_comment_exists(self):
        """A comment explaining user-initiated fork behaviour must exist near the fix."""
        content = html()
        # The comment must mention user-initiated forks
        assert (
            "user-initiated forks" in content.lower()
            or "user-initiated fork" in content.lower()
        ), (
            "Comment about user-initiated forks not found near effectiveMsg fix; "
            "add a comment explaining why isOwnSession prevents injection for user forks"
        )
