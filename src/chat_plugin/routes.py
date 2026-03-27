from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, Response

from chat_plugin.commands import CommandProcessor
from chat_plugin.pin_storage import PinStorage
from chat_plugin.session_history import (
    VALID_SESSION_ID_RE,
    scan_session_revisions,
    scan_sessions,
    search_sessions,
)

STATIC_DIR = Path(__file__).parent / "static"


def _parse_session_id_set(values: list[str]) -> set[str]:
    """Validate session IDs and return a de-duplicated set."""
    out: set[str] = set()
    for raw in values:
        session_id = (raw or "").strip()
        if not session_id:
            continue
        if not VALID_SESSION_ID_RE.fullmatch(session_id):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid session ID format: {session_id!r}",
            )
        out.add(session_id)
    return out


def create_pin_routes(pin_storage: PinStorage) -> APIRouter:
    router = APIRouter(prefix="/chat", tags=["chat-pins"])

    @router.get("/pins")
    async def list_pins():
        return {"pinned": sorted(pin_storage.list_pins())}

    @router.post("/pins/{session_id}")
    async def pin_session(session_id: str):
        if not VALID_SESSION_ID_RE.fullmatch(session_id):
            raise HTTPException(status_code=400, detail="Invalid session ID")
        pin_storage.add(session_id)
        return {"pinned": True, "session_id": session_id}

    @router.delete("/pins/{session_id}")
    async def unpin_session(session_id: str):
        if not VALID_SESSION_ID_RE.fullmatch(session_id):
            raise HTTPException(status_code=400, detail="Invalid session ID")
        pin_storage.remove(session_id)
        return {"pinned": False, "session_id": session_id}

    # Distro-compatible paths under /chat/api/sessions/
    @router.get("/api/sessions/pins")
    async def list_pins_api():
        return {"pinned": sorted(pin_storage.list_pins())}

    @router.post("/api/sessions/{session_id}/pin")
    async def pin_session_api(session_id: str):
        if not VALID_SESSION_ID_RE.fullmatch(session_id):
            raise HTTPException(status_code=400, detail="Invalid session ID")
        pin_storage.add(session_id)
        return {"status": "pinned", "session_id": session_id}

    @router.delete("/api/sessions/{session_id}/pin")
    async def unpin_session_api(session_id: str):
        if not VALID_SESSION_ID_RE.fullmatch(session_id):
            raise HTTPException(status_code=400, detail="Invalid session ID")
        pin_storage.remove(session_id)
        return {"status": "unpinned", "session_id": session_id}

    return router


