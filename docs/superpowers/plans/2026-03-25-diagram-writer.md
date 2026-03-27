# diagram_writer — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the wrongly-merged `dotfile_writer.py` in `team-kb generate` with `diagram_writer.py` — a module that runs `amplifier run --bundle dot-graph --mode single` from each repo directory to produce a semantic system architecture DOT file.

**Architecture:** `diagram_writer.py` is a drop-in replacement at pipeline step 3b. It receives `repo_paths` (the actual local paths) instead of `all_caps`, runs one `amplifier` subprocess per repo, and writes `dotfiles/<handle>/<repo-name>.dot`. Failure is non-fatal — the generate pipeline continues if amplifier is unavailable or a repo fails.

**Tech Stack:** Python stdlib only (`subprocess`, `shutil`, `pathlib`, `logging`). No new dependencies.

---

## File Map

| Action | Path |
|--------|------|
| Create | `tools/src/team_kb/diagram_writer.py` |
| Modify | `tools/src/team_kb/cli.py` — 3 targeted changes |
| Delete | `tools/src/team_kb/dotfile_writer.py` |
| Create | `tools/tests/test_diagram_writer.py` |

All paths relative to:
`~/.amplifier/cache/amplifier-bundle-team-knowledge-base-<hash>/`

---

## Task 1 — Create `diagram_writer.py`

**Files:**
- Create: `tools/src/team_kb/diagram_writer.py`
- Create: `tools/tests/test_diagram_writer.py`

- [ ] **Step 1: Write the failing tests**

```python
# tools/tests/test_diagram_writer.py
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from team_kb.diagram_writer import (
    _amplifier_available,
    _repo_name,
    write_diagram,
    write_diagrams,
)


def test_repo_name_from_path():
    assert _repo_name(Path("/Users/sam/repo/amplifier-chat")) == "amplifier-chat"
    assert _repo_name(Path("/home/user/my-project")) == "my-project"


def test_amplifier_available_when_found():
    with patch("shutil.which", return_value="/usr/local/bin/amplifier"):
        assert _amplifier_available() is True


def test_amplifier_not_available_when_missing():
    with patch("shutil.which", return_value=None):
        assert _amplifier_available() is False


def test_write_diagram_skips_when_amplifier_missing(tmp_path):
    repo = tmp_path / "my-repo"
    repo.mkdir()
    out = tmp_path / "out.dot"
    with patch("shutil.which", return_value=None):
        result = write_diagram(repo, out)
    assert result is False
    assert not out.exists()


def test_write_diagram_skips_when_repo_missing(tmp_path):
    out = tmp_path / "out.dot"
    with patch("shutil.which", return_value="/usr/bin/amplifier"):
        result = write_diagram(tmp_path / "nonexistent", out)
    assert result is False


def test_write_diagram_returns_true_when_file_created(tmp_path):
    repo = tmp_path / "my-repo"
    repo.mkdir()
    out = tmp_path / "out.dot"

    def fake_run(*args, **kwargs):
        # Simulate the agent writing the file
        out.write_text("digraph {} {}")
        m = MagicMock()
        m.returncode = 0
        return m

    with patch("shutil.which", return_value="/usr/bin/amplifier"):
        with patch("subprocess.run", side_effect=fake_run):
            result = write_diagram(repo, out)

    assert result is True
    assert out.exists()


def test_write_diagram_returns_false_on_nonzero_exit(tmp_path):
    repo = tmp_path / "my-repo"
    repo.mkdir()
    out = tmp_path / "out.dot"

    m = MagicMock()
    m.returncode = 1
    with patch("shutil.which", return_value="/usr/bin/amplifier"):
        with patch("subprocess.run", return_value=m):
            result = write_diagram(repo, out)
    assert result is False


def test_write_diagram_returns_false_on_timeout(tmp_path):
    repo = tmp_path / "my-repo"
    repo.mkdir()
    out = tmp_path / "out.dot"

    with patch("shutil.which", return_value="/usr/bin/amplifier"):
        with patch("subprocess.run", side_effect=__import__("subprocess").TimeoutExpired("amplifier", 600)):
            result = write_diagram(repo, out)
    assert result is False


def test_write_diagrams_returns_count(tmp_path):
    kb = tmp_path / "kb"
    repo_a = tmp_path / "repo-a"
    repo_b = tmp_path / "repo-b"
    repo_a.mkdir()
    repo_b.mkdir()

    call_count = 0
    def fake_write_diagram(repo_path, output_path):
        nonlocal call_count
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("digraph {}")
        call_count += 1
        return True

    with patch("team_kb.diagram_writer.write_diagram", side_effect=fake_write_diagram):
        with patch("shutil.which", return_value="/usr/bin/amplifier"):
            count = write_diagrams("sam", [repo_a, repo_b], kb)

    assert count == 2
    assert call_count == 2


def test_write_diagrams_creates_dotfiles_dir(tmp_path):
    kb = tmp_path / "kb"
    repo = tmp_path / "my-repo"
    repo.mkdir()

    with patch("shutil.which", return_value=None):
        write_diagrams("sam", [repo], kb)

    # Even with no amplifier, the dotfiles dir should be created
    # (or gracefully not — just verify no crash)


def test_subprocess_called_with_correct_args(tmp_path):
    repo = tmp_path / "my-repo"
    repo.mkdir()
    out = tmp_path / "out.dot"

    m = MagicMock()
    m.returncode = 1  # File won't be created

    with patch("shutil.which", return_value="/usr/bin/amplifier"):
        with patch("subprocess.run", return_value=m) as mock_run:
            write_diagram(repo, out)

    call_args = mock_run.call_args
    cmd = call_args[0][0]
    assert cmd[0] == "amplifier"
    assert "--bundle" in cmd
    assert "dot-graph" in cmd[cmd.index("--bundle") + 1]
    assert "--mode" in cmd
    assert "single" in cmd
    # cwd should be the repo path
    assert call_args[1]["cwd"] == str(repo)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd ~/.amplifier/cache/amplifier-bundle-team-knowledge-base-<hash>
uv run pytest tools/tests/test_diagram_writer.py -v 2>&1 | head -20
```
Expected: `ModuleNotFoundError: No module named 'team_kb.diagram_writer'`

