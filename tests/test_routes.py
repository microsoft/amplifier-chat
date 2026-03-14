def test_get_pins_empty(client):
    resp = client.get("/chat/pins")
    assert resp.status_code == 200
    assert resp.json() == {"pinned": []}


def test_pin_session(client):
    resp = client.post("/chat/pins/session-abc")
    assert resp.status_code == 200
    resp = client.get("/chat/pins")
    assert "session-abc" in resp.json()["pinned"]


def test_unpin_session(client):
    client.post("/chat/pins/session-abc")
    resp = client.delete("/chat/pins/session-abc")
    assert resp.status_code == 200
    resp = client.get("/chat/pins")
    assert "session-abc" not in resp.json()["pinned"]


def test_serve_spa(client):
    resp = client.get("/chat/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


def test_serve_vendor_js(client):
    resp = client.get("/chat/vendor.js")
    assert resp.status_code == 200
    assert "javascript" in resp.headers["content-type"]


def test_history_endpoint(client):
    resp = client.get("/chat/api/sessions/history")
    assert resp.status_code == 200
    data = resp.json()
    assert "sessions" in data
    assert isinstance(data["sessions"], list)
    # Pagination metadata
    assert "total_count" in data
    assert "has_more" in data
    assert isinstance(data["total_count"], int)
    assert isinstance(data["has_more"], bool)


def test_revisions_get(client):
    resp = client.get("/chat/api/sessions/revisions")
    assert resp.status_code == 200
    data = resp.json()
    assert "sessions" in data


def test_revisions_post_diff(client):
    resp = client.post(
        "/chat/api/sessions/revisions",
        json={
            "session_ids": [],
            "known_revisions": {},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "changed" in data
    assert "removed" in data


def test_api_pins_endpoint(client):
    resp = client.get("/chat/api/sessions/pins")
    assert resp.status_code == 200
    assert "pinned" in resp.json()


def test_api_pin_and_unpin(client):
    resp = client.post("/chat/api/sessions/test-session/pin")
    assert resp.status_code == 200
    assert resp.json()["status"] == "pinned"

    resp = client.get("/chat/api/sessions/pins")
    assert "test-session" in resp.json()["pinned"]

    resp = client.delete("/chat/api/sessions/test-session/pin")
    assert resp.status_code == 200
    assert resp.json()["status"] == "unpinned"


def test_history_with_sessions_on_disk(client, tmp_path, state):
    import json

    # Two-level layout: projects/{slug}/sessions/{id}/
    state.settings.projects_dir = tmp_path
    sess_dir = tmp_path / "-Users-test" / "sessions" / "my-session"
    sess_dir.mkdir(parents=True)
    (sess_dir / "transcript.jsonl").write_text(
        json.dumps({"role": "user", "content": "hello"}) + "\n",
        encoding="utf-8",
    )
    # Re-create app with projects_dir set
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from chat_plugin import create_router

    app = FastAPI()
    router = create_router(state)
    app.include_router(router)
    c = TestClient(app)

    resp = c.get("/chat/api/sessions/history")
    assert resp.status_code == 200
    data = resp.json()
    ids = [s["session_id"] for s in data["sessions"]]
    assert "my-session" in ids
    assert "total_count" in data


def test_history_returns_pinned_sessions_beyond_page(client, tmp_path, state):
    """Pinned sessions outside the pagination window are still returned."""
    import json
    import time

    state.settings.projects_dir = tmp_path

    # Create 3 sessions with distinct mtimes
    for name in ["sess-oldest", "sess-middle", "sess-newest"]:
        sess_dir = tmp_path / "-Users-test" / "sessions" / name
        sess_dir.mkdir(parents=True, exist_ok=True)
        (sess_dir / "transcript.jsonl").write_text(
            json.dumps({"role": "user", "content": "hi"}) + "\n",
            encoding="utf-8",
        )
        time.sleep(0.01)

    # Re-create app with projects_dir set
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from chat_plugin import create_router

    app = FastAPI()
    router = create_router(state)
    app.include_router(router)
    c = TestClient(app)

    # Pin the oldest session
    c.post("/chat/api/sessions/sess-oldest/pin")

    # Request only 2 sessions (page 1) — sess-oldest would normally be excluded
    resp = c.get("/chat/api/sessions/history?limit=2&offset=0")
    assert resp.status_code == 200
    data = resp.json()
    ids = [s["session_id"] for s in data["sessions"]]
    assert "sess-oldest" in ids  # pulled in by ensure_ids
    assert "sess-newest" in ids

    # Verify the pinned flag is set
    pinned_row = next(s for s in data["sessions"] if s["session_id"] == "sess-oldest")
    assert pinned_row["pinned"] is True


def test_history_no_ensure_ids_on_later_pages(client, tmp_path, state):
    """ensure_ids only applies on offset=0 to avoid pagination drift."""
    import json
    import time

    state.settings.projects_dir = tmp_path

    for name in ["sess-a", "sess-b", "sess-c"]:
        sess_dir = tmp_path / "-Users-test" / "sessions" / name
        sess_dir.mkdir(parents=True, exist_ok=True)
        (sess_dir / "transcript.jsonl").write_text(
            json.dumps({"role": "user", "content": "hi"}) + "\n",
            encoding="utf-8",
        )
        time.sleep(0.01)

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from chat_plugin import create_router

    app = FastAPI()
    router = create_router(state)
    app.include_router(router)
    c = TestClient(app)

    # Pin sess-a (oldest)
    c.post("/chat/api/sessions/sess-a/pin")

    # Page 2 (offset=2) should NOT inject pinned sessions
    resp = c.get("/chat/api/sessions/history?limit=2&offset=2")
    assert resp.status_code == 200
    data = resp.json()
    # Page 2 should only contain whatever falls naturally at offset 2.
    # Pinned session should NOT be injected on later pages.
    assert len(data["sessions"]) <= 1


def test_hidden_sessions_excluded_from_history(client, tmp_path, state):
    import json

    state.settings.projects_dir = tmp_path

    # Create a normal session with content
    normal_dir = tmp_path / "-Users-test" / "sessions" / "normal-session"
    normal_dir.mkdir(parents=True)
    (normal_dir / "transcript.jsonl").write_text(
        json.dumps({"role": "user", "content": "visible"}) + "\n",
        encoding="utf-8",
    )

    # Create a hidden session with content and hidden metadata
    hidden_dir = tmp_path / "-Users-test" / "sessions" / "hidden-session"
    hidden_dir.mkdir(parents=True)
    (hidden_dir / "transcript.jsonl").write_text(
        json.dumps({"role": "user", "content": "secret"}) + "\n",
        encoding="utf-8",
    )
    (hidden_dir / "metadata.json").write_text(
        json.dumps({"hidden": True}),
        encoding="utf-8",
    )

    # Re-create app with projects_dir set
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from chat_plugin import create_router

    app = FastAPI()
    router = create_router(state)
    app.include_router(router)
    c = TestClient(app)

    resp = c.get("/chat/api/sessions/history")
    assert resp.status_code == 200
    data = resp.json()
    ids = [s["session_id"] for s in data["sessions"]]
    assert "normal-session" in ids
    assert "hidden-session" not in ids
