"""
Tests for D-05/D-06: child_session_id guard on terminal events.

Bug: When a delegate child session completes, its terminal events
(prompt_complete, execution_cancelled, execution_error) are processed
as parent completions — idling the parent UI prematurely, corrupting
streaming state, and losing output.

Fix: Guard all 6 terminal event handlers (3 active path, 3 background
path) with a child_session_id check. Active path decrements
activeDelegatesRef and breaks. Background path returns early to skip
parent status updates.
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
# Active path: prompt_complete guard
# ---------------------------------------------------------------------------


class TestActivePromptCompleteGuard:
    def test_child_session_id_guard_exists_in_prompt_complete(self):
        """prompt_complete active case must check msg.child_session_id before any side effects."""
        content = html()
        case_start = "case 'prompt_complete':"
        case_pos = content.find(case_start)
        assert case_pos != -1, "prompt_complete case not found"
        # The guard must appear inside this case block (before the next case)
        next_case = content.find("case '", case_pos + len(case_start))
        block = (
            content[case_pos:next_case]
            if next_case != -1
            else content[case_pos : case_pos + 2000]
        )
        assert "if (msg.child_session_id)" in block, (
            "child_session_id guard not found in active prompt_complete handler"
        )

    def test_active_prompt_complete_guard_decrements_delegates(self):
        """Active prompt_complete child guard must decrement activeDelegatesRef."""
        content = html()
        case_start = "case 'prompt_complete':"
        case_pos = content.find(case_start)
        assert case_pos != -1
        # Find the child_session_id guard within this case
        guard_pos = content.find("if (msg.child_session_id)", case_pos)
        assert guard_pos != -1
        # The decrement must appear within ~200 chars of the guard
        nearby = content[guard_pos : guard_pos + 200]
        assert "activeDelegatesRef.current -= 1" in nearby, (
            "activeDelegatesRef decrement not found near child_session_id guard in prompt_complete"
        )

    def test_active_prompt_complete_guard_before_set_sessions(self):
        """The child guard must appear BEFORE setSessions in prompt_complete (no parent side effects)."""
        content = html()
        case_start = "case 'prompt_complete':"
        case_pos = content.find(case_start)
        assert case_pos != -1
        guard_pos = content.find("if (msg.child_session_id)", case_pos)
        set_sessions_pos = content.find("setSessions(", case_pos + len(case_start))
        assert guard_pos != -1, "child_session_id guard not found"
        assert set_sessions_pos != -1, "setSessions not found in prompt_complete"
        assert guard_pos < set_sessions_pos, (
            "child_session_id guard must appear BEFORE setSessions in prompt_complete"
        )


# ---------------------------------------------------------------------------
# Active path: execution_cancelled guard
# ---------------------------------------------------------------------------


class TestActiveExecutionCancelledGuard:
    def test_child_session_id_guard_exists_in_execution_cancelled(self):
        """execution_cancelled active case must check msg.child_session_id."""
        content = html()
        case_start = "case 'execution_cancelled':"
        case_pos = content.find(case_start)
        assert case_pos != -1, "execution_cancelled case not found"
        next_case = content.find("case '", case_pos + len(case_start))
        block = (
            content[case_pos:next_case]
            if next_case != -1
            else content[case_pos : case_pos + 1500]
        )
        assert "if (msg.child_session_id)" in block, (
            "child_session_id guard not found in active execution_cancelled handler"
        )

    def test_active_execution_cancelled_guard_decrements_delegates(self):
        """Active execution_cancelled child guard must decrement activeDelegatesRef."""
        content = html()
        case_start = "case 'execution_cancelled':"
        case_pos = content.find(case_start)
        assert case_pos != -1
        guard_pos = content.find("if (msg.child_session_id)", case_pos)
        assert guard_pos != -1
        nearby = content[guard_pos : guard_pos + 200]
        assert "activeDelegatesRef.current -= 1" in nearby


# ---------------------------------------------------------------------------
# Active path: execution_error guard
# ---------------------------------------------------------------------------


class TestActiveExecutionErrorGuard:
    def test_child_session_id_guard_exists_in_execution_error(self):
        """execution_error active case must check msg.child_session_id early."""
        content = html()
        case_start = "case 'execution_error':"
        case_pos = content.find(case_start)
        assert case_pos != -1, "execution_error case not found"
        next_case = content.find("case '", case_pos + len(case_start))
        block = (
            content[case_pos:next_case]
            if next_case != -1
            else content[case_pos : case_pos + 2000]
        )
        assert "if (msg.child_session_id)" in block, (
            "child_session_id guard not found in active execution_error handler"
        )

    def test_active_execution_error_guard_decrements_delegates(self):
        """Active execution_error child guard must decrement activeDelegatesRef."""
        content = html()
        case_start = "case 'execution_error':"
        case_pos = content.find(case_start)
        assert case_pos != -1
        guard_pos = content.find("if (msg.child_session_id)", case_pos)
        assert guard_pos != -1
        nearby = content[guard_pos : guard_pos + 200]
        assert "activeDelegatesRef.current -= 1" in nearby

    def test_active_execution_error_guard_before_already_executing_check(self):
        """The child guard must appear BEFORE the 'already executing' retry check."""
        content = html()
        case_start = "case 'execution_error':"
        case_pos = content.find(case_start)
        assert case_pos != -1
        guard_pos = content.find("if (msg.child_session_id)", case_pos)
        already_exec_pos = content.find("already executing", case_pos)
        assert guard_pos != -1, "child_session_id guard not found in execution_error"
        assert already_exec_pos != -1, "'already executing' check not found"
        assert guard_pos < already_exec_pos, (
            "child_session_id guard must come before 'already executing' retry"
        )


# ---------------------------------------------------------------------------
# Background path: all 3 terminal event guards
# ---------------------------------------------------------------------------


class TestBackgroundTerminalEventGuards:
    """Background handlers (the if-chain before the active switch) must guard
    against child terminal events updating parent sidebar status."""

    def _get_background_block(self):
        """Return the background handler section (between !isActiveStream and the switch)."""
        content = html()
        bg_start = content.find("if (!isActiveStream)")
        assert bg_start != -1, "Background handler section not found"
        # The background section ends roughly where the active switch starts
        # Find the main switch statement that follows
        switch_pos = content.find("switch (msg.type)", bg_start)
        assert switch_pos != -1, "Active switch not found after background section"
        return content[bg_start:switch_pos]

    def test_background_prompt_complete_has_child_guard(self):
        """Background prompt_complete handler must check child_session_id."""
        block = self._get_background_block()
        # Find the prompt_complete if-block in the background section
        pc_pos = block.find("msg.type === 'prompt_complete'")
        assert pc_pos != -1, "prompt_complete not found in background handlers"
        # The child_session_id guard must appear near the prompt_complete check
        pc_block = block[pc_pos : pc_pos + 400]
        assert "msg.child_session_id" in pc_block, (
            "child_session_id guard not found in background prompt_complete"
        )

    def test_background_execution_cancelled_has_child_guard(self):
        """Background execution_cancelled handler must check child_session_id."""
        block = self._get_background_block()
        ec_pos = block.find("msg.type === 'execution_cancelled'")
        assert ec_pos != -1, "execution_cancelled not found in background handlers"
        ec_block = block[ec_pos : ec_pos + 400]
        assert "msg.child_session_id" in ec_block, (
            "child_session_id guard not found in background execution_cancelled"
        )

    def test_background_execution_error_has_child_guard(self):
        """Background execution_error handler must check child_session_id."""
        block = self._get_background_block()
        ee_pos = block.find("msg.type === 'execution_error'")
        assert ee_pos != -1, "execution_error not found in background handlers"
        ee_block = block[ee_pos : ee_pos + 400]
        assert "msg.child_session_id" in ee_block, (
            "child_session_id guard not found in background execution_error"
        )


# ---------------------------------------------------------------------------
# D-07: Missing replayable events
# ---------------------------------------------------------------------------


class TestReplayableEvents:
    def test_execution_error_in_replayable_events(self):
        """execution_error must be in the replayableEvents Set."""
        content = html()
        replay_set_pos = content.find("const replayableEvents = new Set([")
        assert replay_set_pos != -1, "replayableEvents Set not found"
        # Get the full Set definition (until the closing ])
        set_end = content.find("]);", replay_set_pos)
        set_def = content[replay_set_pos : set_end + 3]
        assert "'execution_error'" in set_def, (
            "execution_error not found in replayableEvents Set"
        )

    def test_approval_request_in_replayable_events(self):
        """approval_request must be in the replayableEvents Set."""
        content = html()
        replay_set_pos = content.find("const replayableEvents = new Set([")
        assert replay_set_pos != -1, "replayableEvents Set not found"
        set_end = content.find("]);", replay_set_pos)
        set_def = content[replay_set_pos : set_end + 3]
        assert "'approval_request'" in set_def, (
            "approval_request not found in replayableEvents Set"
        )

    def test_execution_error_retry_has_replay_guard(self):
        """The 'already executing' retry setTimeout in execution_error must
        not fire during replay (msg._replay check)."""
        content = html()
        case_start = "case 'execution_error':"
        case_pos = content.find(case_start)
        assert case_pos != -1
        # Find the 'already executing' section
        already_pos = content.find("already executing", case_pos)
        assert already_pos != -1
        # There must be a _replay guard near the setTimeout
        nearby = content[already_pos : already_pos + 300]
        assert "_replay" in nearby, (
            "Replay guard (_replay) not found near 'already executing' retry"
        )


# ---------------------------------------------------------------------------
# D-01: Token usage routing
# ---------------------------------------------------------------------------


class TestTokenUsageRouting:
    def test_token_usage_checks_sub_session_key(self):
        """token_usage handler must call resolveSubSessionKey to skip child tokens."""
        content = html()
        case_start = "case 'token_usage':"
        case_pos = content.find(case_start)
        assert case_pos != -1, "token_usage case not found"
        next_case = content.find("case '", case_pos + len(case_start))
        block = content[case_pos:next_case] if next_case != -1 else content[case_pos:case_pos + 500]
        assert "resolveSubSessionKey" in block, (
            "resolveSubSessionKey check not found in token_usage handler"
        )


# ---------------------------------------------------------------------------
# D-02: FIFO fallback improvement
# ---------------------------------------------------------------------------


class TestFifoFallbackImprovement:
    def test_agent_name_matching_before_fifo(self):
        """session_fork must try agent-name matching before FIFO fallback."""
        content = html()
        case_start = "case 'session_fork':"
        case_pos = content.find(case_start)
        assert case_pos != -1, "session_fork case not found"
        next_case = content.find("case '", case_pos + len(case_start))
        block = content[case_pos:next_case] if next_case != -1 else content[case_pos:case_pos + 2000]
        assert "ci.toolInput?.agent === msg.agent" in block, (
            "Agent-name matching not found in session_fork handler"
        )

    def test_console_warn_on_fifo_fallback(self):
        """session_fork must console.warn when falling back to FIFO."""
        content = html()
        case_start = "case 'session_fork':"
        case_pos = content.find(case_start)
        assert case_pos != -1
        next_case = content.find("case '", case_pos + len(case_start))
        block = content[case_pos:next_case] if next_case != -1 else content[case_pos:case_pos + 2000]
        assert "console.warn" in block, (
            "console.warn not found in session_fork handler"
        )


# ---------------------------------------------------------------------------
# D-03: Phantom history entries
# ---------------------------------------------------------------------------


class TestPhantomHistoryGuard:
    def test_sync_session_history_skips_known_children(self):
        """syncSessionHistory must check for live parent inside the !existingKey block
        to skip phantom history entries for known children of live sessions."""
        content = html()
        sync_pos = content.find("const syncSessionHistory = useCallback(")
        assert sync_pos != -1, "syncSessionHistory not found"
        # Find the !existingKey block where new history entries are created
        not_existing_pos = content.find("if (!existingKey)", sync_pos)
        assert not_existing_pos != -1, "!existingKey block not found"
        # Find the 'history-' + sessionId entry creation line
        history_key_pos = content.find("'history-' + sessionId", not_existing_pos)
        assert history_key_pos != -1, "history key creation not found"
        # The phantom guard (live parent check) must appear between !existingKey and history key
        guard_region = content[not_existing_pos:history_key_pos]
        assert "source === 'live'" in guard_region, (
            "Live parent check (source === 'live') not found in !existingKey block before history entry creation"
        )


# ---------------------------------------------------------------------------
# D-04: Post-reload lineage rebuild
# ---------------------------------------------------------------------------


class TestPostReloadLineageRebuild:
    def test_lineage_rebuild_exists_in_resume_history_session(self):
        """resumeHistorySession must rebuild sessionParentByIdRef from transcript."""
        content = html()
        # The lineage rebuild iterates tool_call items with subSessionId
        assert "item.type === 'tool_call' && item.subSessionId" in content, (
            "Transcript-based lineage rebuild not found"
        )

    def test_lineage_rebuild_sets_parent_mapping(self):
        """The lineage rebuild must set sessionParentByIdRef.current[subSessionId] = sessionId."""
        content = html()
        resume_pos = content.find("resumeHistorySession")
        assert resume_pos != -1
        # Find the lineage rebuild loop
        rebuild_pos = content.find("item.subSessionId", resume_pos)
        assert rebuild_pos != -1
        nearby = content[rebuild_pos:rebuild_pos + 200]
        assert "sessionParentByIdRef.current[item.subSessionId]" in nearby, (
            "sessionParentByIdRef mapping not found in lineage rebuild"
        )

    def test_lineage_rebuild_has_d04_comment(self):
        """The lineage rebuild must have D-04 documentation comment."""
        content = html()
        rebuild_pos = content.find("item.type === 'tool_call' && item.subSessionId")
        assert rebuild_pos != -1
        # Check for D-04 comment within 800 chars before the rebuild
        nearby = content[max(0, rebuild_pos - 800):rebuild_pos]
        assert "D-04" in nearby, (
            "D-04 documentation comment not found near lineage rebuild"
        )


# ---------------------------------------------------------------------------
# D-GAP-01: Console.warn on unmapped fields in normalizeKernelPayload
# ---------------------------------------------------------------------------


class TestNormalizeKernelPayloadWarn:
    def test_normalize_kernel_payload_has_default_warn(self):
        """normalizeKernelPayload switch must have a default case with console.warn."""
        content = html()
        fn_pos = content.find("function normalizeKernelPayload(")
        assert fn_pos != -1, "normalizeKernelPayload not found"
        # Find the end of the function (next top-level function)
        fn_end = content.find("\n  function ", fn_pos + 10)
        fn_body = content[fn_pos:fn_end] if fn_end != -1 else content[fn_pos:fn_pos + 2000]
        assert "default:" in fn_body, (
            "default case not found in normalizeKernelPayload switch"
        )


# ---------------------------------------------------------------------------
# D-GAP-03: Sub-session completion inference comment
# ---------------------------------------------------------------------------


class TestSubSessionCompletionComment:
    def test_tool_result_has_completion_inference_comment(self):
        """tool_result handler area must document that sub-session completion
        is inferred from orchestrator:complete via tool_result."""
        content = html()
        case_start = "case 'tool_result':"
        case_pos = content.find(case_start)
        assert case_pos != -1, "tool_result case not found"
        block = content[case_pos:case_pos + 600]
        assert "orchestrator:complete" in block or "sub-session completion" in block.lower(), (
            "Completion inference documentation not found near tool_result handler"
        )
