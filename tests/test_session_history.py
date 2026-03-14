import json

from chat_plugin.session_history import scan_session_revisions, scan_sessions


# ── helpers ──────────────────────────────────────────────────────────────────


def _make_session(
    projects_dir, session_id, slug="-Users-test", transcript=None, metadata=None
):
    """Create a session in the two-level projects/{slug}/sessions/{id}/ layout."""
    session_dir = projects_dir / slug / "sessions" / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    if transcript is not None:
        (session_dir / "transcript.jsonl").write_text(transcript, encoding="utf-8")
    if metadata is not None:
        (session_dir / "metadata.json").write_text(
            json.dumps(metadata), encoding="utf-8"
        )
    return session_dir


# ── basic coverage ────────────────────────────────────────────────────────────


def test_scan_sessions_none_dir():
    sessions, total = scan_sessions(None)
    assert sessions == []
    assert total == 0


def test_scan_sessions_empty_dir(tmp_path):
    sessions, total = scan_sessions(tmp_path)
    assert sessions == []
    assert total == 0


def test_scan_sessions_with_transcript(tmp_path):
    _make_session(
        tmp_path,
        "sess-abc",
        transcript=(
            json.dumps({"role": "user", "content": "Hello"})
            + "\n"
            + json.dumps({"role": "assistant", "content": "Hi"})
            + "\n"
        ),
    )
    results, total = scan_sessions(tmp_path)
    assert total == 1
    assert len(results) == 1
    row = results[0]
    assert row["session_id"] == "sess-abc"
    assert row["message_count"] == 2
    assert row["last_user_message"] == "Hello"
    assert row["revision"]  # non-empty


def test_scan_sessions_with_metadata(tmp_path):
    _make_session(
        tmp_path,
        "sess-xyz",
        transcript=json.dumps({"role": "user", "content": "test"}) + "\n",
        metadata={
            "name": "My Session",
            "description": "A test session",
            "parent_id": "sess-parent",
        },
    )
    results, total = scan_sessions(tmp_path)
    assert total == 1
    assert len(results) == 1
    row = results[0]
    assert row["name"] == "My Session"
    assert row["description"] == "A test session"
    assert row["parent_session_id"] == "sess-parent"


def test_scan_session_revisions(tmp_path):
    _make_session(
        tmp_path,
        "sess-rev",
        transcript=json.dumps({"role": "user", "content": "hi"}) + "\n",
    )
    rows = scan_session_revisions(tmp_path)
    assert len(rows) == 1
    assert rows[0]["session_id"] == "sess-rev"
    assert "revision" in rows[0]
    assert "last_updated" in rows[0]


def test_scan_session_revisions_filter(tmp_path):
    for name in ["sess-a", "sess-b", "sess-c"]:
        _make_session(tmp_path, name, transcript="{}\n")
    rows = scan_session_revisions(tmp_path, session_ids={"sess-b"})
    assert len(rows) == 1
    assert rows[0]["session_id"] == "sess-b"


def test_scan_session_revisions_none_dir():
    assert scan_session_revisions(None) == []


def test_invalid_session_ids_skipped(tmp_path):
    _make_session(tmp_path, "valid-id", transcript="{}\n")
    # Create malformed dirs directly — they sit at the sessions/ level
    bad_sessions = tmp_path / "-Users-test" / "sessions"
    (bad_sessions / ".hidden").mkdir()
    (bad_sessions / "has spaces").mkdir()
    results, total = scan_sessions(tmp_path)
    session_ids = {r["session_id"] for r in results}
    assert "valid-id" in session_ids
    assert ".hidden" not in session_ids
    assert "has spaces" not in session_ids


def test_scan_sessions_pagination(tmp_path):
    """Phase-1 mtime sort + windowed read: offset/limit respected."""
    import time

    for name in ["sess-oldest", "sess-middle", "sess-newest"]:
        _make_session(
            tmp_path,
            name,
            transcript='{"role": "user", "content": "hi"}\n',
        )
        time.sleep(0.01)  # ensure distinct mtimes

    # First page: limit=2, offset=0 → 2 most-recent sessions
    page, total = scan_sessions(tmp_path, limit=2, offset=0)
    assert total == 3
    assert len(page) == 2
    assert page[0]["session_id"] == "sess-newest"
    assert page[1]["session_id"] == "sess-middle"

    # Second page: limit=2, offset=2 → 1 remaining session
    page2, total2 = scan_sessions(tmp_path, limit=2, offset=2)
    assert total2 == 3
    assert len(page2) == 1
    assert page2[0]["session_id"] == "sess-oldest"


