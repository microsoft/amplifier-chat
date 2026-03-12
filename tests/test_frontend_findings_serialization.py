"""Tests for Task 6: Frontend — Include Findings in GitHub Issue.

Verifies that feedback-widget.js contains:
- serializeFindings(allFindings, checkedMap) function in the helpers section
- doSubmit appends serializeFindings output to the issue body
- doSubmit calls cancelAnalysis() before navigating away
- The stale comment on findingChecked has been updated
"""

from __future__ import annotations

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "src" / "chat_plugin" / "static"
WIDGET_JS = STATIC / "feedback-widget.js"


def _read() -> str:
    return WIDGET_JS.read_text(encoding="utf-8")


# ===========================================================================
# serializeFindings — function existence and placement
# ===========================================================================


class TestSerializeFindingsExists:
    """serializeFindings must be defined in the helpers section."""

    def test_function_exists(self):
        src = _read()
        assert "function serializeFindings" in src

    def test_defined_in_helpers_before_openModal(self):
        """serializeFindings must be defined before openModal (in helpers section)."""
        src = _read()
        fn_pos = src.find("function serializeFindings")
        modal_pos = src.find("function openModal")
        assert fn_pos != -1, "serializeFindings not found"
        assert modal_pos != -1, "openModal not found"
        assert fn_pos < modal_pos

    def test_defined_after_buildIssueBody(self):
        """serializeFindings must come after buildIssueBody."""
        src = _read()
        build_pos = src.find("function buildIssueBody")
        serialize_pos = src.find("function serializeFindings")
        assert build_pos != -1
        assert serialize_pos != -1
        assert serialize_pos > build_pos


# ===========================================================================
# serializeFindings — heading and empty-state
# ===========================================================================


class TestSerializeFindingsHeading:
    """serializeFindings must produce the ## Automated Findings heading."""

    def test_automated_findings_header(self):
        src = _read()
        fn_start = src.find("function serializeFindings")
        assert fn_start != -1
        fn_region = src[fn_start : fn_start + 2000]
        assert "## Automated Findings" in fn_region

    def test_returns_empty_string_when_no_checked(self):
        """Returns '' (empty string) when there are no checked findings."""
        src = _read()
        fn_start = src.find("function serializeFindings")
        assert fn_start != -1
        fn_region = src[fn_start : fn_start + 2000]
        # Should have an early return of '' when no checked items
        assert "return ''" in fn_region or 'return ""' in fn_region


# ===========================================================================
# serializeFindings — source grouping
# ===========================================================================


class TestSerializeFindingsGrouping:
    """serializeFindings must produce proper markdown group headers by source."""

    def test_github_group_header(self):
        """github source → '### Related Issues'."""
        src = _read()
        fn_start = src.find("function serializeFindings")
        assert fn_start != -1
        fn_region = src[fn_start : fn_start + 2000]
        assert "### Related Issues" in fn_region

    def test_session_group_header(self):
        """session source → '### Session Errors'."""
        src = _read()
        fn_start = src.find("function serializeFindings")
        assert fn_start != -1
        fn_region = src[fn_start : fn_start + 2000]
        assert "### Session Errors" in fn_region

    def test_server_log_group_header(self):
        """server_log source → '### Server Logs'."""
        src = _read()
        fn_start = src.find("function serializeFindings")
        assert fn_start != -1
        fn_region = src[fn_start : fn_start + 2000]
        assert "### Server Logs" in fn_region

    def test_groups_in_order_github_session_server_log(self):
        """Groups must be defined in order: github, session, server_log."""
        src = _read()
        fn_start = src.find("function serializeFindings")
        assert fn_start != -1
        fn_region = src[fn_start : fn_start + 2000]
        github_pos = fn_region.find("github")
        session_pos = fn_region.find("session")
        server_log_pos = fn_region.find("server_log")
        assert github_pos != -1 and session_pos != -1 and server_log_pos != -1
        assert github_pos < session_pos < server_log_pos

    def test_skips_empty_groups(self):
        """Empty groups are skipped — must check group length before adding header."""
        src = _read()
        fn_start = src.find("function serializeFindings")
        assert fn_start != -1
        fn_region = src[fn_start : fn_start + 2000]
        # There must be a length check before appending group content
        assert re.search(r"\.length", fn_region)


# ===========================================================================
# serializeFindings — checked filtering
# ===========================================================================


class TestSerializeFindingsCheckedFilter:
    """serializeFindings must filter by checkedMap."""

    def test_references_checkedMap_param(self):
        """Must use checkedMap to filter findings."""
        src = _read()
        fn_start = src.find("function serializeFindings")
        assert fn_start != -1
        fn_region = src[fn_start : fn_start + 2000]
        assert "checkedMap" in fn_region

    def test_filters_out_false_entries(self):
        """Must exclude entries where checkedMap[i] === false."""
        src = _read()
        fn_start = src.find("function serializeFindings")
        assert fn_start != -1
        fn_region = src[fn_start : fn_start + 2000]
        # Should check !== false or equivalent
        assert "!== false" in fn_region or "=== false" in fn_region


# ===========================================================================
# serializeFindings — github finding format
# ===========================================================================


