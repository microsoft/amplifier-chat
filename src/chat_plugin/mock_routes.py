"""Mock amplifierd routes for the standalone dev server.

These stubs implement the subset of the amplifierd REST API that the chat
UI needs so you can iterate on the frontend without a running daemon.

Endpoints provided:
    POST   /sessions                           – create a mock session
    GET    /sessions                           – list mock sessions
    GET    /sessions/{id}                      – get session details
    POST   /sessions/{id}/execute/stream       – run a prompt (SSE via /events)
    POST   /sessions/{id}/resume               – resume a paused session
    POST   /sessions/{id}/cancel               – cancel execution
    GET    /sessions/{id}/transcript           – session transcript
    POST   /sessions/{id}/approvals/{req_id}   – approve/deny a pending request
    GET    /events                             – SSE event stream
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any

from fastapi import APIRouter, Request
from starlette.responses import StreamingResponse

# ---------------------------------------------------------------------------
# In-memory state (lives for the lifetime of the dev-server process)
# ---------------------------------------------------------------------------

_sessions: dict[str, dict[str, Any]] = {}
# One asyncio.Queue per session; items are pre-formatted SSE strings.
_queues: dict[str, asyncio.Queue] = {}


def _get_or_create_queue(session_id: str) -> asyncio.Queue:
    if session_id not in _queues:
        _queues[session_id] = asyncio.Queue()
    return _queues[session_id]


# ---------------------------------------------------------------------------
# SSE helpers
# ---------------------------------------------------------------------------


def _sse(event_name: str, payload: dict, session_id: str) -> str:
    """Serialize one SSE event in the amplifierd envelope format."""
    envelope = {"data": payload, "session_id": session_id}
    return f"event: {event_name}\ndata: {json.dumps(envelope)}\n\n"


async def _emit_mock_turn(session_id: str, prompt: str) -> None:
    """Emit a realistic sequence of mock SSE events for one user turn."""
    queue = _get_or_create_queue(session_id)

    await asyncio.sleep(0.3)

    # --- execution start ---
    await queue.put(_sse("execution:start", {}, session_id))
    await asyncio.sleep(0.1)

    # --- streamed assistant text ---
    response = f"Mock response to: {prompt}"
    words = response.split()

    await queue.put(_sse("content_block:start", {"index": 0}, session_id))
    for word in words:
        await queue.put(
            _sse("content_block:delta", {"index": 0, "delta": word + " "}, session_id)
        )
        await asyncio.sleep(0.04)
    await queue.put(
        _sse("content_block:end", {"index": 0, "text": response}, session_id)
    )
    await asyncio.sleep(0.1)

    # --- token usage (this is what drives the TokenUsagePill) ---
    input_tokens = max(50, len(prompt.split()) * 3)
    output_tokens = max(20, len(words) * 2)
    await queue.put(
        _sse(
            "llm:response",
            {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
                "cache_read_tokens": 0,
                "cache_write_tokens": 0,
                "model": "claude-sonnet-4-5",
                "provider": "anthropic",
            },
            session_id,
        )
    )

    # --- execution end then prompt complete ---
    await queue.put(_sse("execution:end", {}, session_id))
    await asyncio.sleep(0.05)
    await queue.put(_sse("orchestrator:complete", {}, session_id))

    # Update mock session status back to idle
    if session_id in _sessions:
        _sessions[session_id]["status"] = "idle"


# ---------------------------------------------------------------------------
# Router factory
# ---------------------------------------------------------------------------


def create_mock_amplifierd_routes() -> APIRouter:
    """Return an APIRouter with mock amplifierd endpoints."""

    router = APIRouter(tags=["mock-amplifierd"])

    # ------------------------------------------------------------------
    # Sessions CRUD
    # ------------------------------------------------------------------

    @router.post("/sessions")
    async def create_session(request: Request) -> dict:
        body: dict = {}
        try:
            body = await request.json()
        except Exception:
            pass
        session_id = uuid.uuid4().hex[:16]
        cwd = body.get("cwd") or "~"
        bundle = body.get("bundle") or "foundation"
        session = {
            "session_id": session_id,
            "cwd": cwd,
            "bundle": bundle,
            "status": "idle",
            "source": "live",
            "created_at": time.time(),
            "updated_at": time.time(),
            "message_count": 0,
            "last_user_message": None,
        }
        _sessions[session_id] = session
        _get_or_create_queue(session_id)
        return session

    @router.get("/sessions")
    async def list_sessions() -> dict:
        return {"sessions": list(_sessions.values())}

    @router.get("/sessions/{session_id}")
    async def get_session(session_id: str) -> dict:
        if session_id in _sessions:
            return _sessions[session_id]
        # Return a minimal stub so the UI doesn't crash on unknown IDs.
        return {
            "session_id": session_id,
            "cwd": "~",
            "bundle": "foundation",
            "status": "idle",
            "source": "live",
            "created_at": time.time(),
            "updated_at": time.time(),
            "message_count": 0,
            "last_user_message": None,
        }

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    @router.post("/sessions/{session_id}/execute/stream")
    async def execute_stream(session_id: str, request: Request) -> dict:
        body: dict = {}
        try:
            body = await request.json()
        except Exception:
            pass
        prompt = body.get("prompt") or ""

        # Update mock session state
        if session_id in _sessions:
            _sessions[session_id]["status"] = "running"
            _sessions[session_id]["message_count"] = (
                _sessions[session_id].get("message_count", 0) + 1
            )
            _sessions[session_id]["last_user_message"] = prompt[:120]
            _sessions[session_id]["updated_at"] = time.time()

        # Fire-and-forget: emit events on the SSE channel
        asyncio.create_task(_emit_mock_turn(session_id, prompt))

        return {"status": "started", "session_id": session_id}

    @router.post("/sessions/{session_id}/resume")
    async def resume_session(session_id: str, request: Request) -> dict:
        body: dict = {}
        try:
            body = await request.json()
        except Exception:
            pass
        prompt = body.get("prompt") or ""
        if session_id in _sessions:
            _sessions[session_id]["status"] = "running"
        asyncio.create_task(_emit_mock_turn(session_id, prompt))
        return {"status": "started", "session_id": session_id}

    @router.post("/sessions/{session_id}/cancel")
    async def cancel_session(session_id: str) -> dict:
        if session_id in _sessions:
            _sessions[session_id]["status"] = "idle"
        return {"status": "cancelled", "session_id": session_id}

    # ------------------------------------------------------------------
    # Transcript
    # ------------------------------------------------------------------

    @router.get("/sessions/{session_id}/transcript")
    async def get_transcript(session_id: str) -> dict:
        return {"turns": [], "session_id": session_id}

    # ------------------------------------------------------------------
    # Approvals
    # ------------------------------------------------------------------

    @router.post("/sessions/{session_id}/approvals/{request_id}")
    async def respond_approval(
        session_id: str, request_id: str, request: Request
    ) -> dict:
        return {"status": "ok"}

    # ------------------------------------------------------------------
    # SSE event stream  (/events?session=<id>)
    # ------------------------------------------------------------------

    @router.get("/events")
    async def sse_events(session: str | None = None) -> StreamingResponse:
        session_id = session
        queue = _get_or_create_queue(session_id) if session_id else None

        async def event_generator():
            # Send an initial keepalive so the browser confirms the connection.
            yield ": connected\n\n"
            if queue is None:
                while True:
                    await asyncio.sleep(20)
                    yield ": keepalive\n\n"
            else:
                while True:
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=20.0)
                        yield event
                    except asyncio.TimeoutError:
                        yield ": keepalive\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    return router