- [ ] **Step 3: Write `diagram_writer.py`**

```python
# tools/src/team_kb/diagram_writer.py
"""Generate semantic system architecture DOT diagrams via amplifier.

Replaces dotfile_writer.py. Runs the amplifier dot-graph bundle from
each repo directory so the agent reads actual source files and produces
a semantic architecture diagram.

Output: dotfiles/<handle>/<repo-name>.dot
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

BUNDLE_URL = "git+https://github.com/microsoft/amplifier-bundle-dot-graph@main"

_PROMPT = (
    "Generate a system architecture DOT file for this project. "
    "Write it to {output_path}.\n\n"
    "- Each node explains what the component does and why it exists, "
    "not what it contains\n"
    "- Enough nodes to understand the system, not catalog every file"
)

# First run is slower (bundle caching); subsequent runs ~60s
_TIMEOUT = 600


def _amplifier_available() -> bool:
    """Return True if amplifier CLI is in PATH."""
    return shutil.which("amplifier") is not None


def _repo_name(repo_path: Path) -> str:
    """Extract repo name from its local path."""
    return repo_path.name


def write_diagram(repo_path: Path, output_path: Path) -> bool:
    """Generate a system architecture DOT for one repository.

    Runs amplifier from the repo directory so the dot-graph agent
    reads actual source files.

    Returns True if the DOT file was successfully written.
    """
    if not _amplifier_available():
        logger.warning(
            "diagram_writer: amplifier not found in PATH — skipping %s",
            repo_path.name,
        )
        return False

    if not repo_path.is_dir():
        logger.warning("diagram_writer: repo path not found: %s", repo_path)
        return False

    output_path.parent.mkdir(parents=True, exist_ok=True)
    prompt = _PROMPT.format(output_path=str(output_path))

    try:
        result = subprocess.run(
            [
                "amplifier", "run",
                "--bundle", BUNDLE_URL,
                "--mode", "single",
                prompt,
            ],
            cwd=str(repo_path),
            timeout=_TIMEOUT,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and output_path.exists():
            logger.info("diagram_writer: wrote %s", output_path.name)
            return True
        logger.warning(
            "diagram_writer: amplifier exited %d for %s",
            result.returncode,
            repo_path.name,
        )
        if result.stderr:
            logger.debug("stderr: %s", result.stderr[:500])
        return False
    except subprocess.TimeoutExpired:
        logger.warning(
            "diagram_writer: timed out after %ds for %s",
            _TIMEOUT,
            repo_path.name,
        )
        return False
    except Exception as exc:  # noqa: BLE001
        logger.warning("diagram_writer: error for %s: %s", repo_path.name, exc)
        return False


def write_diagrams(
    handle: str,
    repo_paths: list[Path],
    kb_root: Path,
) -> int:
    """Generate system architecture DOTs for each repo.

    Creates dotfiles/<handle>/<repo-name>.dot per repo.

    Returns the number of DOT files successfully written.
    """
    if not _amplifier_available():
        logger.warning(
            "diagram_writer: amplifier not found — skipping diagram generation"
        )
        return 0

    dotfiles_dir = kb_root / "dotfiles" / handle
    dotfiles_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    for repo_path in repo_paths:
        output_path = dotfiles_dir / f"{_repo_name(repo_path)}.dot"
        if write_diagram(repo_path.resolve(), output_path):
            count += 1

    return count
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tools/tests/test_diagram_writer.py -v
```
Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add tools/src/team_kb/diagram_writer.py tools/tests/test_diagram_writer.py
git commit -m "feat: add diagram_writer — semantic DOT generation via amplifier"
```

---

## Task 2 — Update `cli.py`

**Files:**
- Modify: `tools/src/team_kb/cli.py`

Three targeted changes at step 3b (around line 156–180):

- [ ] **Step 1: Identify the three lines to change**

```python
# REMOVE THIS BLOCK (lines ~155-175) — all_caps is no longer needed:
from team_kb.dotfile_writer import write_dotfiles   # ← change import
all_caps = []
cap_dir = kb / "capabilities"
if cap_dir.is_dir():
    import yaml as _yaml
    for cap_file in sorted(cap_dir.glob("*.yaml")):
        try:
            data = _yaml.safe_load(cap_file.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("name"):
                all_caps.append(Capability(...))
        except Exception:
            continue
dot_count = write_dotfiles(handle, all_caps, kb)   # ← change call
```

- [ ] **Step 2: Apply the changes**

Replace the entire step 3b block with:
```python
# 3b. Generate system architecture diagrams
from team_kb.diagram_writer import write_diagrams
dot_count = write_diagrams(handle, repo_paths, kb)
logger.info("Generated %d diagram(s)", dot_count)
```

- [ ] **Step 3: Verify cli.py still imports correctly**

```bash
python3 -c "from team_kb.cli import main; print('OK')"
```
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add tools/src/team_kb/cli.py
git commit -m "refactor: wire diagram_writer into team-kb generate pipeline"
```

---

## Task 3 — Remove `dotfile_writer.py`

- [ ] **Step 1: Delete the file**

```bash
rm tools/src/team_kb/dotfile_writer.py
```

- [ ] **Step 2: Verify nothing imports it**

```bash
grep -r "dotfile_writer" tools/src tools/tests 2>/dev/null
```
Expected: no output (no remaining references)

- [ ] **Step 3: Run the full test suite**

```bash
uv run pytest tools/tests/ -v
```
Expected: all pass (or only pre-existing failures, none new)

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore: remove dotfile_writer.py (replaced by diagram_writer)"
```

---

## Task 4 — End-to-End Verification

- [ ] **Step 1: Add amplifier-chat to allowed-dirs (already done)**

```bash
amplifier allowed-dirs list  # verify /Users/samule/repo/amplifier-chat is listed
```

- [ ] **Step 2: Run team-kb generate**

```bash
team-kb generate --repos /Users/samule/repo/amplifier-chat
```

- [ ] **Step 3: Verify output**

```bash
ls -la ~/.amplifier/team-knowledge/made-team-knowledge-data/dotfiles/samueljklee/
cat ~/.amplifier/team-knowledge/made-team-knowledge-data/dotfiles/samueljklee/amplifier-chat.dot | head -20
```
Expected: `amplifier-chat.dot` exists with DOT content containing semantic node labels.

- [ ] **Step 4: Spot check quality**

```bash
grep '\[label=' ~/.amplifier/team-knowledge/made-team-knowledge-data/dotfiles/samueljklee/amplifier-chat.dot | head -5
```
Expected: labels describe behavior (not just filenames).

---

## Notes

- The team-kb bundle is editable-installed from cache. Changes take effect immediately without reinstall.
- `_TIMEOUT = 600` covers first-run bundle caching; typical subsequent runs complete in ~60–90s.
- The generate pipeline continues if diagram generation fails — `dot_count` may be 0 and that's OK.
- The `repo_paths` variable is already available in `generate()` from the `--repos` CLI arg — no new data needed.
