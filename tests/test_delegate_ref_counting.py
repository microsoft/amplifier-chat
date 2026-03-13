"""
Tests for delegate ref-counting fix.

Bug: When the orchestrator spawns delegate sub-agents, their orchestrator:complete
events arrive on the parent session's SSE stream as prompt_complete. The client
can't distinguish sub-agent completions from the parent's real completion, so
setExecuting(false) fires prematurely, the queue starts draining, and the
prematurely-sent message gets rejected ("Session is already executing").

Fix: Track in-flight delegates with activeDelegatesRef. Only honor prompt_complete
(set executing to false + drain queue) when the delegate count is zero.

Event lifecycle:
  1. session_fork fires → activeDelegatesRef.current += 1
  2. sub-agent's prompt_complete arrives → counter > 0, SKIP setExecuting(false)
  3. tool_result for delegate arrives → activeDelegatesRef.current -= 1
  4. parent's prompt_complete arrives → counter === 0 → setExecuting(false) + drain
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


# ---------------------------------------------------------------------------
# Step 1 — activeDelegatesRef declaration
# ---------------------------------------------------------------------------


class TestActiveDelegatesRefDeclaration:
    def test_active_delegates_ref_declared(self):
        """activeDelegatesRef = useRef(0) must be declared."""
        assert "const activeDelegatesRef = useRef(0);" in html()

    def test_active_delegates_ref_near_executing_ref(self):
        """activeDelegatesRef must be declared near executingRef."""
        content = html()
        executing_ref = "const executingRef = useRef(false);"
        delegates_ref = "const activeDelegatesRef = useRef(0);"
        exec_pos = content.find(executing_ref)
        del_pos = content.find(delegates_ref)
        assert exec_pos != -1, "executingRef declaration not found"
        assert del_pos != -1, "activeDelegatesRef declaration not found"
        # Should be within ~300 chars of each other
        assert abs(exec_pos - del_pos) < 300, (
            f"activeDelegatesRef ({del_pos}) not near executingRef ({exec_pos})"
        )


# ---------------------------------------------------------------------------
# Step 2 — session_fork increments the counter
# ---------------------------------------------------------------------------


class TestSessionForkIncrement:
    def test_session_fork_increments_active_delegates(self):
        """session_fork case must increment activeDelegatesRef.current."""
        assert "activeDelegatesRef.current += 1;" in html()

    def test_session_fork_increment_inside_session_fork_case(self):
        """The increment must appear inside the session_fork case block."""
        content = html()
        fork_case = "case 'session_fork':"
        increment = "activeDelegatesRef.current += 1;"
        fork_pos = content.find(fork_case)
        assert fork_pos != -1, "session_fork case not found"
        # The increment must appear after the session_fork case
        inc_pos = content.find(increment, fork_pos)
        assert inc_pos != -1, (
            "activeDelegatesRef increment not found after session_fork"
        )
        # And it must appear before the next case statement (within ~1000 chars)
        next_case = content.find("case '", fork_pos + len(fork_case))
        assert inc_pos < next_case, (
            "activeDelegatesRef increment must be inside session_fork case block"
        )

    def test_session_fork_increment_after_validation(self):
        """The increment must appear after sub-session validation (not at top, to avoid orphaned counts)."""
        content = html()
        fork_case = "case 'session_fork':"
        increment = "activeDelegatesRef.current += 1;"
        early_exit = "if (!parentToolCallId || !parentItemId) break;"
        fork_pos = content.find(fork_case)
        assert fork_pos != -1
        exit_pos = content.find(early_exit, fork_pos)
        inc_pos = content.find(increment, fork_pos)
        assert exit_pos != -1, "early exit guard not found in session_fork"
        assert inc_pos != -1, "increment not found in session_fork"
        # The increment must appear AFTER the early exit guard (only count trackable delegates)
        assert inc_pos > exit_pos, (
            "Increment must appear after parentToolCallId/parentItemId validation"
        )


# ---------------------------------------------------------------------------
# Step 3 — tool_result decrements when a delegate completes
# ---------------------------------------------------------------------------


class TestToolResultDecrement:
    def test_tool_result_decrements_active_delegates(self):
        """tool_result case must decrement activeDelegatesRef.current for delegate results."""
        assert "activeDelegatesRef.current -= 1;" in html()

    def test_tool_result_decrement_inside_sub_session_check(self):
        """Decrement must be inside the subSessionsRef.current.has() check block."""
        content = html()
        sub_check = "if (subSessionsRef.current.has(msg.tool_call_id))"
        decrement = "activeDelegatesRef.current -= 1;"
        sub_pos = content.find(sub_check)
        assert sub_pos != -1, "subSessionsRef.current.has() check not found"
        # Decrement must appear after the sub-session check
        dec_pos = content.find(decrement, sub_pos)
        assert dec_pos != -1, "decrement not found after sub-session check"
        # And within ~300 chars (inside the if block)
        assert (dec_pos - sub_pos) < 300, "decrement not inside sub-session check block"

    def test_tool_result_decrement_has_guard_against_going_negative(self):
        """Decrement must be guarded: if (activeDelegatesRef.current > 0)."""
        assert (
            "if (activeDelegatesRef.current > 0) activeDelegatesRef.current -= 1;"
            in html()
        )


# ---------------------------------------------------------------------------
# Step 4 — prompt_complete guards setExecuting and tryDrainQueue
# ---------------------------------------------------------------------------


class TestPromptCompleteGuard:
    def test_prompt_complete_has_delegate_and_session_guard(self):
        """prompt_complete must have activeDelegatesRef + ownerKey guard for setExecuting/drain."""
        content = html()
        assert (
            "if (activeDelegatesRef.current <= 0 && ownerKey === activeKeyRef.current)"
            in content
        )

    def test_prompt_complete_set_executing_inside_delegate_guard(self):
        """setExecuting(false) in prompt_complete must be inside activeDelegatesRef guard."""
        content = html()
        prompt_complete_case = "case 'prompt_complete':"
        case_pos = content.find(prompt_complete_case)
        assert case_pos != -1, "prompt_complete case not found"
        # Find the guard within the prompt_complete block
        guard = (
            "if (activeDelegatesRef.current <= 0 && ownerKey === activeKeyRef.current)"
        )
        guard_pos = content.find(guard, case_pos)
        assert guard_pos != -1, "delegate+session guard not found in prompt_complete"
        # setExecuting(false) must appear inside the guard (within ~300 chars)
        nearby = content[guard_pos : guard_pos + 300]
        assert "setExecuting(false);" in nearby, (
            f"setExecuting(false) not inside delegate guard: {nearby!r}"
        )

    def test_prompt_complete_try_drain_queue_inside_delegate_guard(self):
        """tryDrainQueue() in prompt_complete must be inside activeDelegatesRef guard."""
        content = html()
        prompt_complete_case = "case 'prompt_complete':"
        case_pos = content.find(prompt_complete_case)
        assert case_pos != -1
        guard = (
            "if (activeDelegatesRef.current <= 0 && ownerKey === activeKeyRef.current)"
        )
        guard_pos = content.find(guard, case_pos)
        assert guard_pos != -1
        nearby = content[guard_pos : guard_pos + 300]
        assert "tryDrainQueue();" in nearby, (
            f"tryDrainQueue() not inside delegate guard: {nearby!r}"
        )


# ---------------------------------------------------------------------------
# Step 5 — execution_cancelled guards setExecuting and tryDrainQueue
# ---------------------------------------------------------------------------


class TestExecutionCancelledGuard:
    def test_execution_cancelled_has_delegate_and_session_guard(self):
        """execution_cancelled must guard setExecuting/drain with activeDelegatesRef + ownerKey."""
        content = html()
        cancelled_case = "case 'execution_cancelled':"
        case_pos = content.find(cancelled_case)
        assert case_pos != -1, "execution_cancelled case not found"
        guard = "if (activeDelegatesRef.current <= 0 && ownerKey === activeKeyRef.current)"
        guard_pos = content.find(guard, case_pos)
        assert guard_pos != -1, "delegate+session guard not found in execution_cancelled"

    def test_execution_cancelled_set_executing_inside_guard(self):
        """setExecuting(false) in execution_cancelled must be inside delegate guard."""
        content = html()
        cancelled_case = "case 'execution_cancelled':"
        case_pos = content.find(cancelled_case)
        assert case_pos != -1
        guard = "if (activeDelegatesRef.current <= 0 && ownerKey === activeKeyRef.current)"
        guard_pos = content.find(guard, case_pos)
        assert guard_pos != -1
        nearby = content[guard_pos : guard_pos + 300]
        assert "setExecuting(false);" in nearby
        assert "tryDrainQueue();" in nearby


# ---------------------------------------------------------------------------
# Step 6 — execution_error guards setExecuting and tryDrainQueue
# ---------------------------------------------------------------------------


class TestExecutionErrorGuard:
    def test_execution_error_has_delegate_and_session_guard(self):
        """execution_error must guard setExecuting/drain with activeDelegatesRef + ownerKey."""
        content = html()
        error_case = "case 'execution_error':"
        case_pos = content.find(error_case)
        assert case_pos != -1, "execution_error case not found"
        guard = "if (activeDelegatesRef.current <= 0 && ownerKey === activeKeyRef.current)"
        guard_pos = content.find(guard, case_pos)
        assert guard_pos != -1, "delegate+session guard not found in execution_error"

    def test_execution_error_set_executing_inside_guard(self):
        """setExecuting(false) in execution_error must be inside delegate guard."""
        content = html()
        error_case = "case 'execution_error':"
        case_pos = content.find(error_case)
        assert case_pos != -1
        guard = "if (activeDelegatesRef.current <= 0 && ownerKey === activeKeyRef.current)"
        guard_pos = content.find(guard, case_pos)
        assert guard_pos != -1
        nearby = content[guard_pos : guard_pos + 300]
        assert "setExecuting(false);" in nearby
        assert "tryDrainQueue();" in nearby


# ---------------------------------------------------------------------------
# Step 7 — newSession and switchSession reset the counter
# ---------------------------------------------------------------------------


class TestSessionResetDelegateCount:
    def test_new_session_resets_active_delegates(self):
        """newSession must reset activeDelegatesRef.current to 0."""
        content = html()
        new_session_def = "const newSession = useCallback(() => {"
        ns_pos = content.find(new_session_def)
        assert ns_pos != -1, "newSession function not found"
        body = content[ns_pos : ns_pos + 3000]
        assert "activeDelegatesRef.current = 0;" in body, (
            "activeDelegatesRef.current = 0 not found in newSession body"
        )

    def test_new_session_resets_after_cancel_countdown(self):
        """activeDelegatesRef reset must appear after cancelCountdown() in newSession."""
        content = html()
        new_session_def = "const newSession = useCallback(() => {"
        ns_pos = content.find(new_session_def)
        assert ns_pos != -1
        body = content[ns_pos : ns_pos + 3000]
        cancel_pos = body.find("cancelCountdown();")
        reset_pos = body.find("activeDelegatesRef.current = 0;")
        assert cancel_pos != -1, "cancelCountdown() not found in newSession"
        assert reset_pos != -1, "activeDelegatesRef reset not found in newSession"
        assert cancel_pos < reset_pos, (
            "activeDelegatesRef reset must come after cancelCountdown()"
        )

    def test_switch_session_resets_active_delegates(self):
        """switchSession must reset activeDelegatesRef.current to 0."""
        content = html()
        switch_session_def = "const switchSession = useCallback((key) => {"
        ss_pos = content.find(switch_session_def)
        assert ss_pos != -1, "switchSession function not found"
        body = content[ss_pos : ss_pos + 3000]
        assert "activeDelegatesRef.current = 0;" in body, (
            "activeDelegatesRef.current = 0 not found in switchSession body"
        )

    def test_switch_session_resets_after_cancel_countdown(self):
        """activeDelegatesRef reset must appear after cancelCountdown() in switchSession."""
        content = html()
        switch_session_def = "const switchSession = useCallback((key) => {"
        ss_pos = content.find(switch_session_def)
        assert ss_pos != -1
        body = content[ss_pos : ss_pos + 3000]
        # cancelCountdown now accepts a session key parameter
        cancel_pos = body.find("cancelCountdown(currentKey)")
        if cancel_pos == -1:
            cancel_pos = body.find("cancelCountdown(")
        reset_pos = body.find("activeDelegatesRef.current = 0;")
        assert cancel_pos != -1, "cancelCountdown() not found in switchSession"
        assert reset_pos != -1, "activeDelegatesRef reset not found in switchSession"
        assert cancel_pos < reset_pos, (
            "activeDelegatesRef reset must come after cancelCountdown()"
        )
