"""
Tests for S-05: Defensive cancelCountdown call at top of resumeHistorySession.

Bug: resumeHistorySession can be called while a countdown is active on the
current session. Without an explicit cancelCountdown call, the countdown
timer continues running even after switching to a history session, causing
phantom UI updates.

Fix: Add cancelCountdown(activeKeyRef.current) as the first statement inside
resumeHistorySession, before any early-return guards.
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


class TestResumeCancelCountdown:
    def test_cancel_countdown_call_exists_in_resume_history_session(self):
        """cancelCountdown(activeKeyRef.current) must appear inside resumeHistorySession."""
        content = html()
        resume_start = content.find(
            "const resumeHistorySession = useCallback((key) => {"
        )
        assert resume_start != -1, "resumeHistorySession not found"
        # Find the end of the function (next top-level useCallback)
        resume_end = content.find("}, []);", resume_start)
        assert resume_end != -1, "End of resumeHistorySession not found"
        resume_body = content[resume_start:resume_end]
        assert "cancelCountdown(activeKeyRef.current)" in resume_body, (
            "cancelCountdown(activeKeyRef.current) not found in resumeHistorySession body"
        )

    def test_cancel_countdown_is_near_top_of_resume_history_session(self):
        """cancelCountdown call must appear before the early-return target check."""
        content = html()
        resume_start = content.find(
            "const resumeHistorySession = useCallback((key) => {"
        )
        assert resume_start != -1, "resumeHistorySession not found"
        cancel_pos = content.find("cancelCountdown(activeKeyRef.current)", resume_start)
        assert cancel_pos != -1, (
            "cancelCountdown(activeKeyRef.current) not found after resumeHistorySession"
        )
        early_return_pos = content.find(
            "if (!target || !target.sessionId) return;", resume_start
        )
        assert early_return_pos != -1, (
            "early-return guard not found in resumeHistorySession"
        )
        assert cancel_pos < early_return_pos, (
            "cancelCountdown must appear BEFORE the early-return guard in resumeHistorySession"
        )

    def test_cancel_countdown_has_explanatory_comment(self):
        """A comment explaining the call-site contract should accompany cancelCountdown."""
        content = html()
        resume_start = content.find(
            "const resumeHistorySession = useCallback((key) => {"
        )
        assert resume_start != -1, "resumeHistorySession not found"
        resume_end = content.find("}, []);", resume_start)
        resume_body = content[resume_start:resume_end]
        # Allow any comment near the cancelCountdown call
        has_comment = (
            "// Cancel" in resume_body
            or "// cancel" in resume_body
            or "// Clear" in resume_body
            or "// clear" in resume_body
            or "// Stop" in resume_body
            or "call-site" in resume_body
        )
        assert has_comment, (
            "No explanatory comment found near cancelCountdown in resumeHistorySession"
        )
