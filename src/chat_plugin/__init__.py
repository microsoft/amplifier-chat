from __future__ import annotations

from typing import Any

from fastapi import APIRouter


def create_router(state: Any) -> APIRouter:
    """Plugin entry point. Called by amplifierd plugin discovery."""
    from chat_plugin.commands import CommandProcessor
    from chat_plugin.config import ChatPluginSettings
    from chat_plugin.pin_storage import PinStorage
    from chat_plugin.routes import (
        create_command_routes,
        create_config_routes,
        create_history_routes,
        create_pin_routes,
        create_static_routes,
    )

    settings = ChatPluginSettings()
    settings.home_dir.mkdir(parents=True, exist_ok=True)
    pin_storage = PinStorage(settings.home_dir / "pinned-sessions.json")
    processor = CommandProcessor(
        session_manager=state.session_manager, event_bus=state.event_bus
    )

    # Extract projects_dir from amplifierd settings (may be None)
    projects_dir = getattr(getattr(state, "settings", None), "projects_dir", None)

    # Extract distro home from distro plugin state (may be None).
    # The distro plugin sets state.distro = SimpleNamespace(settings=...)
    # where settings.distro_home is the path to ~/.amplifier-distro.
    distro_ns = getattr(state, "distro", None)
    distro_home = getattr(getattr(distro_ns, "settings", None), "distro_home", None)

    router = APIRouter()

    @router.get("/chat/health", tags=["chat"])
    async def chat_health():
        return {"status": "ok", "plugin": "chat"}

    router.include_router(create_config_routes(distro_home))
    router.include_router(create_pin_routes(pin_storage))
    router.include_router(create_history_routes(projects_dir, pin_storage))
    router.include_router(create_command_routes(processor))
    router.include_router(create_static_routes())
    return router
