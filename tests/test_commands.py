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

    # Build mock coordinator with get() and config
    mock_coordinator = MagicMock()
    mock_coordinator.get.side_effect = lambda key: (
        mock_context if key == "context" else None
    )
    mock_coordinator.config = {"agents": {"default": {}, "coder": {}}}

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
    assert len(result["data"]["commands"]) > 0


def test_unknown_command(processor):
    result = processor.handle_command("nonexistent", [], session_id=None)
    assert result["type"] == "error"


def test_command_endpoint(client):
    resp = client.post("/chat/command", json={"command": "/help"})
    assert resp.status_code == 200
    assert resp.json()["type"] == "help"


def test_status_command_no_session(processor):
    result = processor.handle_command("status", [], session_id=None)
    assert result["type"] == "error"
    assert "no active session" in result["data"]["message"].lower()


def test_cwd_command(processor_with_mock_session):
    result = processor_with_mock_session.handle_command("cwd", [], session_id="abc")
    assert result["type"] == "cwd"
    assert "working_dir" in result["data"]


def test_status_command(processor_with_mock_session):
    result = processor_with_mock_session.handle_command("status", [], session_id="abc")
    assert result["type"] == "status"
    assert "session_id" in result["data"]


def test_clear_command(processor_with_mock_session):
    result = processor_with_mock_session.handle_command("clear", [], session_id="abc")
    assert result["type"] == "cleared"


def test_tools_command(processor_with_mock_session):
    result = processor_with_mock_session.handle_command("tools", [], session_id="abc")
    assert result["type"] == "tools"


def test_agents_command(processor_with_mock_session):
    result = processor_with_mock_session.handle_command("agents", [], session_id="abc")
    assert result["type"] == "agents"


def test_config_command(processor_with_mock_session):
    result = processor_with_mock_session.handle_command("config", [], session_id="abc")
    assert result["type"] == "config"
