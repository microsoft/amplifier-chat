"""
Tests for S-07: Replace thinking_delta reverse-find with cached lookup.

Bug: The thinking_delta and thinking_final sub-session handlers use
.slice().reverse().find() to locate the active thinking item — O(n) per
delta event, creating quadratic overhead during long thinking streams.

Fix: Cache the active thinking item as sub._activeThinkingItem when it's
created in content_start, use it directly in thinking_delta/thinking_final,
and clear it in thinking_final. Fall back to findLast for robustness.
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


class TestThinkingDeltaCachedLookup:
    def test_active_thinking_item_cached_in_content_start(self):
        """content_start must set sub._activeThinkingItem for thinking blocks."""
        content = html()
        assert (
            "sub._activeThinkingItem = thinkingItem" in content
            or "_activeThinkingItem = thinkingItem" in content
        ), "_activeThinkingItem cache assignment not found in content_start"

    def test_thinking_delta_uses_cached_item(self):
        """thinking_delta must use sub._activeThinkingItem for O(1) lookup."""
        content = html()
        # Find thinking_delta case
        delta_start = content.find("case 'thinking_delta':")
        assert delta_start != -1, "thinking_delta case not found"
        delta_end = content.find("case '", delta_start + 25)
        delta_body = content[delta_start:delta_end]
        assert "_activeThinkingItem" in delta_body, (
            "_activeThinkingItem not used in thinking_delta handler"
        )

    def test_thinking_final_uses_cached_item(self):
        """thinking_final must use sub._activeThinkingItem for O(1) lookup."""
        content = html()
        final_start = content.find("case 'thinking_final':")
        assert final_start != -1, "thinking_final case not found"
        final_end = content.find("case '", final_start + 25)
        final_body = content[final_start:final_end]
        assert "_activeThinkingItem" in final_body, (
            "_activeThinkingItem not used in thinking_final handler"
        )

    def test_no_slice_reverse_find_in_thinking_handlers(self):
        """The old .slice().reverse().find() pattern must not appear in
        thinking_delta or thinking_final sub-session paths."""
        content = html()
        delta_start = content.find("case 'thinking_delta':")
        delta_end = content.find("case '", delta_start + 25)
        delta_body = content[delta_start:delta_end]

        final_start = content.find("case 'thinking_final':")
        final_end = content.find("case '", final_start + 25)
        final_body = content[final_start:final_end]

        assert ".slice().reverse().find(" not in delta_body, (
            "thinking_delta still uses .slice().reverse().find()"
        )
        assert ".slice().reverse().find(" not in final_body, (
            "thinking_final still uses .slice().reverse().find()"
        )

    def test_thinking_final_clears_cache(self):
        """thinking_final must clear _activeThinkingItem after use."""
        content = html()
        final_start = content.find("case 'thinking_final':")
        final_end = content.find("case '", final_start + 25)
        final_body = content[final_start:final_end]
        assert "_activeThinkingItem = null" in final_body, (
            "_activeThinkingItem not cleared in thinking_final"
        )
