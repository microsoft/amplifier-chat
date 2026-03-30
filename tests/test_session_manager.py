"""Tests for SessionManager.create() — session_cwd, prepared-bundle cache,
and tool-wrapping integration.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amplifierd.state.session_manager import SessionManager


# ---------------------------------------------------------------------------
# Helpers / Fakes
# ---------------------------------------------------------------------------


def _make_fake_session(session_id: str = "sess-001") -> MagicMock:
    session = MagicMock()
    session.session_id = session_id
    session.parent_id = None
    return session


def _make_prepared(session: MagicMock | None = None) -> MagicMock:
    if session is None:
        session = _make_fake_session()
    prepared = MagicMock()
    prepared.create_session = AsyncMock(return_value=session)
    return prepared


def _make_session_manager(*, projects_dir: Path | None = None) -> SessionManager:
    event_bus = MagicMock()
    settings = MagicMock()
    settings.default_bundle = None
    settings.default_working_dir = None
    # bundle_registry must be truthy for create() to not raise
    bundle_registry = MagicMock()
    return SessionManager(
        event_bus=event_bus,
        settings=settings,
        bundle_registry=bundle_registry,
        projects_dir=projects_dir,
    )


# ---------------------------------------------------------------------------
# TestCreatePassesSessionCwd
# ---------------------------------------------------------------------------


class TestCreatePassesSessionCwd:
    """create() must forward the resolved working_dir as session_cwd=Path(wd)."""

    @pytest.mark.asyncio
    async def test_create_passes_session_cwd_to_create_session(self, tmp_path):
        """session_cwd is Path(wd) where wd comes from resolve_working_dir."""
        sm = _make_session_manager()
        session = _make_fake_session()
        prepared = _make_prepared(session)

        # Pre-warm the cache so we skip the bundle-registry slow path.
        sm.set_prepared_bundle("my-bundle", prepared)

        with (
            patch(
                "amplifierd.spawn.register_spawn_capability", side_effect=ImportError
            ),
            patch("amplifierd.threading.wrap_tools_for_threading"),
        ):
            handle = await sm.create(
                bundle_name="my-bundle",
                working_dir=str(tmp_path),
            )

        prepared.create_session.assert_called_once_with(session_cwd=tmp_path)
        assert handle.session_id == session.session_id

    @pytest.mark.asyncio
    async def test_create_expands_tilde_in_working_dir(self):
        """resolve_working_dir expands ~ to the absolute home path."""
        sm = _make_session_manager()
        session = _make_fake_session()
        prepared = _make_prepared(session)
        sm.set_prepared_bundle("my-bundle", prepared)

        with (
            patch(
                "amplifierd.spawn.register_spawn_capability", side_effect=ImportError
            ),
            patch("amplifierd.threading.wrap_tools_for_threading"),
        ):
            await sm.create(bundle_name="my-bundle", working_dir="~/some/dir")

        call_kwargs = prepared.create_session.call_args.kwargs
        assert "~" not in str(call_kwargs["session_cwd"])


# ---------------------------------------------------------------------------
# TestSessionManagerPreparedBundleCache
# ---------------------------------------------------------------------------


class TestSessionManagerPreparedBundleCache:
    """The prepared-bundle cache (set_prepared_bundle) is used as fast path."""

    @pytest.mark.asyncio
    async def test_cached_prepared_bundle_is_used(self):
        """When a PreparedBundle is pre-warmed, create() skips bundle_registry.load()."""
        sm = _make_session_manager()
        session = _make_fake_session()
        prepared = _make_prepared(session)
        sm.set_prepared_bundle("my-bundle", prepared)

        with (
            patch(
                "amplifierd.spawn.register_spawn_capability", side_effect=ImportError
            ),
            patch("amplifierd.threading.wrap_tools_for_threading"),
        ):
            handle = await sm.create(bundle_name="my-bundle")

        # The injected mock bundle_registry.load should NOT have been called
        sm._bundle_registry.load.assert_not_called()
        prepared.create_session.assert_called_once()
        assert handle.session_id == session.session_id

    @pytest.mark.asyncio
    async def test_clear_prepared_bundle_forces_slow_path(self):
        """After clear_prepared_bundle(), the fast path is bypassed."""
        sm = _make_session_manager()
        session = _make_fake_session()
        prepared = _make_prepared(session)
        sm.set_prepared_bundle("my-bundle", prepared)
        sm.clear_prepared_bundle("my-bundle")

        # Now the slow path will run → need a real bundle_registry mock.
        bundle = MagicMock()
        bundle.prepare = AsyncMock(return_value=prepared)
        registry = MagicMock()
        registry.load = AsyncMock(return_value=bundle)
        sm._bundle_registry = registry

        with (
            patch("amplifierd.providers.load_provider_config", return_value=[]),
            patch("amplifierd.providers.inject_providers"),
            patch(
                "amplifierd.spawn.register_spawn_capability", side_effect=ImportError
            ),
            patch("amplifierd.threading.wrap_tools_for_threading"),
        ):
            handle = await sm.create(bundle_name="my-bundle")

        registry.load.assert_called_once_with("my-bundle")
        assert handle.session_id == session.session_id


# ---------------------------------------------------------------------------
# TestWrapToolsForThreadingCalledInCreate
# ---------------------------------------------------------------------------


class TestWrapToolsForThreadingCalledInCreate:
    """wrap_tools_for_threading(session) is called immediately after create_session."""

    @pytest.mark.asyncio
    async def test_wrap_tools_called_with_session(self):
        """create() calls wrap_tools_for_threading(session) after create_session."""
        sm = _make_session_manager()
        session = _make_fake_session()
        prepared = _make_prepared(session)
        sm.set_prepared_bundle("my-bundle", prepared)

        with (
            patch(
                "amplifierd.spawn.register_spawn_capability", side_effect=ImportError
            ),
            patch("amplifierd.threading.wrap_tools_for_threading") as mock_wrap,
        ):
            await sm.create(bundle_name="my-bundle")

        mock_wrap.assert_called_once_with(session)

    @pytest.mark.asyncio
    async def test_wrap_tools_called_before_register(self):
        """wrap_tools_for_threading is called before register() so the handle has wrapped tools."""
        sm = _make_session_manager()
        session = _make_fake_session()
        prepared = _make_prepared(session)
        sm.set_prepared_bundle("my-bundle", prepared)

        call_order: list[str] = []

        def record_wrap(s):
            call_order.append("wrap")

        original_register = sm.register

        def record_register(**kwargs):
            call_order.append("register")
            return original_register(**kwargs)

        sm.register = record_register  # type: ignore[method-assign]

        with (
            patch(
                "amplifierd.spawn.register_spawn_capability", side_effect=ImportError
            ),
            patch(
                "amplifierd.threading.wrap_tools_for_threading", side_effect=record_wrap
            ),
        ):
            await sm.create(bundle_name="my-bundle")

        assert "wrap" in call_order, "wrap_tools_for_threading was never called"
        assert call_order.index("wrap") < call_order.index("register"), (
            "wrap_tools_for_threading must be called before register()"
        )


# ---------------------------------------------------------------------------
# TestResumePassesSessionCwd
# ---------------------------------------------------------------------------


class TestResumePassesSessionCwd:
    """resume() must call wrap_tools_for_threading(session) after create_session."""

    @staticmethod
    async def _fake_to_thread(fn, *args, **kwargs):
        """Drop-in replacement for asyncio.to_thread that calls fn synchronously."""
        return fn(*args, **kwargs)

    @pytest.mark.asyncio
    async def test_resume_calls_wrap_tools_for_threading(self, tmp_path):
        """resume() calls wrap_tools_for_threading(session) after create_session."""
        sm = _make_session_manager(projects_dir=tmp_path)
        session = _make_fake_session("sess-resume-001")
        # Ensure coordinator.get returns None so context-injection block is skipped
        session.coordinator.get.return_value = None
        prepared = _make_prepared(session)
        sm.set_prepared_bundle("my-bundle", prepared)

        session_dir = tmp_path / "proj" / "sessions" / "sess-resume-001"
        session_dir.mkdir(parents=True)

        working_dir = str(tmp_path / "work")

        with (
            patch.object(sm, "_find_session_dir", return_value=session_dir),
            patch("amplifierd.persistence.load_transcript", return_value=[]),
            patch(
                "amplifierd.persistence.load_metadata",
                return_value={"bundle": "my-bundle", "working_dir": working_dir},
            ),
            patch("asyncio.to_thread", new=self._fake_to_thread),
            patch("amplifierd.persistence.register_persistence_hooks"),
            patch(
                "amplifierd.spawn.register_spawn_capability", side_effect=ImportError
            ),
            patch("amplifierd.threading.wrap_tools_for_threading") as mock_wrap,
        ):
            handle = await sm.resume("sess-resume-001")

        mock_wrap.assert_called_once_with(session)
        assert handle.session_id == session.session_id


# ---------------------------------------------------------------------------
# TestRegisterAsync - tests that register() is async and works correctly
# ---------------------------------------------------------------------------


class TestRegisterAsync:
    """register() must be async so index.save() can be offloaded to a thread."""

    @pytest.mark.asyncio
    async def test_register_and_get(self):
        """register() is async: returns SessionHandle retrievable via get()."""
        manager = _make_session_manager()
        session = _make_fake_session("sess-reg-001")

        handle = await manager.register(
            session=session,
            prepared_bundle=None,
            bundle_name="test-bundle",
        )

        assert handle.session_id == "sess-reg-001"
        assert manager.get("sess-reg-001") is handle

    @pytest.mark.asyncio
    async def test_destroy(self):
        """destroy() removes session from registry; register() must be awaited first."""
        manager = _make_session_manager()
        session = _make_fake_session("sess-dest-001")

        await manager.register(
            session=session,
            prepared_bundle=None,
            bundle_name="test-bundle",
        )
        assert manager.get("sess-dest-001") is not None

        await manager.destroy("sess-dest-001")
        assert manager.get("sess-dest-001") is None

    @pytest.mark.asyncio
    async def test_list_sessions(self):
        """list_sessions() returns all registered sessions after await register()."""
        manager = _make_session_manager()
        session1 = _make_fake_session("sess-list-001")
        session2 = _make_fake_session("sess-list-002")

        await manager.register(
            session=session1, prepared_bundle=None, bundle_name="bundle-a"
        )
        await manager.register(
            session=session2, prepared_bundle=None, bundle_name="bundle-b"
        )

        sessions = manager.list_sessions()
        ids = {s["session_id"] for s in sessions}
        assert "sess-list-001" in ids
        assert "sess-list-002" in ids


# ---------------------------------------------------------------------------
# TestLoadProviderConfigUsesAsyncioToThread
# ---------------------------------------------------------------------------


class TestLoadProviderConfigUsesAsyncioToThread:
    """load_provider_config() must be called via asyncio.to_thread in create() and resume()."""

    @pytest.mark.asyncio
    async def test_create_uses_to_thread_for_load_provider_config(self):
        """create() must call asyncio.to_thread(load_provider_config) on the slow path."""
        sm = _make_session_manager()
        session = _make_fake_session()
        prepared = _make_prepared(session)

        # Force the slow path by NOT pre-warming the bundle cache
        bundle = MagicMock()
        bundle.prepare = AsyncMock(return_value=prepared)
        registry = MagicMock()
        registry.load = AsyncMock(return_value=bundle)
        sm._bundle_registry = registry

        # Capture actual callables passed to asyncio.to_thread
        to_thread_callables = []

        async def tracking(fn, *args, **kwargs):
            to_thread_callables.append(fn)
            return fn(*args, **kwargs)

        with (
            patch("asyncio.to_thread", new=tracking),
            patch(
                "amplifierd.providers.load_provider_config", return_value=[]
            ) as mock_lpc,
            patch("amplifierd.providers.inject_providers"),
            patch(
                "amplifierd.spawn.register_spawn_capability", side_effect=ImportError
            ),
            patch("amplifierd.threading.wrap_tools_for_threading"),
        ):
            await sm.create(bundle_name="my-bundle")

        assert mock_lpc in to_thread_callables, (
            "create() must call asyncio.to_thread(load_provider_config), not call it directly"
        )

    @pytest.mark.asyncio
    async def test_resume_uses_to_thread_for_load_provider_config(self, tmp_path):
        """resume() must call asyncio.to_thread(load_provider_config) on the slow path."""
        sm = _make_session_manager(projects_dir=tmp_path)
        session = _make_fake_session("sess-resume-tothread-001")
        session.coordinator.get.return_value = None
        prepared = _make_prepared(session)

        # Force the slow path by NOT pre-warming the bundle cache
        bundle = MagicMock()
        bundle.prepare = AsyncMock(return_value=prepared)
        registry = MagicMock()
        registry.load = AsyncMock(return_value=bundle)
        sm._bundle_registry = registry

        session_dir = tmp_path / "proj" / "sessions" / "sess-resume-tothread-001"
        session_dir.mkdir(parents=True)
        working_dir = str(tmp_path / "work")

        # Capture actual callables passed to asyncio.to_thread
        to_thread_callables = []

        async def tracking(fn, *args, **kwargs):
            to_thread_callables.append(fn)
            return fn(*args, **kwargs)

        with (
            patch.object(sm, "_find_session_dir", return_value=session_dir),
            patch("amplifierd.persistence.load_transcript", return_value=[]),
            patch(
                "amplifierd.persistence.load_metadata",
                return_value={"bundle": "my-bundle", "working_dir": working_dir},
            ),
            patch("asyncio.to_thread", new=tracking),
            patch(
                "amplifierd.providers.load_provider_config", return_value=[]
            ) as mock_lpc,
            patch("amplifierd.providers.inject_providers"),
            patch("amplifierd.persistence.register_persistence_hooks"),
            patch(
                "amplifierd.spawn.register_spawn_capability", side_effect=ImportError
            ),
            patch("amplifierd.threading.wrap_tools_for_threading"),
        ):
            await sm.resume("sess-resume-tothread-001")

        assert mock_lpc in to_thread_callables, (
            "resume() must call asyncio.to_thread(load_provider_config), not call it directly"
        )
