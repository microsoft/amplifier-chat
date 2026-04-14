"""
Tests for getArgPreview fix: recipes tool should show 'operation' not [object Object].

Bug: recipes tool calls showed '[object Object]' because getArgPreview had no entry
for 'recipes' in its field map, and the fallback String(firstVal) produces
'[object Object]' when firstVal is an object (like the `context` argument).

Fix:
  1. Add `recipes: 'operation'` to the field map so the operation name is used.
  2. Improve the fallback to JSON.stringify objects so any unknown tool with an
     object-valued first arg gets a readable preview.
"""

import pathlib

ROOT = pathlib.Path(__file__).parent.parent
INDEX_HTML = ROOT / "src" / "chat_plugin" / "static" / "index.html"


def html():
    return INDEX_HTML.read_text()


class TestGetArgPreviewRecipes:
    def test_recipes_operation_in_field_map(self):
        """getArgPreview must map 'recipes' tool to the 'operation' field."""
        content = html()
        assert "recipes: 'operation'" in content, (
            "getArgPreview field map must include `recipes: 'operation'` "
            "so that recipes tool calls show the operation name (e.g. 'execute') "
            "instead of '[object Object]'"
        )

    def test_fallback_handles_object_values(self):
        """getArgPreview fallback must JSON.stringify objects, not call String()."""
        content = html()
        # The improved fallback should detect object type and use JSON.stringify
        assert (
            "typeof firstVal === 'object'" in content and "JSON.stringify" in content
        ), (
            "getArgPreview fallback must use JSON.stringify for object values "
            "to avoid '[object Object]' for any unknown tool whose first arg is an object"
        )
