import json
from unittest.mock import MagicMock

import pytest

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
    sessions, pinned, total = scan_sessions(None)
    assert sessions == []
    assert total == 0


def test_scan_sessions_empty_dir(tmp_path):
    sessions, pinned, total = scan_sessions(tmp_path)
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
    results, pinned, total = scan_sessions(tmp_path)
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
    results, pinned, total = scan_sessions(tmp_path)
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
    results, pinned, total = scan_sessions(tmp_path)
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
    page, pinned, total = scan_sessions(tmp_path, limit=2, offset=0)
    assert total == 3
    assert len(page) == 2
    assert page[0]["session_id"] == "sess-newest"
    assert page[1]["session_id"] == "sess-middle"

    # Second page: limit=2, offset=2 → 1 remaining session
    page2, _pinned2, total2 = scan_sessions(tmp_path, limit=2, offset=2)
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

    _, _pinned, total = scan_sessions(tmp_path)
    assert total == 3

    # Offset beyond all results still reports correct total
    page, _pinned3, total2 = scan_sessions(tmp_path, limit=10, offset=100)
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
    results, pinned, total = scan_sessions(tmp_path)
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
    results, pinned, total = scan_sessions(tmp_path)
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
    results, pinned, total = scan_sessions(tmp_path)
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
    results, pinned, total = scan_sessions(tmp_path)
    assert total == 1
    assert len(results) == 1
    assert results[0]["hidden"] is False


# ── pinned_ids ───────────────────────────────────────────────────────────────


def test_scan_session_revisions_excludes_hidden(tmp_path):
    """S-13: Hidden sessions must not appear in revision results."""
    _make_session(
        tmp_path,
        "visible-sess",
        transcript='{"role": "user", "content": "hi"}\n',
    )
    _make_session(
        tmp_path,
        "hidden-sess",
        transcript='{"role": "user", "content": "secret"}\n',
        metadata={"hidden": True},
    )
    rows = scan_session_revisions(tmp_path)
    ids = {r["session_id"] for r in rows}
    assert "visible-sess" in ids
    assert "hidden-sess" not in ids, (
        "Hidden sessions must be excluded from revision results"
    )


def test_scan_sessions_pinned_priority(tmp_path):
    """Pinned sessions are returned separately, outside the pagination window."""
    import time

    for name in ["sess-oldest", "sess-middle", "sess-newest"]:
        _make_session(
            tmp_path,
            name,
            transcript='{"role": "user", "content": "hi"}\n',
        )
        time.sleep(0.01)  # ensure distinct mtimes

    # Pin the oldest session, paginate with limit=1
    regular, pinned, total = scan_sessions(
        tmp_path, limit=1, offset=0, pinned_ids={"sess-oldest"}
    )

    # Pinned session is always returned regardless of pagination
    assert len(pinned) == 1
    assert pinned[0]["session_id"] == "sess-oldest"

    # Regular pagination: limit=1 returns only the most recent non-pinned
    assert len(regular) == 1
    assert regular[0]["session_id"] == "sess-newest"

    # total_count excludes pinned sessions
    assert total == 2


def test_scan_sessions_pinned_not_in_regular(tmp_path):
    """Pinned sessions do not appear in the regular results."""
    _make_session(
        tmp_path,
        "sess-a",
        transcript='{"role": "user", "content": "a"}\n',
    )
    _make_session(
        tmp_path,
        "sess-b",
        transcript='{"role": "user", "content": "b"}\n',
    )

    regular, pinned, total = scan_sessions(tmp_path, pinned_ids={"sess-a"})

    regular_ids = {r["session_id"] for r in regular}
    pinned_ids_set = {p["session_id"] for p in pinned}

    assert "sess-a" in pinned_ids_set
    assert "sess-a" not in regular_ids
    assert "sess-b" in regular_ids
    assert total == 1  # only non-pinned count


# ── SessionManager / SessionIndex integration ─────────────────────────────────
#
# These tests verify that register() and destroy() interact correctly with
# the SessionIndex.  They live here because list_sessions() merges active
# in-memory sessions with historical index entries – exactly what the
# session-history UI surfaces.
# ─────────────────────────────────────────────────────────────────────────────

from amplifierd.state.session_manager import SessionManager  # noqa: E402


def _make_sm_with_index(projects_dir):
    """Create a SessionManager backed by a real on-disk SessionIndex."""
    event_bus = MagicMock()
    settings = MagicMock()
    settings.default_bundle = None
    settings.default_working_dir = None
    return SessionManager(
        event_bus=event_bus,
        settings=settings,
        projects_dir=projects_dir,
    )


def _make_sm_session(session_id="sess-sm-001"):
    s = MagicMock()
    s.session_id = session_id
    s.parent_id = None
    return s


@pytest.mark.asyncio
async def test_list_sessions_active_takes_priority_over_historical(tmp_path):
    """Active in-memory sessions appear with is_active=True before historical entries."""
    manager = _make_sm_with_index(tmp_path)
    session = _make_sm_session("sess-active-hist-001")

    await manager.register(
        session=session,
        prepared_bundle=None,
        bundle_name="test-bundle",
    )

    sessions = manager.list_sessions()
    active = [s for s in sessions if s.get("is_active")]
    assert any(s["session_id"] == "sess-active-hist-001" for s in active), (
        "Registered session should appear as active"
    )


@pytest.mark.asyncio
async def test_register_adds_entry_to_index(tmp_path):
    """register() writes a SessionIndexEntry to the on-disk index."""
    manager = _make_sm_with_index(tmp_path)
    session = _make_sm_session("sess-idx-add-001")

    await manager.register(
        session=session,
        prepared_bundle=None,
        bundle_name="test-bundle",
        project_id="proj-test",
    )

    assert manager._index is not None
    entry = manager._index.get("sess-idx-add-001")
    assert entry is not None, "register() should add entry to index"
    assert entry.bundle == "test-bundle"


@pytest.mark.asyncio
async def test_destroy_updates_index_status(tmp_path):
    """destroy() marks the session as 'completed' in the index."""
    manager = _make_sm_with_index(tmp_path)
    session = _make_sm_session("sess-dest-idx-001")

    await manager.register(
        session=session,
        prepared_bundle=None,
        bundle_name="test-bundle",
        project_id="proj-test",
    )

    await manager.destroy("sess-dest-idx-001")

    assert manager._index is not None
    entry = manager._index.get("sess-dest-idx-001")
    assert entry is not None
    assert entry.status == "completed", (
        f"Expected 'completed', got {entry.status!r}"
    )