def create_history_routes(
    projects_dir: Path | None,
    pin_storage: PinStorage,
) -> APIRouter:
    router = APIRouter(prefix="/chat", tags=["chat-history"])

    @router.get("/api/sessions/history")
    async def list_session_history(
        limit: int = Query(default=200, ge=1, le=1000),
        offset: int = Query(default=0, ge=0),
    ) -> dict:
        """Return lightweight metadata for all sessions discovered on disk.

        scan_sessions() does a cheap mtime stat-sort first, then parallel
        full-reads of pinned sessions + the requested offset:offset+limit
        window of regular sessions.
        total_count reflects only non-pinned session directories before any
        caller-side content filtering.
        """
        pinned_ids = pin_storage.list_pins()
        sessions, pinned_sessions, total_count = await asyncio.to_thread(
            scan_sessions, projects_dir, limit, offset, pinned_ids=pinned_ids
        )

        # Content filter: only sessions with actual content, exclude hidden
        def _has_content(row: dict) -> bool:
            return (
                (row.get("message_count") or 0) > 0
                or bool(row.get("last_user_message"))
            ) and not row.get("hidden")

        sessions = [row for row in sessions if _has_content(row)]
        pinned_sessions = [row for row in pinned_sessions if _has_content(row)]

        for row in sessions:
            row["pinned"] = False
        for row in pinned_sessions:
            row["pinned"] = True

        return {
            "sessions": pinned_sessions + sessions,
            "total_count": total_count,
            "has_more": offset + limit < total_count,
            "pinned_count": len(pinned_sessions),
        }

    @router.get("/api/sessions/search")
    async def search_session_history(
        q: str = Query(default="", max_length=200),
        limit: int = Query(default=20, ge=1, le=100),
    ) -> dict:
        """Search all sessions on disk matching the query string."""
        results = await asyncio.to_thread(search_sessions, projects_dir, q, limit)

        def _has_content(row: dict) -> bool:
            return (
                (row.get("message_count") or 0) > 0
                or bool(row.get("last_user_message"))
            ) and not row.get("hidden")

        results = [row for row in results if _has_content(row)]
        return {"sessions": results, "query": q}

    @router.get("/api/sessions/revisions")
    async def list_session_revisions(
        limit: int = Query(default=300, ge=1, le=5000),
        session_ids: str | None = Query(default=None, max_length=20000),
    ) -> dict:
        """Return revision signatures for disk-backed sessions (legacy GET)."""
        wanted: set[str] | None = None
        if session_ids:
            wanted = _parse_session_id_set(session_ids.split(","))

        rows = await asyncio.to_thread(scan_session_revisions, projects_dir, wanted)
        return {"sessions": rows[:limit]}

    @router.post("/api/sessions/revisions")
    async def diff_session_revisions(request: Request) -> dict:
        """Return only changed/removed revisions vs client-known state."""
        raw = await request.body()
        if not raw:
            body: dict[str, Any] = {}
        else:
            try:
                body = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise HTTPException(
                    status_code=400,
                    detail="Request body must be valid JSON",
                ) from exc
            if not isinstance(body, dict):
                raise HTTPException(
                    status_code=400,
                    detail="Request body must be a JSON object",
                )

        raw_ids = body.get("session_ids")
        if raw_ids is None:
            wanted: set[str] | None = None
        elif isinstance(raw_ids, list):
            if not all(isinstance(v, str) for v in raw_ids):
                raise HTTPException(
                    status_code=400,
                    detail="'session_ids' must be a list of strings",
                )
            wanted = _parse_session_id_set(raw_ids)
        else:
            raise HTTPException(
                status_code=400,
                detail="'session_ids' must be a list of strings",
            )

        raw_known = body.get("known_revisions")
        known_revisions: dict[str, str | None] = {}
        if raw_known is not None:
            if not isinstance(raw_known, dict):
                raise HTTPException(
                    status_code=400,
                    detail="'known_revisions' must be an object",
                )
            for raw_sid, raw_rev in raw_known.items():
                if not isinstance(raw_sid, str):
                    raise HTTPException(
                        status_code=400,
                        detail="'known_revisions' keys must be strings",
                    )
                ids = _parse_session_id_set([raw_sid])
                if not ids:
                    continue
                sid = next(iter(ids))
                if raw_rev is not None and not isinstance(raw_rev, str):
                    raise HTTPException(
                        status_code=400,
                        detail="'known_revisions' values must be strings or null",
                    )
                known_revisions[sid] = raw_rev

        if wanted is None and known_revisions:
            wanted = set(known_revisions.keys())

        limit = body.get("limit", 300)
        if not isinstance(limit, int) or limit < 1 or limit > 5000:
            raise HTTPException(
                status_code=400,
                detail="'limit' must be an integer between 1 and 5000",
            )

        rows = await asyncio.to_thread(scan_session_revisions, projects_dir, wanted)
        found_ids = {row["session_id"] for row in rows}

        changed: list[dict[str, str]] = []
        for row in rows:
            sid = row["session_id"]
            known = known_revisions.get(sid)
            if sid not in known_revisions or known != row["revision"]:
                changed.append(row)
                if len(changed) >= limit:
                    break

        removed: list[str] = []
        if wanted is not None:
            removed = sorted(sid for sid in wanted if sid not in found_ids)[:limit]

        return {"changed": changed, "removed": removed}

    return router


_DEFAULT_DISTRO_HOME = Path.home() / ".amplifier-distro"


def _read_workspace_root(distro_home: Path) -> str | None:
    """Read ``workspace_root`` from the distro settings YAML, or *None*."""
    settings_file = distro_home / "settings.yaml"
    try:
        if settings_file.exists():
            import yaml

            raw = yaml.safe_load(settings_file.read_text())
            if isinstance(raw, dict):
                ws = raw.get("workspace_root", "")
                if isinstance(ws, str) and ws and ws != "~":
                    return ws
    except Exception:  # noqa: BLE001
        pass
    return None


