"""
Tests for QueuePanel component (Tasks 7-9, Chunk 3).

These tests verify the HTML file contains the expected code for:
- Task 7: QueuePanel CSS classes in the <style> block
- Task 8: QueuePanel function component definition
- Task 9: QueuePanel wired into ChatApp layout between MessageList and InputArea
"""

import pathlib
import pytest

INDEX_HTML = pathlib.Path(__file__).parent.parent / "src" / "chat_plugin" / "static" / "index.html"


@pytest.fixture
def html_content():
    return INDEX_HTML.read_text()


class TestTask7QueuePanelCSS:
    def test_queue_panel_class_in_style(self, html_content):
        """.queue-panel CSS class is present in <style> block."""
        assert ".queue-panel {" in html_content

    def test_queue_panel_header_class_in_style(self, html_content):
        """.queue-panel-header CSS class is present."""
        assert ".queue-panel-header {" in html_content

    def test_queue_item_class_in_style(self, html_content):
        """.queue-item CSS class is present."""
        assert ".queue-item {" in html_content

    def test_queue_item_countdown_class_in_style(self, html_content):
        """.queue-item--countdown modifier class is present."""
        assert ".queue-item--countdown {" in html_content

    def test_queue_item_paused_class_in_style(self, html_content):
        """.queue-item--paused modifier class is present."""
        assert ".queue-item--paused {" in html_content

    def test_queue_item_text_class_in_style(self, html_content):
        """.queue-item-text CSS class is present."""
        assert ".queue-item-text {" in html_content

    def test_queue_item_remove_class_in_style(self, html_content):
        """.queue-item-remove CSS class is present."""
        assert ".queue-item-remove {" in html_content

    def test_queue_panel_btn_class_in_style(self, html_content):
        """.queue-panel-btn CSS class is present."""
        assert ".queue-panel-btn {" in html_content

    def test_pulse_border_animation_in_style(self, html_content):
        """pulse-border keyframe animation is defined."""
        assert "@keyframes pulse-border {" in html_content

    def test_queue_panel_mobile_max_height(self, html_content):
        """Mobile media query reduces queue-panel max-height to 25vh."""
        assert ".queue-panel { max-height: 25vh; }" in html_content

    def test_css_comes_before_close_style_tag(self, html_content):
        """QueuePanel CSS is inserted before </style>."""
        css_pos = html_content.find(".queue-panel {")
        style_close_pos = html_content.find("</style>")
        assert css_pos != -1
        assert style_close_pos != -1
        assert css_pos < style_close_pos


class TestTask8QueuePanelComponent:
    def test_queuepanel_function_exists(self, html_content):
        """QueuePanel function component is defined."""
        assert "function QueuePanel({" in html_content

    def test_queuepanel_accepts_queue_prop(self, html_content):
        """QueuePanel accepts queue prop."""
        assert "function QueuePanel({ queue, drainState, countdownSecs, onRemove, onResume })" in html_content

    def test_queuepanel_returns_null_when_empty(self, html_content):
        """QueuePanel returns null when queue is empty."""
        assert "if (!queue || queue.length === 0) return null;" in html_content

    def test_queuepanel_checks_paused_state(self, html_content):
        """QueuePanel checks for 'paused' drainState."""
        assert "const isPaused = drainState === 'paused';" in html_content

    def test_queuepanel_checks_countdown_state(self, html_content):
        """QueuePanel checks for 'countdown' drainState."""
        assert "const isCountdown = drainState === 'countdown';" in html_content

    def test_queuepanel_renders_queue_panel_div(self, html_content):
        """QueuePanel renders a div with class queue-panel."""
        assert 'class="queue-panel"' in html_content

    def test_queuepanel_renders_queued_messages_header(self, html_content):
        """QueuePanel renders 'Queued messages' header."""
        assert "Queued messages (" in html_content

    def test_queuepanel_renders_remove_button(self, html_content):
        """QueuePanel renders remove button with aria-label."""
        assert 'aria-label="Remove queued message"' in html_content

    def test_queuepanel_renders_countdown_label(self, html_content):
        """QueuePanel renders countdown label when in countdown state."""
        assert "queue-item-countdown-label" in html_content
        assert "Sending in " in html_content

    def test_queuepanel_renders_resume_button_when_paused(self, html_content):
        """QueuePanel renders Resume button when paused."""
        assert "Resume queue (" in html_content

    def test_queuepanel_defined_before_inputarea(self, html_content):
        """QueuePanel component is defined before InputArea component."""
        qp_pos = html_content.find("function QueuePanel({")
        ia_pos = html_content.find("function InputArea({")
        assert qp_pos != -1
        assert ia_pos != -1
        assert qp_pos < ia_pos

    def test_queuepanel_uses_queue_item_remove_class(self, html_content):
        """QueuePanel remove button uses queue-item-remove CSS class."""
        assert 'class="queue-item-remove"' in html_content

    def test_queuepanel_item_has_image_indicator(self, html_content):
        """QueuePanel shows [image] indicator for messages with images."""
        assert "queue-item-image" in html_content
        assert "[image]" in html_content


class TestTask9QueuePanelWiredIntoLayout:
    def test_queuepanel_rendered_in_chatapp(self, html_content):
        """QueuePanel component is rendered in ChatApp."""
        assert "<${QueuePanel}" in html_content

    def test_queuepanel_receives_queue_prop(self, html_content):
        """ChatApp passes queue prop to QueuePanel."""
        assert "queue=${getQueue()}" in html_content

    def test_queuepanel_receives_drainstate_prop(self, html_content):
        """ChatApp passes drainState prop to QueuePanel."""
        assert "drainState=${getQueueDrainState()}" in html_content

    def test_queuepanel_receives_countdownsecs_prop(self, html_content):
        """ChatApp passes countdownSecs prop to QueuePanel."""
        assert "countdownSecs=${countdownRemaining}" in html_content

    def test_queuepanel_receives_onremove_prop(self, html_content):
        """ChatApp passes onRemove handler to QueuePanel."""
        assert "onRemove=${(msgId) => {" in html_content

    def test_queuepanel_receives_onresume_prop(self, html_content):
        """ChatApp passes onResume handler to QueuePanel."""
        assert "onResume=${() => {" in html_content

    def test_queuepanel_onremove_handles_countdown_item(self, html_content):
        """onRemove handler clears countdown timer when removing first item in countdown state."""
        assert "countdownTimerRef.current" in html_content
        assert "clearTimeout(countdownTimerRef.current)" in html_content

    def test_queuepanel_onremove_sets_idle(self, html_content):
        """onRemove handler sets drain state to idle when removing countdown item."""
        assert "setQueueDrainStateFn('idle')" in html_content

    def test_queuepanel_between_messagelist_and_inputarea(self, html_content):
        """QueuePanel is positioned between MessageList and InputArea in the layout."""
        qp_pos = html_content.find("<${QueuePanel}")
        ml_pos = html_content.find("<${MessageList}")
        ia_pos = html_content.find("<${InputArea}")
        assert ml_pos != -1
        assert qp_pos != -1
        assert ia_pos != -1
        # QueuePanel comes after first MessageList but before InputArea
        assert ml_pos < qp_pos < ia_pos

    def test_queuepanel_onresume_sets_idle(self, html_content):
        """onResume handler sets drain state to idle."""
        # The onResume handler should contain setQueueDrainStateFn('idle')
        # which is already tested above, but let's check context
        assert "onResume=${() => {" in html_content
        assert "setQueueDrainStateFn('idle')" in html_content