class TestSerializeFindingsGithubFormat:
    """GitHub findings must render as markdown links with optional status + relevance."""

    def test_github_renders_markdown_link(self):
        """GitHub findings use [summary](url) markdown link format."""
        src = _read()
        fn_start = src.find("function serializeFindings")
        assert fn_start != -1
        fn_region = src[fn_start : fn_start + 2500]
        # Should have something like '- [' for a markdown list link
        assert "- [" in fn_region or "'- [')" in fn_region or '"- ["' in fn_region

    def test_github_includes_url_field(self):
        """GitHub findings reference the .url field."""
        src = _read()
        fn_start = src.find("function serializeFindings")
        assert fn_start != -1
        fn_region = src[fn_start : fn_start + 2500]
        assert ".url" in fn_region

    def test_github_blockquote_for_relevance(self):
        """GitHub findings with relevance use blockquote (> ...) format."""
        src = _read()
        fn_start = src.find("function serializeFindings")
        assert fn_start != -1
        fn_region = src[fn_start : fn_start + 2500]
        assert "relevance" in fn_region
        # Blockquote character
        assert (
            "'> '" in fn_region
            or '"> "' in fn_region
            or "blockquote" in fn_region
            or "> " in fn_region
        )


# ===========================================================================
# serializeFindings — session finding format
# ===========================================================================


class TestSerializeFindingsSessionFormat:
    """Session findings must render with bold summary, error type/message, traceback."""

    def test_session_bold_summary(self):
        """Session findings use **summary** bold format."""
        src = _read()
        fn_start = src.find("function serializeFindings")
        assert fn_start != -1
        fn_region = src[fn_start : fn_start + 3000]
        assert "**" in fn_region

    def test_session_error_type_in_backticks(self):
        """Session error.type is rendered in backticks."""
        src = _read()
        fn_start = src.find("function serializeFindings")
        assert fn_start != -1
        fn_region = src[fn_start : fn_start + 3000]
        assert "error.type" in fn_region
        # Backtick usage
        assert "`" in fn_region

    def test_session_traceback_code_fence(self):
        """Session traceback frames use triple-backtick code fences."""
        src = _read()
        fn_start = src.find("function serializeFindings")
        assert fn_start != -1
        fn_region = src[fn_start : fn_start + 3000]
        assert "traceback" in fn_region
        assert "```" in fn_region


# ===========================================================================
# serializeFindings — server_log finding format
# ===========================================================================


class TestSerializeFindingsServerLogFormat:
    """Server log findings must render with bold summary and code fence for log lines."""

    def test_server_log_context_lines_or_log_line(self):
        """server_log findings render context_lines or log_line in code fences."""
        src = _read()
        fn_start = src.find("function serializeFindings")
        assert fn_start != -1
        fn_region = src[fn_start : fn_start + 3000]
        assert "context_lines" in fn_region or "log_line" in fn_region

    def test_server_log_uses_code_fence(self):
        """server_log findings use triple-backtick code fences."""
        src = _read()
        fn_start = src.find("function serializeFindings")
        assert fn_start != -1
        fn_region = src[fn_start : fn_start + 3000]
        assert "```" in fn_region


# ===========================================================================
# doSubmit — calls serializeFindings
# ===========================================================================


class TestDoSubmitCallsSerializeFindings:
    """doSubmit must append serializeFindings output to the issue body."""

    def test_doSubmit_calls_serializeFindings(self):
        """doSubmit must call serializeFindings."""
        src = _read()
        fn_start = src.find("function doSubmit")
        assert fn_start != -1
        fn_region = src[fn_start : fn_start + 1000]
        assert "serializeFindings" in fn_region

    def test_doSubmit_appends_to_body(self):
        """doSubmit must append serializeFindings result to the body string."""
        src = _read()
        fn_start = src.find("function doSubmit")
        assert fn_start != -1
        fn_region = src[fn_start : fn_start + 1000]
        # Body must be augmented (+=, concatenation, or body = body + ...)
        assert re.search(r"body\s*\+=|body\s*=\s*body\s*\+", fn_region)

    def test_doSubmit_only_appends_if_findings_exist(self):
        """doSubmit only appends findings when findings.length > 0."""
        src = _read()
        fn_start = src.find("function doSubmit")
        assert fn_start != -1
        fn_region = src[fn_start : fn_start + 1000]
        assert "findings.length" in fn_region


# ===========================================================================
# doSubmit — cancels analysis before navigating
# ===========================================================================


class TestDoSubmitCancelsAnalysis:
    """doSubmit must cancel ongoing analysis before navigating to GitHub."""

    def test_doSubmit_calls_cancelAnalysis(self):
        """doSubmit must call cancelAnalysis() before window.open."""
        src = _read()
        fn_start = src.find("function doSubmit")
        assert fn_start != -1
        fn_region = src[fn_start : fn_start + 1000]
        assert "cancelAnalysis" in fn_region

    def test_doSubmit_cancelAnalysis_before_window_open(self):
        """cancelAnalysis must appear before window.open in doSubmit."""
        src = _read()
        fn_start = src.find("function doSubmit")
        assert fn_start != -1
        fn_region = src[fn_start : fn_start + 1000]
        cancel_pos = fn_region.find("cancelAnalysis")
        open_pos = fn_region.find("window.open")
        assert cancel_pos != -1, "cancelAnalysis not found in doSubmit"
        assert open_pos != -1, "window.open not found in doSubmit"
        assert cancel_pos < open_pos

    def test_doSubmit_guards_cancel_with_analysisComplete(self):
        """doSubmit only calls cancelAnalysis if !analysisComplete."""
        src = _read()
        fn_start = src.find("function doSubmit")
        assert fn_start != -1
        fn_region = src[fn_start : fn_start + 1000]
        assert "analysisComplete" in fn_region


# ===========================================================================
# Stale comment fix
# ===========================================================================


class TestStaleCommentFixed:
    """The stale 'next task' comment on findingChecked must be replaced."""

    def test_stale_comment_removed(self):
        """Old 'Used by renderFindings (next task)' comment must not exist."""
        src = _read()
        assert "Used by renderFindings (next task)" not in src

    def test_updated_comment_present(self):
        """findingChecked declaration must have the updated descriptive comment."""
        src = _read()
        assert "Tracks per-finding checkbox state by index" in src
