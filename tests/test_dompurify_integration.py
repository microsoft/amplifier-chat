"""
Tests for S-26: DOMPurify integration.

Replace the hand-rolled sanitizeHtml with DOMPurify.sanitize for
production-quality XSS protection.

Deliverables:
  - scripts/build-vendor.sh  — vendor rebuild script
  - scripts/vendor-entry.js  — esbuild entry point with DOMPurify import
  - index.html               — sanitizeHtml uses DOMPurify when available
  - AGENTS.md                — documents the vendor build process
"""

import pathlib
import stat

ROOT = pathlib.Path(__file__).parent.parent
INDEX_HTML = ROOT / "src" / "chat_plugin" / "static" / "index.html"


def html():
    return INDEX_HTML.read_text()


class TestBuildInfrastructure:
    def test_build_vendor_sh_exists(self):
        """scripts/build-vendor.sh must exist."""
        assert (ROOT / "scripts" / "build-vendor.sh").is_file()

    def test_build_vendor_sh_executable(self):
        """scripts/build-vendor.sh must be executable."""
        path = ROOT / "scripts" / "build-vendor.sh"
        assert path.stat().st_mode & stat.S_IXUSR, (
            "build-vendor.sh must have executable permission"
        )

    def test_build_vendor_sh_installs_dompurify(self):
        """build-vendor.sh must install dompurify."""
        content = (ROOT / "scripts" / "build-vendor.sh").read_text()
        assert "dompurify" in content.lower(), "build-vendor.sh must install dompurify"

    def test_vendor_entry_js_exists(self):
        """scripts/vendor-entry.js must exist."""
        assert (ROOT / "scripts" / "vendor-entry.js").is_file()

    def test_vendor_entry_imports_dompurify(self):
        """vendor-entry.js must import DOMPurify."""
        content = (ROOT / "scripts" / "vendor-entry.js").read_text()
        assert "dompurify" in content.lower(), "vendor-entry.js must import DOMPurify"

    def test_vendor_entry_exports_dompurify(self):
        """vendor-entry.js must export DOMPurify to window."""
        content = (ROOT / "scripts" / "vendor-entry.js").read_text()
        assert "window.DOMPurify" in content, (
            "vendor-entry.js must set window.DOMPurify"
        )


class TestSanitizeHtmlReplacement:
    def test_sanitize_html_uses_dompurify(self):
        """sanitizeHtml must use DOMPurify.sanitize when available."""
        content = html()
        assert "DOMPurify.sanitize" in content, (
            "DOMPurify.sanitize not found in index.html"
        )

    def test_no_todo_replace_comment(self):
        """The old TODO comment about replacing with DOMPurify must be gone."""
        content = html()
        assert "TODO: Replace with DOMPurify" not in content, (
            "Old TODO comment should be removed after DOMPurify integration"
        )

    def test_fallback_sanitizer_exists(self):
        """A fallback sanitizer must exist for when DOMPurify isn't loaded."""
        content = html()
        # The fallback should still remove dangerous tags
        assert "script,iframe,object,embed" in content, (
            "Fallback sanitizer must still strip dangerous tags"
        )


class TestAgentsMd:
    def test_agents_md_exists(self):
        """AGENTS.md must exist at project root."""
        assert (ROOT / "AGENTS.md").is_file()

    def test_agents_md_mentions_vendor_build(self):
        """AGENTS.md must document the vendor build process."""
        content = (ROOT / "AGENTS.md").read_text()
        assert "build-vendor" in content, "AGENTS.md must mention build-vendor script"

    def test_agents_md_mentions_dompurify(self):
        """AGENTS.md must mention DOMPurify."""
        content = (ROOT / "AGENTS.md").read_text()
        assert "DOMPurify" in content, "AGENTS.md must mention DOMPurify"
