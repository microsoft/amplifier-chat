import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from chat_plugin import create_router


class MockSettings:
    projects_dir = None


class MockState:
    session_manager = None
    event_bus = None
    bundle_registry = None
    settings = MockSettings()


@pytest.fixture
def state():
    return MockState()


@pytest.fixture
def app(state, tmp_path, monkeypatch):
    monkeypatch.setenv("CHAT_PLUGIN_HOME_DIR", str(tmp_path))
    app = FastAPI()
    app.state = state
    router = create_router(state)
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    return TestClient(app)