def create_config_routes(distro_home: Path | None) -> APIRouter:
    """Expose plugin configuration to the frontend.

    Reads ``workspace_root`` from the distro settings YAML.  Tries the
    distro-plugin-provided home first, then falls back to the well-known
    default ``~/.amplifier-distro`` so the endpoint works even when the
    distro plugin is not installed.  The YAML is read at request time so
    wizard changes are picked up without a restart.
    """

    router = APIRouter(prefix="/chat", tags=["chat-config"])

    @router.get("/api/config")
    async def get_config() -> dict[str, str]:
        # Try distro-plugin-provided path first (respects env-var override),
        # then fall back to the well-known default location.
        ws = None
        if distro_home is not None:
            ws = _read_workspace_root(Path(distro_home))
        if ws is None:
            ws = _read_workspace_root(_DEFAULT_DISTRO_HOME)
        return {"default_cwd": ws or "~"}

    return router


def create_command_routes(processor: CommandProcessor) -> APIRouter:
    router = APIRouter(prefix="/chat", tags=["chat-commands"])

    @router.post("/command")
    async def dispatch_command(body: dict):
        session_id = body.get("session_id")
        if session_id is not None and not VALID_SESSION_ID_RE.fullmatch(session_id):
            raise HTTPException(status_code=400, detail="Invalid session ID")
        text = body.get("command", body.get("text", ""))
        action, data = processor.process_input(text)
        if action == "command":
            command = data["command"]
            args = data["args"]
            if command == "fork" and args:
                return await asyncio.to_thread(
                    processor.handle_command,
                    command,
                    args,
                    session_id=session_id,
                )
            return processor.handle_command(command, args, session_id=session_id)
        return {"type": "prompt", "data": data}

    return router


