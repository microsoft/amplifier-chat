"""Feedback analysis endpoint.

Creates a hidden analysis session, kicks off an analysis prompt via the
daemon's streaming execution endpoint, and returns the analysis_session_id
immediately so the UI can poll for results.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class AnalyzeRequest(BaseModel):
    session_id: str


class AnalyzeResponse(BaseModel):
    analysis_session_id: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_transcript_path(projects_dir: Path | None, session_id: str) -> Path | None:
    """Search across all project slugs for a session's transcript.jsonl."""
    if projects_dir is None:
        return None
    if not projects_dir.is_dir():
        return None
    for slug_dir in projects_dir.iterdir():
        if not slug_dir.is_dir():
            continue
        transcript = slug_dir / "sessions" / session_id / "transcript.jsonl"
        if transcript.exists():
            return transcript
    return None


def _build_analysis_prompt(
    session_id: str,
    transcript_path: Path,
    daemon_session_path: str | None,
) -> str:
    """Build the analysis prompt with two tasks.

    TASK 1: search GitHub for related issues using ``gh issue list``.
    TASK 2: analyse the session transcript and server logs.
    """
    output_schema = json.dumps(
        {
            "source": {
                "github": {"issues": [{"number": "int", "title": "str", "url": "str"}]},
                "session": {
                    "session_id": "str",
                    "summary": "str",
                    "key_errors": ["str"],
                },
                "server_log": {"errors": [{"timestamp": "str", "message": "str"}]},
            }
        },
        indent=2,
    )

    parts: list[str] = [
        f"Analyse feedback for session {session_id}.\n",
        "TASK 1 — GitHub issue search",
        "Run: gh issue list --search '<keywords from transcript>' --json number,title,url",
        f"Transcript path: {transcript_path}\n",
        "TASK 2 — Session & server-log analysis",
        f"Session transcript: {transcript_path}",
    ]
    if daemon_session_path:
        parts.append(f"Server log: {daemon_session_path}")
    parts.append(f"\nReturn results as JSON matching this schema:\n{output_schema}")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Async helpers (mockable)
# ---------------------------------------------------------------------------

_BASE_URL_DEFAULT = "http://127.0.0.1:8080"


async def _create_analysis_session(base_url: str = _BASE_URL_DEFAULT) -> str:
    """Create a new session via POST /sessions and return its ID."""
    logger.info("[feedback-analysis] Creating analysis session via %s", base_url)
    async with httpx.AsyncClient(base_url=base_url, timeout=30) as client:
        resp = await client.post("/sessions", json={})
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        sid = data["session_id"]
        logger.info("[feedback-analysis] Analysis session created: %s", sid)
        return sid


async def _mark_session_hidden(base_url: str, session_id: str) -> None:
    """Mark a session as hidden via PATCH /sessions/{id}/metadata.

    Best-effort: if the session directory doesn't exist on disk yet (404),
    we log a warning and continue. The session will still work; it just
    won't be hidden from the history sidebar until metadata is written.
    """
    logger.info("[feedback-analysis] Marking session %s as hidden", session_id)
    async with httpx.AsyncClient(base_url=base_url, timeout=30) as client:
        resp = await client.patch(
            f"/sessions/{session_id}/metadata",
            json={"hidden": True},
        )
        if resp.status_code == 404:
            logger.warning(
                "[feedback-analysis] Session dir not yet on disk for %s; "
                "hidden flag skipped (best-effort)",
                session_id,
            )
            return
        resp.raise_for_status()
        logger.info("[feedback-analysis] Session %s marked hidden", session_id)


async def _kick_off_execution(base_url: str, session_id: str, prompt: str) -> None:
    """Fire-and-forget: consume the SSE stream so the analysis runs."""
    logger.info(
        "[feedback-analysis] Starting execution for session %s (prompt length: %d)",
        session_id,
        len(prompt),
    )
    async with httpx.AsyncClient(base_url=base_url, timeout=600) as client:
        async with client.stream(
            "POST",
            f"/sessions/{session_id}/execute/stream",
            json={"prompt": prompt},
        ) as resp:
            resp.raise_for_status()
            logger.info(
                "[feedback-analysis] SSE stream connected for session %s, consuming...",
                session_id,
            )
            chunk_count = 0
            async for _chunk in resp.aiter_bytes():
                chunk_count += 1
            logger.info(
                "[feedback-analysis] Execution complete for session %s (%d chunks received)",
                session_id,
                chunk_count,
            )


async def _safe_kick_off(base_url: str, session_id: str, prompt: str) -> None:
    """Wrap _kick_off_execution with logging so failures aren't silent."""
    try:
        await _kick_off_execution(base_url, session_id, prompt)
    except Exception:
        logger.exception(
            "[feedback-analysis] Background analysis FAILED for session %s",
            session_id,
        )


# ---------------------------------------------------------------------------
# Route factory
# ---------------------------------------------------------------------------


def create_feedback_routes(
    projects_dir: Path | None,
    daemon_session_path: str | None,
) -> APIRouter:
    """Create the feedback analysis router.

    Parameters
    ----------
    projects_dir:
        Root directory containing project slugs with session data.
    daemon_session_path:
        Path to the daemon's own session directory for server-log analysis.
    """
    router = APIRouter(prefix="/chat", tags=["chat-feedback"])

    @router.post("/api/feedback/analyze", response_model=AnalyzeResponse)
    async def analyze_feedback(
        body: AnalyzeRequest, request: Request
    ) -> AnalyzeResponse:
        if projects_dir is None:
            raise HTTPException(
                status_code=503,
                detail="Session storage not configured",
            )

        logger.info(
            "[feedback-analysis] Analyze request for session %s",
            body.session_id,
        )

        transcript_path = _find_transcript_path(projects_dir, body.session_id)
        if transcript_path is None:
            logger.warning(
                "[feedback-analysis] Transcript not found for session %s "
                "(projects_dir=%s)",
                body.session_id,
                projects_dir,
            )
            raise HTTPException(
                status_code=404,
                detail=f"Transcript not found for session {body.session_id}",
            )

        logger.info("[feedback-analysis] Found transcript at %s", transcript_path)

        _burl = request.base_url
        _host = _burl.hostname or "127.0.0.1"
        # Normalise bind-all wildcard addresses to loopback so that httpx can
        # actually connect.  amplifierd always listens on the same host, so
        # 127.0.0.1 is always correct for intra-process calls.
        if _host in ("0.0.0.0", "::"):
            _host = "127.0.0.1"
        _port = _burl.port
        base_url = (
            f"{_burl.scheme}://{_host}:{_port}"
            if _port
            else f"{_burl.scheme}://{_host}"
        )

        # Create a new analysis session and mark it hidden
        analysis_session_id = await _create_analysis_session(base_url)
        await _mark_session_hidden(base_url, analysis_session_id)

        # Build the prompt and kick off execution in the background
        prompt = _build_analysis_prompt(
            body.session_id, transcript_path, daemon_session_path
        )
        logger.info(
            "[feedback-analysis] Kicking off background execution "
            "(analysis_session=%s, target_session=%s, daemon_path=%s)",
            analysis_session_id,
            body.session_id,
            daemon_session_path,
        )
        asyncio.create_task(
            _safe_kick_off(base_url, analysis_session_id, prompt),
            name=f"analysis-{analysis_session_id}",
        )

        return AnalyzeResponse(analysis_session_id=analysis_session_id)

    return router
