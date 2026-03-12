"""
Tests for InputArea modifications (Tasks 3-6, Chunk 2).

These tests verify the HTML file contains the expected code for:
- Task 3: New props in InputArea signature and ChatApp render
- Task 4: doSend routes messages to queue when shouldQueue is true
- Task 5: Textarea stays enabled during execution (no disabled attr, opacity 1)
- Task 6: Both Send and Stop buttons shown separately during execution
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


class TestTask3InputAreaSignature:
    def test_inputarea_signature_has_onqueuemessage(self, html_content):
        """InputArea function signature includes onQueueMessage prop (queueCount removed as unused)."""
        assert (
            "function InputArea({ onSend, onStop, onQueueMessage, executing, shouldQueue, viewMode, setViewMode, activeKey })"
            in html_content
        )

    def test_chatapp_render_passes_onqueuemessage(self, html_content):
        """ChatApp renders InputArea with onQueueMessage prop bound to pushToQueue."""
        assert "onQueueMessage=${pushToQueue}" in html_content

    def test_chatapp_render_passes_shouldqueue(self, html_content):
        """ChatApp renders InputArea with shouldQueue prop."""
        assert (
            "shouldQueue=${executing || getQueueDrainState() === 'countdown'}"
            in html_content
        )

    def test_chatapp_render_no_queuecount(self, html_content):
        """ChatApp no longer passes queueCount to InputArea (unused prop removed)."""
        assert "queueCount=${getQueue().length}" not in html_content


class TestTask4DoSendQueueRouting:
    def test_dosend_routes_to_queue_when_shouldqueue(self, html_content):
        """doSend calls onQueueMessage when shouldQueue is true and not a slash command."""
        assert "if (shouldQueue && !content.startsWith('/')) {" in html_content

    def test_dosend_calls_onqueuemessage(self, html_content):
        """doSend calls onQueueMessage with content and images."""
        assert (
            "onQueueMessage(content, pendingImages.map(d => d.split(',')[1]));"
            in html_content
        )

    def test_dosend_no_longer_guards_on_executing(self, html_content):
        """doSend no longer returns early on executing (old guard removed)."""
        assert "if (executing) return;" not in html_content

    def test_dosend_deps_include_shouldqueue_and_onqueuemessage(self, html_content):
        """doSend useCallback deps include shouldQueue and onQueueMessage."""
        assert "[onSend, onQueueMessage, pendingImages, shouldQueue]" in html_content

    def test_dosend_slash_commands_bypass_queue(self, html_content):
        """The comment about slash commands bypassing queue is present."""
        assert (
            "Slash commands always bypass the queue and send directly" in html_content
        )


class TestTask5TextareaEnabled:
    def test_textarea_placeholder_says_queue(self, html_content):
        """Textarea placeholder says 'Queue a message…' when executing."""
        assert (
            'placeholder=${executing ? "Queue a message\\u2026" : "Message\\u2026 (/ for commands)"}'
            in html_content
            or 'placeholder=${executing ? "Queue a message\u2026" : "Message\u2026 (/ for commands)"}'
            in html_content
        )

    def test_textarea_not_disabled(self, html_content):
        """Textarea no longer has disabled=${executing} attribute."""
        assert "disabled=${executing}" not in html_content

    def test_textarea_opacity_always_1(self, html_content):
        """Textarea style opacity is always 1, not conditional on executing."""
        assert "style=${{ opacity: 1 }}" in html_content
        assert "style=${{ opacity: executing ? 0.6 : 1 }}" not in html_content

    def test_autofocus_effect_no_disabled_check(self, html_content):
        """Auto-focus useEffect no longer checks ta.disabled."""
        assert "if (!ta || ta.disabled) return;" not in html_content


class TestTask6SeparateButtons:
    def test_send_button_always_rendered(self, html_content):
        """Send button is always rendered (not inside the ternary)."""
        assert '<button class="input-btn send-btn" onClick=${doSend}>' in html_content

    def test_send_button_label_is_queue_or_send(self, html_content):
        """Send button label changes to 'Queue' when shouldQueue is true."""
        assert "${shouldQueue ? 'Queue' : 'Send'}" in html_content

    def test_stop_button_conditional_on_executing(self, html_content):
        """Stop button is shown only when executing (not via ternary toggling Send off)."""
        assert (
            '${executing && html`<button class="input-btn stop-btn" onClick=${onStop}>\\u25a0 Stop</button>`}'
            in html_content
            or '${executing && html`<button class="input-btn stop-btn" onClick=${onStop}>\u25a0 Stop</button>`}'
            in html_content
        )

    def test_old_ternary_removed(self, html_content):
        """The old executing ternary that showed EITHER Send OR Stop is removed."""
        assert (
            '${executing\n            ? html`<button class="input-btn stop-btn"'
            not in html_content
        )
