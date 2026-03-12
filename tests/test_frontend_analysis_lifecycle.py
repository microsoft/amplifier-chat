"""Tests for Task 4: Frontend Analysis Lifecycle.

Verifies that index.html passes sessionIdRef to the feedback widget,
and that feedback-widget.js contains the analysis lifecycle wiring:
CSS classes, extractFindings, SSE subscription, cancel-on-close, etc.
"""

from __future__ import annotations

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "src" / "chat_plugin" / "static"
INDEX_HTML = STATIC / "index.html"
WIDGET_JS = STATIC / "feedback-widget.js"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ===========================================================================
# index.html — sessionIdRef plumbing
# ===========================================================================


class TestIndexSessionIdRef:
    """index.html must declare sessionIdRef and pass it to the widget."""

    def test_sessionIdRef_declared(self):
        src = _read(INDEX_HTML)
        assert "const sessionIdRef = useRef(null);" in src

    def test_sessionIdRef_sync_effect(self):
        """A useEffect syncs sessionId state into sessionIdRef."""
        src = _read(INDEX_HTML)
        assert "sessionIdRef.current = sessionId;" in src
        # Must be in a useEffect with [sessionId] dependency
        assert re.search(
            r"useEffect\(\(\)\s*=>\s*\{\s*sessionIdRef\.current\s*=\s*sessionId;\s*\},\s*\[sessionId\]\)",
            src,
        )

    def test_getSessionId_callback_passed(self):
        """Widget init receives a getSessionId callback returning sessionIdRef.current."""
        src = _read(INDEX_HTML)
        assert "getSessionId" in src
        assert "sessionIdRef.current" in src
        # The init call should contain the getSessionId option
        assert re.search(
            r"getSessionId\s*:\s*function\s*\(\)\s*\{\s*return\s+sessionIdRef\.current;\s*\}",
            src,
        )


# ===========================================================================
# feedback-widget.js — CSS classes
# ===========================================================================


class TestWidgetAnalysisCSS:
    """All analysis CSS classes must be defined in the widget stylesheet."""

    REQUIRED_CLASSES = [
        ".amp-fb-analysis",
        ".amp-fb-analysis-loading",
        ".amp-fb-spinner",
        ".amp-fb-analysis-cancel",
        ".amp-fb-analysis-error",
        ".amp-fb-findings-group",
        ".amp-fb-findings-group-header",
        ".amp-fb-finding",
        ".amp-fb-finding-content",
        ".amp-fb-finding-summary",
        ".amp-fb-finding-detail",
        ".amp-fb-finding-link",
        ".amp-fb-finding-status",
    ]

    def test_all_css_classes_present(self):
        src = _read(WIDGET_JS)
        for cls in self.REQUIRED_CLASSES:
            assert cls in src, f"Missing CSS class: {cls}"

    def test_spinner_keyframes(self):
        src = _read(WIDGET_JS)
        assert "@keyframes amp-fb-spin" in src

    def test_finding_checkbox_style(self):
        src = _read(WIDGET_JS)
        assert ".amp-fb-finding input[type=checkbox]" in src

    def test_finding_detail_pre_style(self):
        src = _read(WIDGET_JS)
        assert ".amp-fb-finding-detail pre" in src

    def test_finding_status_variants(self):
        src = _read(WIDGET_JS)
        # .open and .closed variants
        assert re.search(r"\.amp-fb-finding-status\.open", src)
        assert re.search(r"\.amp-fb-finding-status\.closed", src)

    def test_css_before_reduced_motion(self):
        """Analysis CSS must appear before the reduced-motion media query."""
        src = _read(WIDGET_JS)
        spinner_pos = src.find(".amp-fb-spinner")
        reduced_motion_pos = src.find("prefers-reduced-motion")
        assert spinner_pos != -1 and reduced_motion_pos != -1
        assert spinner_pos < reduced_motion_pos


# ===========================================================================
# feedback-widget.js — extractFindings function
# ===========================================================================


