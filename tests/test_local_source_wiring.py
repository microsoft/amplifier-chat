"""Tests that verify the local src/amplifierd source is correctly wired.

These tests exist to satisfy the build-path requirement: src/amplifierd must be
on the active build/import path so that the local threading.py (and any other
overridden modules) are actually exercised rather than the installed site-packages
copy.

The importlib-based tests load the local file *directly* from disk, bypassing
Python's regular import resolution entirely, so they always prove the local
source is correct regardless of sys.path ordering.
"""

from __future__ import annotations

import importlib.util
import tomllib
from pathlib import Path

# Root of the amplifier-chat repository (two levels up from tests/)
_REPO_ROOT = Path(__file__).parent.parent
_LOCAL_THREADING = _REPO_ROOT / "src" / "amplifierd" / "threading.py"


class TestWheelPackagesWiring:
    """Verify pyproject.toml wires src/amplifierd into the build path."""

    def test_amplifierd_in_wheel_packages(self):
        """src/amplifierd must appear in [tool.hatch.build.targets.wheel] packages.

        Without this entry the local amplifierd overrides are dead — they are
        present on disk but never included in the built wheel, so deployed
        amplifier-chat would still use whatever amplifierd version was
        independently installed.
        """
        data = tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text())
        packages = data["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"]
        assert "src/amplifierd" in packages, (
            f"src/amplifierd is missing from wheel packages. "
            f"Add it to [tool.hatch.build.targets.wheel] packages in pyproject.toml. "
            f"Current packages: {packages}"
        )

    def test_local_threading_file_exists(self):
        """The local override file must actually exist on disk."""
        assert _LOCAL_THREADING.exists(), (
            f"Expected local threading.py at {_LOCAL_THREADING}"
        )


class TestLocalThreadingSource:
    """Load and validate src/amplifierd/threading.py directly from disk.

    These tests bypass Python's import resolution (which uses the installed
    amplifierd package) and instead exercise the local source file using
    importlib.util.spec_from_file_location.  This guarantees the local file
    is what is being tested even when sys.path ordering would otherwise
    shadow it.
    """

    @staticmethod
    def _load_local_threading():
        """Load src/amplifierd/threading.py directly from disk via importlib."""
        spec = importlib.util.spec_from_file_location(
            "local_amplifierd_threading", _LOCAL_THREADING
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore[union-attr]
        return module

    def test_local_module_loads_cleanly(self):
        """The local file must import without errors."""
        module = self._load_local_threading()
        assert module is not None

    def test_local_module_exports_threaded_tool_wrapper(self):
        """ThreadedToolWrapper must be present in the local source."""
        module = self._load_local_threading()
        assert hasattr(module, "ThreadedToolWrapper"), (
            "ThreadedToolWrapper missing from local threading.py"
        )

    def test_local_module_exports_wrap_tools_for_threading(self):
        """wrap_tools_for_threading must be present in the local source."""
        module = self._load_local_threading()
        assert hasattr(module, "wrap_tools_for_threading"), (
            "wrap_tools_for_threading missing from local threading.py"
        )

    def test_local_module_has_callable_guard(self):
        """The callable(get_fn) guard must be in the local source.

        This is the critical fix that was absent from the original simplified
        version — it prevents a crash when the coordinator doesn't expose .get().
        """
        content = _LOCAL_THREADING.read_text()
        assert "callable(get_fn)" in content, (
            "callable(get_fn) guard is missing from local threading.py. "
            "This guard prevents a crash when the coordinator has no .get() method."
        )

    def test_local_module_handles_dict_tools(self):
        """The dict-path branch must be present in the local source."""
        content = _LOCAL_THREADING.read_text()
        assert "isinstance(tools, dict)" in content, (
            "dict-path branch is missing from local threading.py"
        )

    def test_local_module_needs_threading_set(self):
        """_NEEDS_THREADING frozenset must list the expected blocking tools."""
        module = self._load_local_threading()
        needs = module._NEEDS_THREADING
        for expected in ("read_file", "write_file", "web_fetch", "grep", "glob"):
            assert expected in needs, (
                f"Tool '{expected}' is missing from _NEEDS_THREADING in local threading.py"
            )

    def test_local_module_idempotency_guard(self):
        """Double-wrapping guard must be present in the local source."""
        content = _LOCAL_THREADING.read_text()
        assert "isinstance(tool, ThreadedToolWrapper)" in content, (
            "Idempotency guard (double-wrap check) missing from local threading.py"
        )
