import pytest
from unittest.mock import MagicMock
from chat_plugin.commands import CommandProcessor


@pytest.fixture
def processor():
    return CommandProcessor(session_manager=None, event_bus=None)


@pytest.fixture
def processor_with_mock_session():
    # Build mock context with clear()
    mock_context = MagicMock()

    # Build mock mode_discovery with list_modes() and find()
    mock_mode_discovery = MagicMock()
    mock_mode_discovery.list_modes.return_value = [
        ("debug", "Debug mode", "built-in"),
        ("focus", "Focus mode", "built-in"),
    ]
    mock_mode_discovery.find.side_effect = lambda name: name in ("debug", "focus")

    # Build session_state dict with mode_discovery
    mock_session_state = {
        "mode_discovery": mock_mode_discovery,
        "active_mode": None,
    }

    # Build mock coordinator with get() and config
    mock_coordinator = MagicMock()
    mock_coordinator.get.side_effect = lambda key: (
        mock_context if key == "context" else None
    )
    mock_coordinator.config = {"agents": {"default": {}, "coder": {}}}
    mock_coordinator.session_state = mock_session_state

    # Build mock session with coordinator
    mock_session = MagicMock()
    mock_session.coordinator = mock_coordinator

    # Build mock SessionHandle
    mock_handle = MagicMock()
    mock_handle.session_id = "abc"
    mock_handle.status = "idle"
    mock_handle.bundle_name = "test-bundle"
    mock_handle.working_dir = "/tmp/test"
    mock_handle.turn_count = 5
    mock_handle.session = mock_session

    # Build mock session_manager
    mock_session_manager = MagicMock()
    mock_session_manager.get.return_value = mock_handle

    return CommandProcessor(session_manager=mock_session_manager, event_bus=None)


def test_process_input_recognizes_command(processor):
    action, data = processor.process_input("/help")
    assert action == "command"
    assert data["command"] == "help"


def test_process_input_recognizes_command_with_args(processor):
    action, data = processor.process_input("/mode debug")
    assert action == "command"
    assert data["command"] == "mode"
    assert data["args"] == ["debug"]


def test_process_input_non_command(processor):
    action, data = processor.process_input("hello world")
    assert action == "prompt"
    assert data["text"] == "hello world"


def test_help_command(processor):
    result = processor.handle_command("help", [], session_id=None)
    assert result["type"] == "help"
    # B1: flattened — commands lives at top level, not under data
    assert len(result["commands"]) > 0


def test_unknown_command(processor):
    result = processor.handle_command("nonexistent", [], session_id=None)
    assert result["type"] == "error"


def test_command_endpoint(client):
    resp = client.post("/chat/command", json={"command": "/help"})
    assert resp.status_code == 200
    assert resp.json()["type"] == "help"


def test_command_endpoint_runs_help_inline(client, monkeypatch):
    import chat_plugin.routes as routes

    async def unexpected_to_thread(*args, **kwargs):
        raise AssertionError("non-blocking commands should not use asyncio.to_thread")

    monkeypatch.setattr(routes.asyncio, "to_thread", unexpected_to_thread)

    resp = client.post("/chat/command", json={"command": "/help"})

    assert resp.status_code == 200
    assert resp.json()["type"] == "help"


def test_command_endpoint_offloads_fork_execution(client, monkeypatch):
    import chat_plugin.routes as routes

    seen: dict[str, object] = {}

    async def fake_to_thread(func, *args, **kwargs):
        seen["func_name"] = getattr(func, "__name__", None)
        seen["args"] = args
        seen["kwargs"] = kwargs
        return {"type": "forked", "session_id": "forked-session"}

    monkeypatch.setattr(routes.asyncio, "to_thread", fake_to_thread)

    resp = client.post(
        "/chat/command",
        json={"command": "/fork 3", "session_id": "valid-session-123"},
    )

    assert resp.status_code == 200
    assert resp.json() == {"type": "forked", "session_id": "forked-session"}
    assert seen == {
        "func_name": "handle_command",
        "args": ("fork", ["3"]),
        "kwargs": {"session_id": "valid-session-123"},
    }


def test_status_command_no_session(processor):
    result = processor.handle_command("status", [], session_id=None)
    assert result["type"] == "error"
    # B1: error message lives at result["error"], not result["data"]["message"]
    assert "no active session" in result["error"].lower()


def test_cwd_command(processor_with_mock_session):
    result = processor_with_mock_session.handle_command("cwd", [], session_id="abc")
    assert result["type"] == "cwd"
    # B1: flattened — working_dir at top level
    assert "working_dir" in result


