from fastapi import FastAPI
from fastapi.routing import APIRoute, APIRouter


def test_create_router_returns_api_router():
    from chat_plugin import create_router

    app = FastAPI()
    app.state.session_manager = None
    app.state.event_bus = None
    app.state.bundle_registry = None
    app.state.settings = None
    router = create_router(app.state)
    assert isinstance(router, APIRouter)


def test_plugin_routes_registered():
    from chat_plugin import create_router

    app = FastAPI()
    app.state.session_manager = None
    app.state.event_bus = None
    app.state.bundle_registry = None
    app.state.settings = None
    router = create_router(app.state)
    paths = [r.path for r in router.routes if isinstance(r, APIRoute)]
    assert "/chat/" in paths or any("/chat" in p for p in paths)


def test_standalone_registers_overlay_bundle(tmp_path, monkeypatch):
    """When distro plugin is absent and overlay bundle.yaml exists,
    create_router() registers it in the bundle_registry."""
    from pathlib import Path
    from unittest.mock import MagicMock

    from chat_plugin import create_router

    # Create fake ~/.amplifier-distro/bundle/bundle.yaml
    fake_home = tmp_path / "home"
    overlay_dir = fake_home / ".amplifier-distro" / "bundle"
    overlay_dir.mkdir(parents=True)
    (overlay_dir / "bundle.yaml").write_text("name: test\n")

    monkeypatch.setenv("CHAT_PLUGIN_HOME_DIR", str(tmp_path / "chat"))
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))

    mock_registry = MagicMock()

    app = FastAPI()
    app.state.session_manager = None
    app.state.event_bus = None
    app.state.bundle_registry = mock_registry
    app.state.settings = None

    create_router(app.state)

    mock_registry.register.assert_called_once_with({"distro": str(overlay_dir)})


def test_standalone_skips_when_no_overlay(tmp_path, monkeypatch):
    """When overlay bundle.yaml does not exist, create_router() does not
    call bundle_registry.register()."""
    from pathlib import Path
    from unittest.mock import MagicMock

    from chat_plugin import create_router

    fake_home = tmp_path / "home"
    fake_home.mkdir()

    monkeypatch.setenv("CHAT_PLUGIN_HOME_DIR", str(tmp_path / "chat"))
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))

    mock_registry = MagicMock()

    app = FastAPI()
    app.state.session_manager = None
    app.state.event_bus = None
    app.state.bundle_registry = mock_registry
    app.state.settings = None

    create_router(app.state)

    mock_registry.register.assert_not_called()


def test_distro_plugin_present_skips_overlay(tmp_path, monkeypatch):
    """When distro plugin already loaded (state.distro set), the standalone
    overlay registration is bypassed even if bundle.yaml exists."""
    from pathlib import Path
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from chat_plugin import create_router

    fake_home = tmp_path / "home"
    overlay_dir = fake_home / ".amplifier-distro" / "bundle"
    overlay_dir.mkdir(parents=True)
    (overlay_dir / "bundle.yaml").write_text("name: test\n")

    monkeypatch.setenv("CHAT_PLUGIN_HOME_DIR", str(tmp_path / "chat"))
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))

    mock_registry = MagicMock()

    app = FastAPI()
    app.state.session_manager = None
    app.state.event_bus = None
    app.state.bundle_registry = mock_registry
    app.state.settings = None
    app.state.distro = SimpleNamespace(
        settings=SimpleNamespace(distro_home="/some/path")
    )

    create_router(app.state)

    mock_registry.register.assert_not_called()