def test_scan_sessions_total_count(tmp_path):
    """total_count equals the number of valid session directories."""
    for name in ["sess-a", "sess-b", "sess-c"]:
        _make_session(
            tmp_path,
            name,
            transcript='{"role": "user", "content": "x"}\n',
        )

    _, total = scan_sessions(tmp_path)
    assert total == 3

    # Offset beyond all results still reports correct total
    page, total2 = scan_sessions(tmp_path, limit=10, offset=100)
    assert total2 == 3
    assert page == []


def test_scan_sessions_cwd_from_slug(tmp_path):
    """CWD is decoded from project slug when session-info.json is absent."""
    _make_session(
        tmp_path,
        "sess-cwd",
        slug="-Users-test-myproject",
        transcript='{"role": "user", "content": "cwd test"}\n',
    )
    results, total = scan_sessions(tmp_path)
    assert total == 1
    row = results[0]
    # Naive fallback: -Users-test-myproject → /Users/test/myproject (or longer match)
    assert row["cwd"] is not None
    assert row["cwd"].startswith("/")


def test_scan_sessions_multiple_projects(tmp_path):
    """Sessions from different project slugs are all returned."""
    _make_session(
        tmp_path,
        "sess-1",
        slug="-Users-alice-projA",
        transcript='{"role": "user", "content": "a"}\n',
    )
    _make_session(
        tmp_path,
        "sess-2",
        slug="-Users-bob-projB",
        transcript='{"role": "user", "content": "b"}\n',
    )
    results, total = scan_sessions(tmp_path)
    assert total == 2
    ids = {r["session_id"] for r in results}
    assert ids == {"sess-1", "sess-2"}


def test_scan_sessions_hidden_flag(tmp_path):
    """Sessions with hidden: true in metadata surface the flag."""
    _make_session(
        tmp_path,
        "sess-hidden",
        transcript='{"role": "user", "content": "secret"}\n',
        metadata={"hidden": True},
    )
    results, total = scan_sessions(tmp_path)
    assert total == 1
    assert len(results) == 1
    assert results[0]["hidden"] is True


def test_scan_sessions_not_hidden_by_default(tmp_path):
    """Sessions without hidden metadata default to False."""
    _make_session(
        tmp_path,
        "sess-normal",
        transcript='{"role": "user", "content": "hello"}\n',
    )
    results, total = scan_sessions(tmp_path)
    assert total == 1
    assert len(results) == 1
    assert results[0]["hidden"] is False


# ── ensure_ids ───────────────────────────────────────────────────────────────


def test_scan_sessions_ensure_ids_outside_window(tmp_path):
    """ensure_ids pulls sessions from outside the pagination window."""
    import time

    for name in ["sess-oldest", "sess-middle", "sess-newest"]:
        _make_session(
            tmp_path,
            name,
            transcript='{"role": "user", "content": "hi"}\n',
        )
        time.sleep(0.01)

    # Page of 2 would normally exclude sess-oldest (position 3).
    # ensure_ids forces it into the results.
    page, total = scan_sessions(tmp_path, limit=2, offset=0, ensure_ids={"sess-oldest"})
    assert total == 3
    ids = {r["session_id"] for r in page}
    assert "sess-oldest" in ids
    assert "sess-newest" in ids
    assert "sess-middle" in ids
    assert len(page) == 3  # 2 windowed + 1 ensured


def test_scan_sessions_ensure_ids_already_in_window(tmp_path):
    """ensure_ids does not duplicate sessions already in the window."""
    import time

    for name in ["sess-a", "sess-b"]:
        _make_session(
            tmp_path,
            name,
            transcript='{"role": "user", "content": "hi"}\n',
        )
        time.sleep(0.01)

    page, total = scan_sessions(tmp_path, limit=10, offset=0, ensure_ids={"sess-b"})
    assert total == 2
    assert len(page) == 2  # no duplication
    ids = [r["session_id"] for r in page]
    assert ids.count("sess-b") == 1


def test_scan_sessions_ensure_ids_nonexistent(tmp_path):
    """ensure_ids silently ignores IDs that don't exist on disk."""
    _make_session(
        tmp_path,
        "sess-real",
        transcript='{"role": "user", "content": "hi"}\n',
    )
    page, total = scan_sessions(tmp_path, limit=10, offset=0, ensure_ids={"sess-ghost"})
    assert total == 1
    assert len(page) == 1
    assert page[0]["session_id"] == "sess-real"


def test_scan_sessions_ensure_ids_empty_set(tmp_path):
    """An empty ensure_ids set behaves like None."""
    _make_session(
        tmp_path,
        "sess-only",
        transcript='{"role": "user", "content": "hi"}\n',
    )
    page, total = scan_sessions(tmp_path, limit=10, offset=0, ensure_ids=set())
    assert total == 1
    assert len(page) == 1