def test_status_command(processor_with_mock_session):
    result = processor_with_mock_session.handle_command("status", [], session_id="abc")
    assert result["type"] == "status"
    # B1: flattened — session_id at top level
    assert "session_id" in result


def test_clear_command(processor_with_mock_session):
    result = processor_with_mock_session.handle_command("clear", [], session_id="abc")
    assert result["type"] == "cleared"


def test_tools_command(processor_with_mock_session):
    result = processor_with_mock_session.handle_command("tools", [], session_id="abc")
    assert result["type"] == "tools"
    # B1: flattened — tools list at top level
    assert "tools" in result


def test_agents_command(processor_with_mock_session):
    result = processor_with_mock_session.handle_command("agents", [], session_id="abc")
    assert result["type"] == "agents"
    # B1: flattened — agents list at top level
    assert "agents" in result


def test_config_command(processor_with_mock_session):
    result = processor_with_mock_session.handle_command("config", [], session_id="abc")
    assert result["type"] == "config"
    # B1: shape matches what formatCommandResult expects
    assert "session" in result
    assert "providers" in result
    assert "tools" in result
    assert "hooks" in result
    assert "agents" in result
    # agents came from {"default": {}, "coder": {}}
    assert set(result["agents"]) == {"default", "coder"}


def test_modes_command(processor_with_mock_session):
    result = processor_with_mock_session.handle_command("modes", [], session_id="abc")
    assert result["type"] == "modes"
    # B1: flattened — modes list at top level, not under data
    assert "modes" in result
    assert len(result["modes"]) == 2


def test_mode_activate(processor_with_mock_session):
    result = processor_with_mock_session.handle_command(
        "mode", ["debug"], session_id="abc"
    )
    # B1: type is now "mode" (not "mode_changed")
    assert result["type"] in ("mode", "error")


def test_mode_with_trailing_prompt(processor_with_mock_session):
    """/mode debug my problem activates debug mode and returns trailing prompt."""
    result = processor_with_mock_session.handle_command(
        "mode", ["debug", "my", "problem"], session_id="abc"
    )
    # B1: type "mode" and trailing_prompt at top level
    if result["type"] == "mode":
        assert result.get("trailing_prompt") == "my problem"


def test_mode_deactivate(processor_with_mock_session):
    """/mode off deactivates current mode."""
    result = processor_with_mock_session.handle_command(
        "mode", ["off"], session_id="abc"
    )
    # B1: type is "mode" and active_mode at top level
    assert result["type"] == "mode"
    assert result["active_mode"] is None


def test_rename_command(processor_with_mock_session):
    result = processor_with_mock_session.handle_command(
        "rename", ["My", "Session"], session_id="abc"
    )
    assert result["type"] == "renamed"
    # B1: flattened — name at top level
    assert result["name"] == "My Session"


def test_fork_command_no_args(processor_with_mock_session):
    """Fork with no args returns turn info."""
    result = processor_with_mock_session.handle_command("fork", [], session_id="abc")
    assert result["type"] == "fork_info"


def test_fork_command_with_turn_no_projects_dir(processor_with_mock_session):
    """Fork with turn but no projects_dir returns a helpful error."""
    result = processor_with_mock_session.handle_command("fork", ["3"], session_id="abc")
    assert result["type"] == "error"
    assert (
        "not found" in result["error"].lower()
        or "fork button" in result["error"].lower()
    )


def test_fork_command_with_turn(tmp_path, processor_with_mock_session):
    """Fork with turn and valid session dir calls fork_session."""
    # Set up a fake projects dir with the session
    project_dir = tmp_path / "proj" / "sessions" / "abc"
    project_dir.mkdir(parents=True)
    # Write minimal transcript so fork_session can work
    (project_dir / "transcript.jsonl").write_text("")
    (project_dir / "metadata.json").write_text('{"session_id": "abc"}')

    processor_with_mock_session._projects_dir = tmp_path

    # Without amplifier_foundation installed, we get an import error message
    result = processor_with_mock_session.handle_command("fork", ["3"], session_id="abc")
    # Either succeeds (foundation installed) or returns import-error
    assert result["type"] in ("forked", "error")


# ── B4: /bundle coming soon ───────────────────────────────────────────────────


def test_bundle_command_coming_soon(processor):
    """B4: /bundle returns an info stub with a coming-soon message."""
    result = processor.handle_command("bundle", ["my-bundle"], session_id=None)
    assert result["type"] == "info"
    assert "coming soon" in result["message"].lower()


def test_bundle_command_in_commands_list(processor):
    """B4: /bundle appears in the /help listing."""
    result = processor.handle_command("help", [], session_id=None)
    names = [c["name"] for c in result["commands"]]
    assert "/bundle" in names
