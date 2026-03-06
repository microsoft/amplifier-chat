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
