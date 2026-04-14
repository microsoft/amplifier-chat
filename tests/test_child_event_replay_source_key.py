"""
Tests for S-08: Pass ownerKey as sourceKey in child event replay.

Bug: When session_fork flushes buffered child events via
pendingChildEventsRef, it calls handleWsMessage(bufferedMsg) without
passing sourceKey. If the active session has changed since the events
were buffered, they get routed to the wrong session.

Fix: Pass ownerKey as the second argument so replayed events always
target the correct parent session:
  handleWsMessage(bufferedMsg, ownerKey);
"""

import pathlib

INDEX_HTML = (
    pathlib.Path(__file__).parent.parent
    / "src"
    / "chat_plugin"
    / "static"
    / "index.html"
)


def html():
    return INDEX_HTML.read_text()


class TestChildEventReplaySourceKey:
    def test_buffered_replay_passes_owner_key(self):
        """handleWsMessage(bufferedMsg, ownerKey) must appear in session_fork flush."""
        content = html()
        assert "handleWsMessage(bufferedMsg, ownerKey)" in content, (
            "Buffered child event replay must pass ownerKey as sourceKey"
        )

    def test_no_bare_handle_ws_message_buffered_msg(self):
        """handleWsMessage(bufferedMsg) without sourceKey must not exist."""
        content = html()
        # Find the session_fork handler and check there's no bare call
        fork_start = content.find("case 'session_fork':")
        assert fork_start != -1, "session_fork case not found"
        fork_end = content.find("case '", fork_start + 20)
        fork_body = content[fork_start:fork_end]
        assert (
            "handleWsMessage(bufferedMsg)" not in fork_body
            or "handleWsMessage(bufferedMsg, ownerKey)" in fork_body
        ), "session_fork must not call handleWsMessage(bufferedMsg) without ownerKey"
