"""Tests for Task 5: Frontend Findings Checklist UI.

Verifies that feedback-widget.js contains:
- escapeHtml() helper
- buildFindingDetail(f, source) helper
- Full renderFindings() implementation (grouped checklist, not placeholder)
"""

from __future__ import annotations

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "src" / "chat_plugin" / "static"
WIDGET_JS = STATIC / "feedback-widget.js"


def _read() -> str:
    return WIDGET_JS.read_text(encoding="utf-8")


# ===========================================================================
# escapeHtml
# ===========================================================================


class TestEscapeHtml:
    """escapeHtml must escape &, <, > for safe HTML insertion."""

    def test_function_exists(self):
        src = _read()
        assert "function escapeHtml" in src

    def test_escapes_ampersand(self):
        src = _read()
        fn_start = src.find("function escapeHtml")
        assert fn_start != -1
        fn_region = src[fn_start : fn_start + 400]
        assert "&amp;" in fn_region

    def test_escapes_less_than(self):
        src = _read()
        fn_start = src.find("function escapeHtml")
        fn_region = src[fn_start : fn_start + 400]
        assert "&lt;" in fn_region

    def test_escapes_greater_than(self):
        src = _read()
        fn_start = src.find("function escapeHtml")
        fn_region = src[fn_start : fn_start + 400]
        assert "&gt;" in fn_region


# ===========================================================================
# buildFindingDetail
# ===========================================================================


class TestBuildFindingDetail:
    """buildFindingDetail must handle github, session, and server_log sources."""

    def test_function_exists(self):
        src = _read()
        assert "function buildFindingDetail" in src

    def test_handles_github_relevance(self):
        """For github source, shows f.relevance if present."""
        src = _read()
        fn_start = src.find("function buildFindingDetail")
        assert fn_start != -1
        fn_region = src[fn_start : fn_start + 800]
        assert "relevance" in fn_region

    def test_handles_session_source(self):
        """For session source, shows event_type, turn number, error fields."""
        src = _read()
        fn_start = src.find("function buildFindingDetail")
        fn_region = src[fn_start : fn_start + 800]
        assert "event_type" in fn_region
        assert "error" in fn_region

    def test_handles_server_log_source(self):
        """For server_log source, shows log_level and context_lines or log_line."""
        src = _read()
        fn_start = src.find("function buildFindingDetail")
        fn_region = src[fn_start : fn_start + 1500]
        assert "log_level" in fn_region
        assert "context_lines" in fn_region or "log_line" in fn_region

    def test_uses_pre_block_for_traceback(self):
        """Session tracebacks are rendered in <pre> blocks."""
        src = _read()
        fn_start = src.find("function buildFindingDetail")
        fn_region = src[fn_start : fn_start + 1500]
        assert "traceback" in fn_region
        assert "<pre>" in fn_region or "'pre'" in fn_region or '"pre"' in fn_region

    def test_returns_null_for_no_content(self):
        """Returns null when there is no detail content (ternary or explicit return)."""
        src = _read()
        fn_start = src.find("function buildFindingDetail")
        fn_region = src[fn_start : fn_start + 1800]
        # Either an explicit "return null" or a ternary "... : null"
        assert "return null" in fn_region or ": null" in fn_region

    def test_defined_in_helpers_section(self):
        """buildFindingDetail is defined in the helpers section (before openModal)."""
        src = _read()
        fn_pos = src.find("function buildFindingDetail")
        modal_pos = src.find("function openModal")
        assert fn_pos != -1
        assert modal_pos != -1
        assert fn_pos < modal_pos


# ===========================================================================
# renderFindings — full implementation
# ===========================================================================


