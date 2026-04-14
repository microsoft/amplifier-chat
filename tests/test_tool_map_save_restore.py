"""
Tests for S-06: Save/restore toolMapRef in switchSession alongside blockMapRef.

Bug: When switching sessions (A->B->A), blockMapRef is saved/restored but
toolMapRef is NOT. After switching back, tool_result events can't find their
parent tool call items because toolMapRef is empty.

Fix: Add `savedToolMap: { ...toolMapRef.current }` to the save object and
`toolMapRef.current = target.savedToolMap || {}` to the restore block in
switchSession, mirroring what is already done for blockMapRef/savedBlockMap.
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


class TestToolMapSaveInSwitchSession:
    def test_saved_tool_map_key_in_save_block(self):
        """savedToolMap must appear in the switchSession save object."""
        assert "savedToolMap" in html(), "savedToolMap not found anywhere in index.html"

    def test_saved_tool_map_saved_near_saved_block_map(self):
        """savedToolMap save line must be close to savedBlockMap save line (within 200 chars)."""
        content = html()
        block_map_pos = content.find("savedBlockMap: { ...blockMapRef.current }")
        tool_map_pos = content.find("savedToolMap: { ...toolMapRef.current }")
        assert block_map_pos != -1, "savedBlockMap save line not found"
        assert tool_map_pos != -1, "savedToolMap save line not found"
        assert abs(tool_map_pos - block_map_pos) < 200, (
            f"savedToolMap save ({tool_map_pos}) not near savedBlockMap save ({block_map_pos})"
        )

    def test_saved_tool_map_restore_line_present(self):
        """toolMapRef.current must be restored from target.savedToolMap in switchSession."""
        assert "toolMapRef.current = target.savedToolMap || {};" in html(), (
            "toolMapRef.current restore line not found in index.html"
        )

    def test_saved_tool_map_restored_near_block_map_restore(self):
        """toolMapRef restore must be close to blockMapRef restore line (within 200 chars)."""
        content = html()
        block_restore_pos = content.find(
            "blockMapRef.current = target.savedBlockMap || {};"
        )
        tool_restore_pos = content.find(
            "toolMapRef.current = target.savedToolMap || {};"
        )
        assert block_restore_pos != -1, "blockMapRef restore line not found"
        assert tool_restore_pos != -1, "toolMapRef restore line not found"
        assert abs(tool_restore_pos - block_restore_pos) < 200, (
            f"toolMapRef restore ({tool_restore_pos}) not near blockMapRef restore ({block_restore_pos})"
        )