def create_fork_routes(
    session_manager: Any,
    projects_dir: Path | None,
) -> APIRouter:
    """Fork-from-message endpoints: preview + execute."""
    router = APIRouter(prefix="/chat", tags=["chat-fork"])

    def _patch_forked_metadata(
        forked_dir: Path,
        parent_dir: Path,
        cwd: str | None,
    ) -> None:
        """Patch the forked session's metadata.json with working_dir and
        any fields that fork_session() left as null (e.g. bundle)."""
        meta_path = forked_dir / "metadata.json"
        try:
            meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
        except (json.JSONDecodeError, OSError):
            meta = {}

        # Read parent metadata for fallback values
        parent_meta: dict = {}
        parent_meta_path = parent_dir / "metadata.json"
        try:
            parent_meta = json.loads(parent_meta_path.read_text())
        except (json.JSONDecodeError, OSError, FileNotFoundError):
            pass

        changed = False

        # Patch working_dir
        if not cwd:
            cwd = parent_meta.get("working_dir") or parent_meta.get("cwd")
        if cwd:
            meta["working_dir"] = cwd
            changed = True

        # Patch bundle if null (fork_session may have copied null from parent
        # if metadata was written before the daemon set the bundle field).
        if not meta.get("bundle") and parent_meta.get("bundle"):
            meta["bundle"] = parent_meta["bundle"]
            changed = True

        # Patch model if null
        if not meta.get("model") and parent_meta.get("model"):
            meta["model"] = parent_meta["model"]
            changed = True

        if changed:
            try:
                meta_path.write_text(json.dumps(meta, indent=2) + "\n")
            except OSError:
                pass  # best-effort

    def _find_session_dir(session_id: str) -> Path:
        if projects_dir is None:
            raise HTTPException(status_code=500, detail="projects_dir not configured")
        for project_dir in projects_dir.iterdir():
            if not project_dir.is_dir():
                continue
            candidate = project_dir / "sessions" / session_id
            if candidate.is_dir():
                return candidate
        raise HTTPException(
            status_code=404, detail=f"Session directory not found: {session_id}"
        )

    @router.get("/api/sessions/{session_id}/fork-preview")
    async def fork_preview(
        session_id: str,
        turn: int = Query(..., ge=1),
    ) -> dict:
        """Return a lightweight preview of what a fork at *turn* would produce."""
        if not VALID_SESSION_ID_RE.fullmatch(session_id):
            raise HTTPException(status_code=400, detail="Invalid session ID")
        session_dir = _find_session_dir(session_id)
        try:
            from amplifier_foundation.session import get_fork_preview

            preview = await asyncio.to_thread(get_fork_preview, session_dir, turn)
            return preview
        except ImportError:
            raise HTTPException(
                status_code=501,
                detail="Fork unavailable (amplifier-foundation not installed)",
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.post("/api/sessions/{session_id}/fork")
    async def do_fork_session(session_id: str, request: Request) -> dict:
        """Execute a fork at the given turn and return the new session info."""
        if not VALID_SESSION_ID_RE.fullmatch(session_id):
            raise HTTPException(status_code=400, detail="Invalid session ID")
        raw = await request.body()
        if not raw:
            raise HTTPException(status_code=400, detail="Request body required")
        try:
            body = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="Invalid JSON") from exc

        turn = body.get("turn")
        if turn is None or not isinstance(turn, int) or turn < 1:
            raise HTTPException(
                status_code=400, detail="'turn' must be a positive integer"
            )

        cwd = body.get("cwd")

        session_dir = _find_session_dir(session_id)
        try:
            from amplifier_foundation.session import fork_session

            result = await asyncio.to_thread(fork_session, session_dir, turn=turn)

            if result.session_dir:
                _patch_forked_metadata(result.session_dir, session_dir, cwd)

            return {
                "session_id": result.session_id,
                "session_dir": str(result.session_dir) if result.session_dir else None,
                "parent_id": result.parent_id,
                "forked_from_turn": result.forked_from_turn,
                "message_count": result.message_count,
                "events_count": getattr(result, "events_count", 0),
                "cwd": cwd,
            }
        except ImportError:
            raise HTTPException(
                status_code=501,
                detail="Fork unavailable (amplifier-foundation not installed)",
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    return router


def create_shell_routes(session_manager: Any) -> APIRouter:
    """User-initiated shell command execution via ! prefix."""
    from starlette.responses import StreamingResponse

    from chat_plugin.shell import execute_shell_command

    router = APIRouter(prefix="/chat", tags=["chat-shell"])

    @router.post("/api/sessions/{session_id}/shell")
    async def execute_shell(session_id: str, body: dict):
        if not VALID_SESSION_ID_RE.fullmatch(session_id):
            raise HTTPException(status_code=400, detail="Invalid session ID")
        command = body.get("command", "").strip()
        if not command:
            raise HTTPException(status_code=400, detail="Empty command")

        cwd = (body.get("cwd") or "").strip()
        if not cwd:
            raise HTTPException(status_code=400, detail="cwd is required")

        async def event_stream():
            async for event in execute_shell_command(command, cwd=cwd):
                yield event

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    return router


def create_static_routes() -> APIRouter:
    router = APIRouter(tags=["chat-static"])

    @router.get("/chat/")
    async def serve_spa(request: Request):
        # Serve loading screen while bundles are warming up
        bundles_ready = getattr(request.app.state, "bundles_ready", None)
        if bundles_ready and not bundles_ready.is_set():
            loading_path = STATIC_DIR / "loading.html"
            try:
                return Response(
                    content=loading_path.read_text(),
                    media_type="text/html",
                )
            except OSError:
                return Response(
                    content="<h1>Starting up&hellip;</h1><p>Preparing your environment.</p>",
                    media_type="text/html",
                    status_code=503,
                    headers={"Retry-After": "5"},
                )
        html = (STATIC_DIR / "index.html").read_text()
        return Response(content=html, media_type="text/html")

    @router.get("/chat/vendor.js")
    async def serve_vendor():
        js = (STATIC_DIR / "vendor.js").read_text()
        return Response(content=js, media_type="application/javascript")

    @router.get("/chat/feedback-widget.js")
    async def serve_feedback_widget():
        js = (STATIC_DIR / "feedback-widget.js").read_text()
        return Response(content=js, media_type="application/javascript")

    return router
