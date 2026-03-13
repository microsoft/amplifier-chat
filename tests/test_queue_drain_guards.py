"""
Tests for premature queue drain bug fixes (3 bugs).

Bug 1: tryDrainQueue() has no `executing` guard — needs executingRef
Bug 2: tryDrainQueue() can double-start a countdown — needs drainState === 'countdown' guard
Bug 3: switchSession() calls tryDrainQueue() unconditionally while target may be running
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
# Bug 1a — executingRef declaration
# ---------------------------------------------------------------------------


class TestExecutingRef:
    def test_executing_ref_declared(self):
        """executingRef = useRef(false) must be declared."""
        assert "const executingRef = useRef(false);" in html()

    def test_executing_ref_declared_near_executing_state(self):
        """executingRef must be declared close to the executing useState."""
        content = html()
        state_decl = "const [executing, setExecuting] = useState(false);"
        ref_decl = "const executingRef = useRef(false);"
        state_pos = content.find(state_decl)
        ref_pos = content.find(ref_decl)
        assert state_pos != -1, "executing state declaration not found"
        assert ref_pos != -1, "executingRef declaration not found"
        # The ref should appear within 5 lines (roughly 200 chars) of the state declaration
        assert abs(ref_pos - state_pos) < 200, (
            f"executingRef ({ref_pos}) not near executing state ({state_pos})"
        )

    def test_executing_ref_synced_via_use_effect(self):
        """useEffect must sync executingRef.current = executing."""
        assert "executingRef.current = executing;" in html()

    def test_executing_ref_sync_effect_has_executing_dependency(self):
        """The useEffect that syncs executingRef must list [executing] as dependency."""
        content = html()
        sync_line = "executingRef.current = executing;"
        sync_pos = content.find(sync_line)
        assert sync_pos != -1, "executingRef sync line not found"
        # The closing of this effect (}, [executing]) should be near the sync line
        nearby = content[sync_pos : sync_pos + 100]
        assert "[executing]" in nearby, (
            f"[executing] dependency not found near sync line: {nearby!r}"
        )

    def test_try_drain_queue_has_executing_ref_guard(self):
        """tryDrainQueue() must check executingRef.current early."""
        content = html()
        fn_pos = content.find("function tryDrainQueue()")
        assert fn_pos != -1, "tryDrainQueue not found"
        # The guard must appear inside the function body (within 500 chars)
        body = content[fn_pos : fn_pos + 500]
        assert "if (executingRef.current) return;" in body, (
            f"executingRef guard not found in tryDrainQueue body: {body!r}"
        )

    def test_try_drain_queue_executing_ref_guard_before_queue_read(self):
        """The executingRef guard must come before the queue is read."""
        content = html()
        fn_pos = content.find("function tryDrainQueue()")
        body = content[fn_pos : fn_pos + 500]
        guard_pos = body.find("if (executingRef.current) return;")
        queue_read_pos = body.find("getQueue(key)")
        assert guard_pos != -1, "executingRef guard not in tryDrainQueue"
        assert queue_read_pos != -1, "getQueue(key) not in tryDrainQueue"
        assert guard_pos < queue_read_pos, (
            "executingRef guard must appear before getQueue(key)"
        )

    def test_countdown_callback_has_executing_ref_guard(self):
        """The startCountdown callback must abort if executing or session switched when it fires."""
        content = html()
        fn_pos = content.find("function tryDrainQueue()")
        fn_body = content[fn_pos : fn_pos + 1000]
        assert (
            "if (executingRef.current || activeKeyRef.current !== key) {" in fn_body
        ), (
            "executingRef + activeKey guard not found inside tryDrainQueue countdown callback"
        )

    def test_countdown_callback_guard_resets_drain_state_to_idle(self):
        """When the countdown guard fires, drain state must be reset to idle."""
        content = html()
        fn_pos = content.find("function tryDrainQueue()")
        fn_body = content[fn_pos : fn_pos + 1000]
        guard_pos = fn_body.find(
            "if (executingRef.current || activeKeyRef.current !== key) {"
        )
        assert guard_pos != -1
        guard_block = fn_body[guard_pos : guard_pos + 150]
        assert "setQueueDrainStateFn('idle', key)" in guard_block, (
            f"idle reset not in executingRef guard block: {guard_block!r}"
        )


# ---------------------------------------------------------------------------
# Bug 2 — countdown double-start guard
# ---------------------------------------------------------------------------


class TestCountdownDoubleStartGuard:
    def test_try_drain_queue_guards_against_countdown_state(self):
        """tryDrainQueue() early-return condition must include drainState === 'countdown'."""
        content = html()
        assert "drainState === 'countdown'" in content, (
            "drainState === 'countdown' guard not found"
        )

    def test_countdown_guard_is_in_early_return_condition(self):
        """The countdown guard must be on the same condition as the paused guard."""
        content = html()
        fn_pos = content.find("function tryDrainQueue()")
        fn_body = content[fn_pos : fn_pos + 500]
        # The condition must have both paused and countdown together
        assert "drainState === 'paused' || drainState === 'countdown'" in fn_body, (
            "Combined paused || countdown guard not found in tryDrainQueue"
        )


# ---------------------------------------------------------------------------
# Bug 3 — switchSession running guard
# ---------------------------------------------------------------------------


class TestSwitchSessionRunningGuard:
    def test_switch_session_guards_try_drain_queue_when_running(self):
        """switchSession must check target.status !== 'running' before calling tryDrainQueue."""
        content = html()
        assert "target.status !== 'running'" in content, (
            "target.status !== 'running' guard not found"
        )

    def test_switch_session_drain_guard_precedes_try_drain_queue(self):
        """The target.status check must be on the same line as the countdown drain call."""
        content = html()
        guard = "target.status !== 'running' && getQueueDrainState(key) === 'countdown'"
        assert guard in content, f"Combined guard not found: {guard!r}"

    def test_switch_session_drain_guard_after_set_executing(self):
        """The running guard must come after setExecuting(target.status === 'running')."""
        content = html()
        set_exec = "setExecuting(target.status === 'running');"
        guard = "target.status !== 'running' && getQueueDrainState(key) === 'countdown'"
        exec_pos = content.find(set_exec)
        guard_pos = content.find(guard, exec_pos)
        assert exec_pos != -1, "setExecuting(target.status === 'running') not found"
        assert guard_pos != -1, "Combined running guard not found after setExecuting"
        assert exec_pos < guard_pos
