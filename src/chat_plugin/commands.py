from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from chat_plugin.session_utils import patch_forked_metadata

logger = logging.getLogger(__name__)


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
    CommandDef(
        "bundle", "Switch to a different bundle (coming soon)", "/bundle <name>"
    ),
    CommandDef("voice", "Voice feature settings", "/voice [on|off]"),
    CommandDef("skills", "List available skills"),
    CommandDef("skill", "Load a skill", "/skill <name> [context]"),
]


class CommandProcessor:
    def __init__(
        self,
        *,
        session_manager: Any,
        event_bus: Any,
        projects_dir: Any | None = None,
    ) -> None:
        self._session_manager = session_manager
        self._event_bus = event_bus
        self._projects_dir = projects_dir

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
            return {"type": "error", "error": f"Unknown command: /{command}"}
        return handler(args, session_id=session_id)

    def _find_session_dir(self, session_id: str) -> Path | None:
        """Locate session directory on disk by scanning projects_dir."""
        if not self._projects_dir:
            return None
        projects = Path(self._projects_dir)
        if not projects.is_dir():
            return None
        for project_dir in projects.iterdir():
            if not project_dir.is_dir():
                continue
            candidate = project_dir / "sessions" / session_id
            if candidate.is_dir():
                return candidate
        return None

    def _require_session(self, session_id: str | None) -> Any:
        """Get session handle or return None."""
        if not session_id:
            return None
        if not self._session_manager:
            return None
        return self._session_manager.get(session_id)

    def _error(self, message: str) -> dict:
        # B1: Top-level "error" key so formatCommandResult's
        # `if (result.error)` check works correctly.
        return {"type": "error", "error": message}

    def _cmd_status(self, args: list[str], *, session_id: str | None = None) -> dict:
        handle = self._require_session(session_id)
        if not handle:
            return self._error("No active session")
        # B1: Flatten — frontend reads result.session_id, result.status, etc.
        return {
            "type": "status",
            "session_id": handle.session_id,
            "status": str(handle.status),
            "turn_count": handle.turn_count,
            "bundle_name": handle.bundle_name,
        }

    def _cmd_cwd(self, args: list[str], *, session_id: str | None = None) -> dict:
        handle = self._require_session(session_id)
        if not handle:
            return self._error("No active session")
        # B1: Flatten
        return {"type": "cwd", "working_dir": handle.working_dir}

    def _cmd_clear(self, args: list[str], *, session_id: str | None = None) -> dict:
        handle = self._require_session(session_id)
        if not handle:
            return self._error("No active session")
        try:
            ctx = handle.session.coordinator.get("context")
            ctx.clear()
        except Exception:
            logger.warning(
                "Could not clear context for session %s", session_id, exc_info=True
            )
        # B1: Flatten
        return {"type": "cleared", "session_id": session_id}

    def _cmd_tools(self, args: list[str], *, session_id: str | None = None) -> dict:
        handle = self._require_session(session_id)
        if not handle:
            return self._error("No active session")
        try:
            # coordinator.get("tools") returns a dict {name: tool_object},
            # not a list — iterating it directly yields only string keys.
            # Mirror the pattern used in routes/sessions.py list_tools().
            tools: dict = handle.session.coordinator.get("tools") or {}
            tool_list = [
                {"name": name, "description": getattr(tool, "description", "")}
                for name, tool in tools.items()
            ]
        except Exception:
            logger.exception("Failed to list tools for session %s", session_id)
            tool_list = []
        # B1: Flatten — frontend reads result.tools directly
        return {"type": "tools", "tools": tool_list}

    def _cmd_skills(self, args: list[str], *, session_id: str | None = None) -> dict:
        handle = self._require_session(session_id)
        if not handle:
            return self._error("No active session")
        try:
            coordinator = handle.session.coordinator
            # Try get_capability first (same pattern as amplifier-app-cli),
            # fall back to session_state dict (same pattern as _cmd_modes).
            discovery = None
            if hasattr(coordinator, "get_capability"):
                discovery = coordinator.get_capability("skills_discovery")
            if discovery is None:
                state = coordinator.session_state
                discovery = state.get("skills_discovery")

            if not discovery:
                return {"type": "skills", "skills": [], "shortcuts": []}

            raw_skills = discovery.list_skills()
            skill_list = [
                {"name": name, "description": description}
                for name, description, *_ in raw_skills
            ]
            shortcuts: list[str] = []
            if hasattr(discovery, "get_shortcuts"):
                shortcuts = list(discovery.get_shortcuts().keys())
        except Exception:
            skill_list = []
            shortcuts = []
        return {"type": "skills", "skills": skill_list, "shortcuts": shortcuts}

    def _cmd_agents(self, args: list[str], *, session_id: str | None = None) -> dict:
        handle = self._require_session(session_id)
        if not handle:
            return self._error("No active session")
        try:
            config = handle.session.coordinator.config
            agents_cfg = config.get("agents", {})
            if isinstance(agents_cfg, dict):
                agent_list = [
                    {
                        "name": name,
                        "description": info.get("description", "")
                        if isinstance(info, dict)
                        else "",
                    }
                    for name, info in agents_cfg.items()
                ]
            else:
                agent_list = [{"name": str(a), "description": ""} for a in agents_cfg]
        except Exception:
            logger.exception("Failed to list agents for session %s", session_id)
            agent_list = []
        # B1: Flatten — frontend reads result.agents directly
        return {"type": "agents", "agents": agent_list}

    def _cmd_config(self, args: list[str], *, session_id: str | None = None) -> dict:
        handle = self._require_session(session_id)
        if not handle:
            return self._error("No active session")
        try:
            config = handle.session.coordinator.config
            cfg = dict(config)
        except Exception:
            logger.exception("Failed to read config for session %s", session_id)
            cfg = {}

        # B1: Map raw coordinator config to the shape formatCommandResult expects:
        #   result.session   → {orchestrator, context}
        #   result.providers → [{module, model, priority}, ...]
        #   result.tools     → [name, ...]   (strings)
        #   result.hooks     → [name, ...]   (strings)
        #   result.agents    → [name, ...]   (strings)
        session_info = {
            "orchestrator": cfg.get("orchestrator", "unknown"),
            "context": cfg.get("context", "unknown"),
        }

        raw_providers = cfg.get("providers", [])
        providers = []
        for p in raw_providers if isinstance(raw_providers, list) else []:
            if isinstance(p, dict):
                providers.append(
                    {
                        "module": p.get("module", p.get("name", str(p))),
                        "model": p.get("model"),
                        "priority": p.get("priority"),
                    }
                )
            else:
                providers.append({"module": str(p), "model": None, "priority": None})

        raw_tools = cfg.get("tools", [])
        tools: list[str] = []
        for t in raw_tools if isinstance(raw_tools, list) else []:
            if isinstance(t, str):
                tools.append(t)
            elif isinstance(t, dict):
                tools.append(t.get("name", str(t)))
            else:
                tools.append(str(t))

        raw_hooks = cfg.get("hooks", [])
        hooks: list[str] = []
        for h in raw_hooks if isinstance(raw_hooks, list) else []:
            if isinstance(h, str):
                hooks.append(h)
            elif isinstance(h, dict):
                hooks.append(h.get("name", str(h)))
            else:
                hooks.append(str(h))

        raw_agents = cfg.get("agents", {})
        agents: list[str] = []
        if isinstance(raw_agents, dict):
            agents = list(raw_agents.keys())
        elif isinstance(raw_agents, list):
            for a in raw_agents:
                if isinstance(a, str):
                    agents.append(a)
                elif isinstance(a, dict):
                    agents.append(a.get("name", str(a)))
                else:
                    agents.append(str(a))

        return {
            "type": "config",
            "session": session_info,
            "providers": providers,
            "tools": tools,
            "hooks": hooks,
            "agents": agents,
        }

    def _cmd_modes(self, args: list[str], *, session_id: str | None = None) -> dict:
        handle = self._require_session(session_id)
        if not handle:
            return self._error("No active session")
        try:
            state = handle.session.coordinator.session_state
            discovery = state.get("mode_discovery")
            if not discovery:
                return {"type": "modes", "modes": [], "active_mode": None}
            modes = discovery.list_modes()
            # B1: Flatten — frontend reads result.modes and result.active_mode directly
            return {
                "type": "modes",
                "active_mode": state.get("active_mode"),
                "modes": [
                    {"name": n, "description": d, "source": s} for n, d, s in modes
                ],
            }
        except Exception:
            logger.exception("Failed to list modes for session %s", session_id)
            return {"type": "modes", "modes": [], "active_mode": None}

    def _cmd_mode(self, args: list[str], *, session_id: str | None = None) -> dict:
        handle = self._require_session(session_id)
        if not handle:
            return self._error("No active session")
        try:
            state = handle.session.coordinator.session_state
            current = state.get("active_mode")

            if not args or args[0] == "off":
                state["active_mode"] = None
                # B1: Flatten + type "mode" (frontend checks result.type === 'mode')
                return {"type": "mode", "active_mode": None, "previous_mode": current}

            mode_name = args[0]
            trailing_args = args[1:]
            trailing = None

            if trailing_args and trailing_args[-1] == "off":
                state["active_mode"] = None
                return {"type": "mode", "active_mode": None, "previous_mode": current}
            elif trailing_args and trailing_args[-1] != "on":
                trailing = " ".join(trailing_args)
            # if trailing_args == ["on"], trailing stays None

            # Toggle: if already active, deactivate
            if mode_name == current and trailing is None:
                state["active_mode"] = None
                return {"type": "mode", "active_mode": None, "previous_mode": current}

            # Validate mode exists
            discovery = state.get("mode_discovery")
            if discovery and not discovery.find(mode_name):
                avail = [n for n, _, _ in discovery.list_modes()]
                return {
                    "type": "error",
                    "error": f"Unknown mode: {mode_name}",
                    "available_modes": avail,
                }

            state["active_mode"] = mode_name
            result: dict = {
                "type": "mode",
                "active_mode": mode_name,
                "previous_mode": current,
            }
            if trailing:
                result["trailing_prompt"] = trailing
            return result
        except Exception as e:
            return self._error(f"Mode command failed: {e}")

    def _cmd_rename(self, args: list[str], *, session_id: str | None = None) -> dict:
        handle = self._require_session(session_id)
        if not handle:
            return self._error("No active session")
        name = " ".join(args) if args else "Untitled"
        # B1: Flatten
        return {"type": "renamed", "session_id": session_id, "name": name}

    def _cmd_fork(self, args: list[str], *, session_id: str | None = None) -> dict:
        handle = self._require_session(session_id)
        if not handle:
            return self._error("No active session")
        if not args:
            return {
                "type": "fork_info",
                "turn_count": handle.turn_count,
                "session_id": session_id,
            }
        try:
            turn = int(args[0])
        except ValueError:
            return self._error(f"Invalid turn number: {args[0]}")

        session_dir = self._find_session_dir(session_id)
        if not session_dir:
            return self._error(
                "Session directory not found on disk. "
                "Use the fork button on a message instead."
            )
        try:
            from amplifier_foundation.session import fork_session

            result = fork_session(session_dir, turn=turn)

            if result.session_dir:
                cwd = (
                    str(handle.working_dir)
                    if getattr(handle, "working_dir", None)
                    else None
                )
                patch_forked_metadata(result.session_dir, session_dir, cwd)

            return {
                "type": "forked",
                "session_id": result.session_id,
                "parent_id": result.parent_id,
                "forked_from_turn": result.forked_from_turn,
                "message_count": result.message_count,
            }
        except ImportError:
            return self._error("Fork unavailable (amplifier-foundation not installed)")
        except ValueError as e:
            return self._error(str(e))

    def _cmd_help(self, args: list[str], **_: Any) -> dict:
        # B1: Flatten
        return {
            "type": "help",
            "commands": [
                {
                    "name": f"/{c.name}",
                    "description": c.description,
                    "usage": c.usage,
                }
                for c in COMMANDS
            ],
        }

    def _cmd_voice(self, args: list[str], *, session_id: str | None = None) -> dict:
        """Voice feature info and settings."""
        try:
            from chat_plugin.voice import (
                DEFAULT_STT_MODEL,
                _models_dir,
                _tts_available,
                _whisper_available,
            )

            model_file = _models_dir() / f"ggml-{DEFAULT_STT_MODEL}.bin"
            return {
                "type": "voice",
                "stt_available": _whisper_available,
                "tts_available": _tts_available,
                "stt_model": DEFAULT_STT_MODEL,
                "stt_model_downloaded": model_file.exists(),
                "message": (
                    "Voice features: "
                    + (
                        "STT ready"
                        if _whisper_available and model_file.exists()
                        else "STT not ready"
                    )
                    + " | "
                    + ("TTS ready" if _tts_available else "TTS not ready")
                    + ". Install: uv sync --extra voice"
                ),
            }
        except ImportError:
            return {
                "type": "voice",
                "stt_available": False,
                "tts_available": False,
                "message": "Voice dependencies not installed. Run: uv sync --extra voice",
            }

    def _cmd_bundle(self, args: list[str], *, session_id: str | None = None) -> dict:
        # B4: Coming soon stub — bundle switching not yet implemented
        return {
            "type": "info",
            "message": (
                "Bundle switching is coming soon. "
                "Create a new session with the desired bundle instead."
            ),
        }
