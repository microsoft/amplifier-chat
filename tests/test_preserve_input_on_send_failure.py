"""
Tests for PR #39: preserve user input when message send fails.

Four changes ensure the textarea is NOT cleared when sendMessage rejects:

1. doSend() is async so it can await onSend
2. doSend() awaits onSend and checks `=== false` before clearing
3. sendMessage() returns false when session is still loading (history resume)
4. sendMessage() returns false when session creation (connect) fails

The happy-path (successful send) must still clear the textarea as before.
"""

import pathlib
import re

import pytest

INDEX_HTML = (
    pathlib.Path(__file__).parent.parent
    / "src"
    / "chat_plugin"
    / "static"
    / "index.html"
)


@pytest.fixture
def html():
    return INDEX_HTML.read_text()


# ---------------------------------------------------------------------------
# 1. doSend is async
# ---------------------------------------------------------------------------


class TestDoSendIsAsync:
    def test_dosend_callback_is_async(self, html):
        """doSend useCallback must be async to allow awaiting onSend."""
        assert "const doSend = useCallback(async () => {" in html

    def test_dosend_is_not_synchronous(self, html):
        """The old synchronous doSend pattern must be gone."""
        assert "const doSend = useCallback(() => {" not in html


# ---------------------------------------------------------------------------
# 2. doSend awaits onSend and checks result before clearing
# ---------------------------------------------------------------------------


class TestDoSendAwaitsResult:
    def test_dosend_awaits_onsend(self, html):
        """doSend must await the onSend call to get the result."""
        assert "const result = await onSend(content, images);" in html

    def test_dosend_checks_result_false(self, html):
        """doSend must check `result === false` and return early (preserving input)."""
        assert "if (result === false) return;" in html

    def test_old_fire_and_forget_onsend_removed(self, html):
        """The old fire-and-forget onSend (no await, no result capture) must be gone."""
        # The old pattern was exactly: "      onSend(content, images);\n"
        # followed immediately by "      ta.value = '';"
        # We check that there's no bare onSend call without result capture
        # near the normal send path.
        pattern = re.compile(
            r"// Normal send path.*?onSend\(content, images\);",
            re.DOTALL,
        )
        match = pattern.search(html)
        # If there's a match, it should be the "await onSend" form
        if match:
            assert "await onSend" in match.group(0)

    def test_textarea_clear_after_result_check(self, html):
        """ta.value = '' must come AFTER the result === false check, not before."""
        result_check_pos = html.find("if (result === false) return;")
        textarea_clear_pos = html.find("ta.value = '';", result_check_pos)
        assert result_check_pos != -1, "result === false check not found"
        assert textarea_clear_pos != -1, "ta.value = '' not found after check"
        assert textarea_clear_pos > result_check_pos, (
            "textarea clear must come after result check"
        )

    def test_pending_images_clear_after_result_check(self, html):
        """setPendingImages([]) must come AFTER the result === false check."""
        result_check_pos = html.find("if (result === false) return;")
        # Find setPendingImages([]) that's in the doSend function (after the check)
        images_clear_pos = html.find("setPendingImages([]);", result_check_pos)
        assert result_check_pos != -1
        assert images_clear_pos != -1
        assert images_clear_pos > result_check_pos


# ---------------------------------------------------------------------------
# 3. sendMessage returns false for session-still-loading
# ---------------------------------------------------------------------------


class TestSendMessageSessionLoading:
    def test_session_loading_returns_false(self, html):
        """sendMessage must return false when session is still loading from history."""
        loading_msg_pos = html.find(
            "Session is still loading. Please wait a moment and try again."
        )
        assert loading_msg_pos != -1, "Session loading message not found"
        # Find the return statement near this message (within ~200 chars after)
        nearby = html[loading_msg_pos : loading_msg_pos + 200]
        assert "return false;" in nearby, (
            f"'return false;' not found near session loading message: {nearby!r}"
        )

    def test_session_loading_does_not_bare_return(self, html):
        """The old bare 'return;' after session loading error must be replaced."""
        loading_msg_pos = html.find(
            "Session is still loading. Please wait a moment and try again."
        )
        assert loading_msg_pos != -1
        nearby = html[loading_msg_pos : loading_msg_pos + 200]
        # Every 'return' in this block must be 'return false'
        returns = [m.start() for m in re.finditer(r"return\b", nearby)]
        for r in returns:
            snippet = nearby[r : r + 15]
            assert "return false" in snippet, (
                f"Found bare return instead of return false: {snippet!r}"
            )


# ---------------------------------------------------------------------------
# 4. sendMessage returns false for session creation failure
# ---------------------------------------------------------------------------


class TestSendMessageConnectFailure:
    def test_connect_failure_returns_false(self, html):
        """sendMessage must return false when connect() returns null."""
        connect_err_pos = html.find("Error: Could not create session.")
        assert connect_err_pos != -1, "Connect failure message not found"
        nearby = html[connect_err_pos : connect_err_pos + 200]
        assert "return false;" in nearby, (
            f"'return false;' not found near connect failure: {nearby!r}"
        )

    def test_connect_failure_does_not_bare_return(self, html):
        """The old bare 'return;' after connect failure must be replaced."""
        connect_err_pos = html.find("Error: Could not create session.")
        assert connect_err_pos != -1
        nearby = html[connect_err_pos : connect_err_pos + 200]
        returns = [m.start() for m in re.finditer(r"return\b", nearby)]
        for r in returns:
            snippet = nearby[r : r + 15]
            assert "return false" in snippet, (
                f"Found bare return instead of return false: {snippet!r}"
            )


# ---------------------------------------------------------------------------
# 5. Happy path — successful send still clears textarea
# ---------------------------------------------------------------------------


class TestHappyPathStillClears:
    def test_textarea_cleared_on_success(self, html):
        """After a successful send (result is not false), ta.value = '' must execute."""
        dosend_pos = html.find("const doSend = useCallback(async () => {")
        assert dosend_pos != -1
        dosend_body = html[dosend_pos : dosend_pos + 800]
        assert "ta.value = '';" in dosend_body
        assert "ta.style.height = 'auto';" in dosend_body
        assert "setPendingImages([]);" in dosend_body
        assert "setSlashOpen(false);" in dosend_body

    def test_queue_path_still_clears_immediately(self, html):
        """The queue path (shouldQueue) still clears textarea immediately — no await needed."""
        dosend_pos = html.find("const doSend = useCallback(async () => {")
        dosend_body = html[dosend_pos : dosend_pos + 800]
        # The queue branch should still have immediate clear
        queue_pos = dosend_body.find("onQueueMessage(content,")
        assert queue_pos != -1
        queue_nearby = dosend_body[queue_pos : queue_pos + 150]
        assert "ta.value = '';" in queue_nearby


# ---------------------------------------------------------------------------
# 6. sendMessage is async (prerequisite for return false to work with await)
# ---------------------------------------------------------------------------


class TestSendMessageIsAsync:
    def test_send_message_is_async(self, html):
        """sendMessage must be an async function (so return false becomes a resolved promise)."""
        assert "const sendMessage = useCallback(async (content, images) => {" in html

    def test_onsend_prop_is_sendmessage(self, html):
        """onSend prop passed to InputArea must be bound to sendMessage."""
        assert "onSend=${sendMessage}" in html