class TestExtractFindings:
    """extractFindings must be defined after buildIssueBody."""

    def test_function_exists(self):
        src = _read(WIDGET_JS)
        assert "function extractFindings" in src

    def test_strips_code_fences(self):
        """Must handle markdown code fences."""
        src = _read(WIDGET_JS)
        # Should reference code fence stripping (```json ... ```)
        assert "```" in src or "replace" in src

    def test_json_parse(self):
        """Must use JSON.parse."""
        src = _read(WIDGET_JS)
        # extractFindings should use JSON.parse on some substring
        fn_start = src.find("function extractFindings")
        assert fn_start != -1
        fn_region = src[fn_start : fn_start + 600]
        assert "JSON.parse" in fn_region

    def test_returns_empty_on_failure(self):
        """Returns [] on parse failure."""
        src = _read(WIDGET_JS)
        fn_start = src.find("function extractFindings")
        fn_region = src[fn_start : fn_start + 2000]
        assert "[]" in fn_region

    def test_defined_after_buildIssueBody(self):
        src = _read(WIDGET_JS)
        build_pos = src.find("function buildIssueBody")
        extract_pos = src.find("function extractFindings")
        assert build_pos != -1 and extract_pos != -1
        assert extract_pos > build_pos


# ===========================================================================
# feedback-widget.js — Analysis lifecycle in openModal
# ===========================================================================


class TestAnalysisLifecycle:
    """openModal must wire up analysis start, SSE subscription, and cancel."""

    def test_startAnalysis_function(self):
        src = _read(WIDGET_JS)
        assert "function startAnalysis" in src

    def test_startAnalysis_posts_to_analyze(self):
        """startAnalysis calls POST to the feedback/analyze endpoint."""
        src = _read(WIDGET_JS)
        # apiBase is constructed as origin + '/chat/api', then fetch uses apiBase + '/feedback/analyze'
        assert "/feedback/analyze" in src

    def test_subscribeToSSE_function(self):
        src = _read(WIDGET_JS)
        assert "function subscribeToSSE" in src

    def test_sse_uses_eventsource(self):
        src = _read(WIDGET_JS)
        assert "EventSource" in src

    def test_sse_listens_for_content_block_delta(self):
        src = _read(WIDGET_JS)
        assert "content_block:delta" in src

    def test_sse_listens_for_completion_events(self):
        src = _read(WIDGET_JS)
        assert "orchestrator:complete" in src
        assert "execution:end" in src

    def test_cancelAnalysis_function(self):
        src = _read(WIDGET_JS)
        assert "function cancelAnalysis" in src

    def test_cancelAnalysis_posts_cancel(self):
        """cancelAnalysis POSTs /sessions/{id}/cancel with {immediate: true}."""
        src = _read(WIDGET_JS)
        assert "/cancel" in src
        assert "immediate" in src

    def test_closeModal_calls_cancelAnalysis(self):
        """cancelAnalysis() must be the first line in closeModal."""
        src = _read(WIDGET_JS)
        match = re.search(
            r"function closeModal\(\)\s*\{[^}]*cancelAnalysis\(\)", src, re.DOTALL
        )
        assert match, "closeModal must call cancelAnalysis()"

    def test_openModal_calls_startAnalysis(self):
        """startAnalysis() is called after titleInput.focus() in the openModal body."""
        src = _read(WIDGET_JS)
        focus_pos = src.find("titleInput.focus()")
        # Find the startAnalysis() *call* that appears after focus, not the definition
        start_call_pos = src.find("startAnalysis();", focus_pos)
        assert focus_pos != -1 and start_call_pos != -1
        assert start_call_pos > focus_pos

    def test_updateAnalysisUI_function(self):
        src = _read(WIDGET_JS)
        assert "function updateAnalysisUI" in src

    def test_analysisSection_in_modal(self):
        """analysisSection div is created and added to modal."""
        src = _read(WIDGET_JS)
        assert "analysisSection" in src

    def test_renderFindings_exists(self):
        """renderFindings function must exist in the modal scope."""
        src = _read(WIDGET_JS)
        assert "function renderFindings" in src

    def test_onComplete_guards_against_double_fire(self):
        """onComplete must early-return if already complete to prevent double processing."""
        src = _read(WIDGET_JS)
        # Find the onComplete function body
        fn_start = src.find("function onComplete()")
        assert fn_start != -1, "onComplete function must exist"
        fn_region = src[fn_start : fn_start + 300]
        # Must contain an early-return guard checking analysisComplete
        assert re.search(r"if\s*\(\s*analysisComplete\s*\)\s*return;", fn_region), (
            "onComplete must guard against double-fire with 'if (analysisComplete) return;'"
        )