class TestRenderFindingsImplementation:
    """renderFindings must be a full implementation, not the placeholder."""

    def test_placeholder_removed(self):
        """The old placeholder text must be gone."""
        src = _read()
        assert "finding(s) ready" not in src

    def test_accepts_container_parameter(self):
        """renderFindingsInto must accept a container parameter (caller handles clearing)."""
        src = _read()
        fn_start = src.find("function renderFindingsInto")
        assert fn_start != -1
        fn_region = src[fn_start : fn_start + 50]
        assert "container" in fn_region

    def test_groups_by_source_github(self):
        """Must map 'github' source to 'Related Issues' group label."""
        src = _read()
        assert "Related Issues" in src

    def test_groups_by_source_session(self):
        """Must map 'session' source to 'Session Errors' group label."""
        src = _read()
        assert "Session Errors" in src

    def test_groups_by_source_server_log(self):
        """Must map 'server_log' source to 'Server Logs' group label."""
        src = _read()
        assert "Server Logs" in src

    def test_renders_group_header_class(self):
        """Group headers must use amp-fb-findings-group-header class."""
        src = _read()
        fn_start = src.find("function renderFindings")
        fn_region = src[fn_start : fn_start + 2000]
        assert "amp-fb-findings-group-header" in fn_region

    def test_renders_findings_group_class(self):
        """Groups must use amp-fb-findings-group class."""
        src = _read()
        fn_start = src.find("function renderFindings")
        fn_region = src[fn_start : fn_start + 2000]
        assert "amp-fb-findings-group" in fn_region

    def test_renders_checkbox_per_finding(self):
        """Each finding must have a checkbox input."""
        src = _read()
        fn_start = src.find("function renderFindings")
        fn_region = src[fn_start : fn_start + 2000]
        assert "checkbox" in fn_region

    def test_checkbox_uses_findingChecked(self):
        """Checkbox checked state uses findingChecked[idx]."""
        src = _read()
        fn_start = src.find("function renderFindings")
        fn_region = src[fn_start : fn_start + 2000]
        assert "findingChecked" in fn_region

    def test_checkbox_listener_updates_findingChecked(self):
        """Checkbox event listener updates findingChecked[idx]."""
        src = _read()
        fn_start = src.find("function renderFindings")
        fn_region = src[fn_start : fn_start + 2000]
        # Listener must assign back to findingChecked
        assert re.search(r"findingChecked\[", fn_region)

    def test_github_findings_have_link(self):
        """GitHub findings must render a link with amp-fb-finding-link class."""
        src = _read()
        fn_start = src.find("function renderFindings")
        fn_region = src[fn_start : fn_start + 2000]
        assert "amp-fb-finding-link" in fn_region

    def test_github_findings_have_status_badge(self):
        """GitHub findings must render a status badge with amp-fb-finding-status class."""
        src = _read()
        fn_start = src.find("function renderFindings")
        fn_region = src[fn_start : fn_start + 2000]
        assert "amp-fb-finding-status" in fn_region

    def test_uses_details_element_for_expandable(self):
        """Detail sections must use <details> + <summary> HTML elements."""
        src = _read()
        fn_start = src.find("function renderFindings")
        fn_region = src[fn_start : fn_start + 2000]
        assert "'details'" in fn_region or '"details"' in fn_region

    def test_uses_summary_element(self):
        """Detail sections must use <summary> element."""
        src = _read()
        fn_start = src.find("function renderFindings")
        fn_region = src[fn_start : fn_start + 2000]
        assert "'summary'" in fn_region or '"summary"' in fn_region

    def test_skips_empty_groups(self):
        """Empty groups must not be rendered."""
        src = _read()
        fn_start = src.find("function renderFindings")
        fn_region = src[fn_start : fn_start + 2000]
        # There must be a length check before appending a group
        assert re.search(r"\.length", fn_region)

    def test_renders_in_order_github_session_server_log(self):
        """Groups must be defined/iterated in order: github, session, server_log."""
        src = _read()
        fn_start = src.find("function renderFindings")
        fn_region = src[fn_start : fn_start + 2000]
        github_pos = fn_region.find("github")
        session_pos = fn_region.find("session")
        server_log_pos = fn_region.find("server_log")
        assert github_pos != -1 and session_pos != -1 and server_log_pos != -1
        assert github_pos < session_pos < server_log_pos

    def test_uses_el_helper(self):
        """renderFindings must use the el() DOM helper."""
        src = _read()
        fn_start = src.find("function renderFindings")
        fn_region = src[fn_start : fn_start + 2000]
        assert re.search(r"\bel\(", fn_region)

    def test_finding_content_class(self):
        """Finding rows must include amp-fb-finding-content wrapper."""
        src = _read()
        fn_start = src.find("function renderFindings")
        fn_region = src[fn_start : fn_start + 3500]
        assert "amp-fb-finding-content" in fn_region

    def test_finding_summary_class(self):
        """Finding summary must include amp-fb-finding-summary class."""
        src = _read()
        fn_start = src.find("function renderFindings")
        fn_region = src[fn_start : fn_start + 3500]
        assert "amp-fb-finding-summary" in fn_region

    def test_finding_detail_class(self):
        """Detail container must include amp-fb-finding-detail class."""
        src = _read()
        fn_start = src.find("function renderFindings")
        fn_region = src[fn_start : fn_start + 3500]
        assert "amp-fb-finding-detail" in fn_region

    def test_calls_buildFindingDetail(self):
        """renderFindings must call buildFindingDetail."""
        src = _read()
        fn_start = src.find("function renderFindings")
        fn_region = src[fn_start : fn_start + 2000]
        assert "buildFindingDetail" in fn_region

    def test_calls_escapeHtml(self):
        """renderFindings or buildFindingDetail must call escapeHtml."""
        src = _read()
        fn_start = src.find("function buildFindingDetail")
        fn_region = src[fn_start : fn_start + 1000]
        assert "escapeHtml" in fn_region
