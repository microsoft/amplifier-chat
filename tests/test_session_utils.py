"""Tests for shared session utilities."""

import json


def test_atomic_write_json(tmp_path):
    """S-15: atomic_write_json must use tmp+rename pattern."""
    from chat_plugin.session_utils import atomic_write_json

    target = tmp_path / "test.json"
    atomic_write_json(target, {"key": "value"})

    assert target.exists()
    data = json.loads(target.read_text())
    assert data == {"key": "value"}

    # No leftover .tmp files
    tmp_files = list(tmp_path.glob("*.tmp"))
    assert tmp_files == []


def test_atomic_write_json_creates_parent_dirs(tmp_path):
    """atomic_write_json should create parent directories if needed."""
    from chat_plugin.session_utils import atomic_write_json

    target = tmp_path / "nested" / "deep" / "test.json"
    atomic_write_json(target, {"nested": True})
    assert target.exists()


def test_patch_forked_metadata_sets_working_dir(tmp_path):
    """S-15: patch_forked_metadata should set working_dir from cwd param."""
    from chat_plugin.session_utils import patch_forked_metadata

    forked_dir = tmp_path / "forked"
    forked_dir.mkdir()
    (forked_dir / "metadata.json").write_text("{}")

    parent_dir = tmp_path / "parent"
    parent_dir.mkdir()
    (parent_dir / "metadata.json").write_text(
        json.dumps({"bundle": "test-bundle", "model": "gpt-4"})
    )

    patch_forked_metadata(forked_dir, parent_dir, cwd="/Users/test/project")

    meta = json.loads((forked_dir / "metadata.json").read_text())
    assert meta["working_dir"] == "/Users/test/project"
    assert meta["bundle"] == "test-bundle"
    assert meta["model"] == "gpt-4"


def test_patch_forked_metadata_falls_back_to_parent_cwd(tmp_path):
    """patch_forked_metadata should use parent's working_dir when cwd is None."""
    from chat_plugin.session_utils import patch_forked_metadata

    forked_dir = tmp_path / "forked"
    forked_dir.mkdir()
    (forked_dir / "metadata.json").write_text("{}")

    parent_dir = tmp_path / "parent"
    parent_dir.mkdir()
    (parent_dir / "metadata.json").write_text(
        json.dumps({"working_dir": "/parent/cwd"})
    )

    patch_forked_metadata(forked_dir, parent_dir, cwd=None)

    meta = json.loads((forked_dir / "metadata.json").read_text())
    assert meta["working_dir"] == "/parent/cwd"


def test_patch_forked_metadata_no_change_when_nothing_to_patch(tmp_path):
    """patch_forked_metadata should not write if nothing changed."""
    from chat_plugin.session_utils import patch_forked_metadata

    forked_dir = tmp_path / "forked"
    forked_dir.mkdir()
    (forked_dir / "metadata.json").write_text(
        json.dumps({"bundle": "existing", "model": "existing"})
    )

    parent_dir = tmp_path / "parent"
    parent_dir.mkdir()
    (parent_dir / "metadata.json").write_text("{}")

    mtime_before = (forked_dir / "metadata.json").stat().st_mtime_ns
    patch_forked_metadata(forked_dir, parent_dir, cwd=None)
    mtime_after = (forked_dir / "metadata.json").stat().st_mtime_ns

    assert mtime_before == mtime_after, (
        "File should not be rewritten when nothing changed"
    )
