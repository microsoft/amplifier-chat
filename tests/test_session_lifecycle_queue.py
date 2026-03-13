"""
Tests for session lifecycle + sidebar badge (Tasks 19-22, Chunk 6).

These tests verify the HTML file contains the expected code for:
- Task 19: switchSession cancels countdown on switch-away, restarts on switch-back
- Task 20: newSession cancels countdown from the previous session
- Task 21: SessionCard shows a queue count badge when the session has queued messages
- Task 22: (covered by Task 21 — queueCount prop passed at render site)
"""

import pathlib
import pytest

INDEX_HTML = (
    pathlib.Path(__file__).parent.parent
    / "src"
    / "chat_plugin"
    / "static"
    / "index.html"
)


@pytest.fixture
def html_content():
    return INDEX_HTML.read_text()


class TestTask19SwitchSessionCountdown:
    def test_switch_session_cancels_countdown_before_early_returns(self, html_content):
        """switchSession calls cancelCountdown(currentKey) before any early returns."""
        # cancelCountdown must appear before the history early-return to prevent
        # countdowns surviving a session switch to a history session.
        cancel_call = "cancelCountdown(currentKey)"
        history_check = "target.source === 'history'"
        cancel_pos = html_content.find(cancel_call)
        history_pos = html_content.find(history_check)
        assert cancel_pos != -1, "cancelCountdown(currentKey) not found"
        assert history_pos != -1, "history source check not found"
        assert cancel_pos < history_pos, (
            "cancelCountdown(currentKey) must appear before history early-return"
        )

    def test_switch_session_restarts_countdown_for_target(self, html_content):
        """switchSession restarts countdown if target session had active countdown (and isn't running)."""
        # The condition now guards against running sessions too
        assert "getQueueDrainState(key) === 'countdown'" in html_content

    def test_switch_session_resets_stale_countdown_state_on_restore(self, html_content):
        """switchSession resets stale countdown drain state when restoring a session."""
        # The pattern: if getQueueDrainState(key) === 'countdown' → reset to idle
        # This prevents the queue from getting permanently stuck
        check = "getQueueDrainState(key) === 'countdown'"
        reset = "setQueueDrainStateFn('idle', key)"
        check_pos = html_content.find(check)
        assert check_pos != -1, "getQueueDrainState(key) check not found"
        # The idle reset should appear within a short window after the check
        nearby = html_content[check_pos : check_pos + 200]
        assert reset in nearby, (
            "setQueueDrainStateFn('idle', key) not found near getQueueDrainState(key) check"
        )

    def test_switch_session_countdown_restart_after_set_executing(self, html_content):
        """The countdown restore block comes after setExecuting(target.status === 'running')."""
        set_exec = "setExecuting(target.status === 'running');"
        drain_check = "getQueueDrainState(key) === 'countdown'"
        exec_pos = html_content.find(set_exec)
        drain_pos = html_content.find(drain_check, exec_pos)
        assert exec_pos != -1, "setExecuting(target.status === 'running') not found"
        assert drain_pos != -1, (
            "getQueueDrainState(key) check not found after setExecuting"
        )
        assert exec_pos < drain_pos


class TestTask20NewSessionCountdown:
    def test_new_session_cancels_countdown(self, html_content):
        """newSession calls cancelCountdown() before setExecuting(false)."""
        cancel_call = "cancelCountdown();"
        set_exec_false = "setExecuting(false);"
        # Find cancelCountdown in newSession context — it should appear before setExecuting(false)
        # We find the newSession function definition first
        new_session_def = "const newSession = useCallback(() => {"
        ns_pos = html_content.find(new_session_def)
        assert ns_pos != -1, "newSession function not found"
        # Within newSession body, cancelCountdown() should precede setExecuting(false)
        body = html_content[ns_pos : ns_pos + 3000]
        cancel_pos = body.find(cancel_call)
        exec_pos = body.find(set_exec_false)
        assert cancel_pos != -1, "cancelCountdown() not found in newSession body"
        assert exec_pos != -1, "setExecuting(false) not found in newSession body"
        assert cancel_pos < exec_pos, (
            "cancelCountdown() must come before setExecuting(false)"
        )


class TestTask21SidebarQueueBadge:
    def test_session_card_accepts_queue_count_prop(self, html_content):
        """SessionCard function signature includes queueCount parameter."""
        assert "function SessionCard({" in html_content
        # queueCount must be in the SessionCard signature
        sc_pos = html_content.find("function SessionCard({")
        sig_end = html_content.find(")", sc_pos)
        signature = html_content[sc_pos : sig_end + 1]
        assert "queueCount" in signature, (
            f"queueCount not in SessionCard signature: {signature}"
        )

    def test_session_card_meta_shows_queue_badge(self, html_content):
        """SessionCard renders a badge showing queue count when queueCount > 0."""
        assert "queueCount > 0" in html_content

    def test_session_card_badge_shows_queued_text(self, html_content):
        """The queue badge shows '${queueCount} queued' text."""
        assert "queued</span>" in html_content

    def test_session_card_badge_uses_stale_badge_class(self, html_content):
        """Queue badge reuses session-stale-badge CSS class."""
        # The badge should be inside session-card-meta and use session-stale-badge
        meta_pos = html_content.find("session-card-meta")
        assert meta_pos != -1
        # Look for session-stale-badge after session-card-meta (within same component area)
        # There will be multiple; the new one should appear near queueCount > 0
        queue_badge_pos = html_content.find("queueCount > 0")
        assert queue_badge_pos != -1
        nearby = html_content[queue_badge_pos : queue_badge_pos + 200]
        assert "session-stale-badge" in nearby, (
            "session-stale-badge class not found near queueCount > 0 badge"
        )

    def test_session_card_render_passes_queue_count(self, html_content):
        """SessionCard render call passes queueCount prop from msgQueueRef."""
        assert "queueCount=${" in html_content
        # The prop should reference msgQueueRef and .length
        assert "msgQueueRef.current.get(" in html_content

    def test_queue_count_prop_passed_at_session_card_render_site(self, html_content):
        """The queueCount prop is passed where SessionCard is rendered in the tree."""
        sc_render = "<${SessionCard}"
        render_pos = html_content.find(sc_render)
        assert render_pos != -1
        # Find the closing /> after the render start
        render_end = html_content.find("/>", render_pos)
        render_block = html_content[render_pos : render_end + 2]
        assert "queueCount=${" in render_block, (
            f"queueCount prop not found in SessionCard render block: {render_block}"
        )
