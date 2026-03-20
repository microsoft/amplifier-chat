from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi.responses import RedirectResponse


def create_router(state: Any) -> APIRouter:
    """Plugin entry point. Called by amplifierd plugin discovery."""
    import os

    from chat_plugin.commands import CommandProcessor
    from chat_plugin.config import ChatPluginSettings
    from chat_plugin.feedback import create_feedback_routes
    from chat_plugin.pin_storage import PinStorage
    from chat_plugin.routes import (
        create_command_routes,
        create_config_routes,
        create_fork_routes,
        create_history_routes,
        create_pin_routes,
        create_static_routes,
    )

    settings = ChatPluginSettings()
    settings.home_dir.mkdir(parents=True, exist_ok=True)
    pin_storage = PinStorage(settings.home_dir / "pinned-sessions.json")

    # Extract projects_dir from amplifierd settings (may be None)
    projects_dir = getattr(getattr(state, "settings", None), "projects_dir", None)

    processor = CommandProcessor(
        session_manager=state.session_manager,
        event_bus=state.event_bus,
        projects_dir=projects_dir,
    )

    # Extract distro home from distro plugin state (may be None).
    # The distro plugin sets state.distro = SimpleNamespace(settings=...)
    # where settings.distro_home is the path to ~/.amplifier-distro.
    distro_ns = getattr(state, "distro", None)
    distro_home = getattr(getattr(distro_ns, "settings", None), "distro_home", None)

    # When running standalone (without the distro plugin), register the
    # overlay bundle so that amplifierd's built-in prewarm warms the user's
    # customized bundle instead of the raw upstream from GitHub.
    if distro_ns is None:
        bundle_registry = getattr(state, "bundle_registry", None)
        if bundle_registry:
            default_distro_home = Path.home() / ".amplifier-distro"
            overlay_yaml = default_distro_home / "bundle" / "bundle.yaml"
            if overlay_yaml.exists():
                distro_home = str(default_distro_home)
                bundle_registry.register({"distro": str(overlay_yaml.parent)})

    router = APIRouter()

    @router.get("/chat/health", tags=["chat"])
    async def chat_health():
        return {"status": "ok", "plugin": "chat"}

    # Daemon session path for server-log analysis (may be None)
    daemon_session_path = os.environ.get("AMPLIFIERD_DAEMON_SESSION_PATH")

    # When no distro plugin owns the root path, redirect / → /chat/
    if distro_ns is None:

        @router.get("/", include_in_schema=False)
        async def root_redirect():
            return RedirectResponse(url="/chat/")

    router.include_router(create_config_routes(distro_home))
    router.include_router(create_pin_routes(pin_storage))
    router.include_router(create_history_routes(projects_dir, pin_storage))
    router.include_router(create_command_routes(processor))
    router.include_router(create_fork_routes(state.session_manager, projects_dir))
    router.include_router(create_feedback_routes(projects_dir, daemon_session_path))
    from chat_plugin.voice import create_voice_routes

    router.include_router(create_voice_routes())
    router.include_router(create_static_routes())
    return router
