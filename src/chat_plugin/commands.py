from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class CommandDef:
    name: str
    description: str
    usage: str = ""


COMMANDS: list[CommandDef] = [
    CommandDef("help", "Show available commands"),
    CommandDef("status", "Show session status"),
    CommandDef("tools", "List available tools"),
    CommandDef("agents", "List available agents"),
    CommandDef("config", "Show session configuration"),
    CommandDef("cwd", "Show working directory"),
    CommandDef("clear", "Clear conversation context"),
    CommandDef("modes", "List available modes"),
    CommandDef("mode", "Activate/deactivate a mode", "/mode <name> [on|off]"),
    CommandDef("rename", "Rename the session", "/rename <name>"),
    CommandDef("fork", "Fork session at a turn", "/fork [turn]"),
]


class CommandProcessor:
    def __init__(self, *, session_manager: Any, event_bus: Any) -> None:
        self._session_manager = session_manager
        self._event_bus = event_bus

    def process_input(self, text: str) -> tuple[str, dict]:
        text = text.strip()
        if text.startswith("/"):
            parts = text[1:].split(None, 1)
            command = parts[0] if parts else ""
            args = parts[1].split() if len(parts) > 1 else []
            return "command", {"command": command, "args": args, "raw": text}
        return "prompt", {"text": text}

    def handle_command(
        self, command: str, args: list[str], *, session_id: str | None
    ) -> dict:
        handler = getattr(self, f"_cmd_{command}", None)
        if handler is None:
            return {
                "type": "error",
                "data": {"message": f"Unknown command: /{command}"},
            }
        return handler(args, session_id=session_id)

    def _require_session(self, session_id: str | None) -> Any:
        """Get session handle or return None."""
        if not session_id:
            return None
        if not self._session_manager:
            return None
        return self._session_manager.get(session_id)

    def _error(self, message: str) -> dict:
        return {"type": "error", "data": {"message": message}}

    def _cmd_status(self, args: list[str], *, session_id: str | None = None) -> dict:
        handle = self._require_session(session_id)
        if not handle:
            return self._error("No active session")
        return {
            "type": "status",
            "data": {
                "session_id": handle.session_id,
                "status": str(handle.status),
                "turn_count": handle.turn_count,
                "bundle_name": handle.bundle_name,
            },
        }

    def _cmd_cwd(self, args: list[str], *, session_id: str | None = None) -> dict:
        handle = self._require_session(session_id)
        if not handle:
            return self._error("No active session")
        return {"type": "cwd", "data": {"working_dir": handle.working_dir}}

    def _cmd_clear(self, args: list[str], *, session_id: str | None = None) -> dict:
        handle = self._require_session(session_id)
        if not handle:
            return self._error("No active session")
        try:
            ctx = handle.session.coordinator.get("context")
            ctx.clear()
        except Exception:
            pass  # best effort
        return {"type": "cleared", "data": {"session_id": session_id}}

    def _cmd_tools(self, args: list[str], *, session_id: str | None = None) -> dict:
        handle = self._require_session(session_id)
        if not handle:
            return self._error("No active session")
        try:
            tools = handle.session.coordinator.get("tools")
            tool_list = (
                [
                    {"name": t.name, "description": getattr(t, "description", "")}
                    for t in tools
                ]
                if tools
                else []
            )
        except Exception:
            tool_list = []
        return {"type": "tools", "data": {"tools": tool_list}}

    def _cmd_agents(self, args: list[str], *, session_id: str | None = None) -> dict:
        handle = self._require_session(session_id)
        if not handle:
            return self._error("No active session")
        try:
            config = handle.session.coordinator.config
            agents = config.get("agents", {})
            agent_list = [{"name": name} for name in agents]
        except Exception:
            agent_list = []
        return {"type": "agents", "data": {"agents": agent_list}}

    def _cmd_config(self, args: list[str], *, session_id: str | None = None) -> dict:
        handle = self._require_session(session_id)
        if not handle:
            return self._error("No active session")
        try:
            config = handle.session.coordinator.config
            return {"type": "config", "data": {"config": dict(config)}}
        except Exception:
            return {"type": "config", "data": {"config": {}}}

    def _cmd_help(self, args: list[str], **_: Any) -> dict:
        return {
            "type": "help",
            "data": {
                "commands": [
                    {
                        "name": f"/{c.name}",
                        "description": c.description,
                        "usage": c.usage,
                    }
                    for c in COMMANDS
                ],
            },
        }
