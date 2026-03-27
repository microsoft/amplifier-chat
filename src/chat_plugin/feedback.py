"""Feedback analysis endpoint.

Creates a hidden analysis session, kicks off an analysis prompt via the
daemon's streaming execution endpoint, and returns the analysis_session_id
immediately so the UI can poll for results.
"""

from __future__ import annotations

import asyncio
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
    """Build the analysis prompt focused on infrastructure/harness failures.

    This prompt ONLY looks for platform-level issues: LLM API errors,
    tool execution failures, SSE connection problems, file I/O errors,
    session lifecycle issues. It does NOT analyze the content of the
    user's conversation or what they were discussing.
    """
    server_log_section = ""
    if daemon_session_path:
        server_log_section = f"""
TASK 2 — Server log analysis
Read the server log at: {daemon_session_path}/serve.log
Search for entries correlated with session {session_id}:
- HTTP 5xx responses
- Connection errors (ConnectionResetError, BrokenPipeError)
- SSE subscriber drops
- Unhandled exceptions / tracebacks
Include 2-3 surrounding context lines for each finding.
If the file doesn't exist or has no relevant entries, skip this task."""

    return f"""\
You are analyzing session {session_id} for INFRASTRUCTURE FAILURES only.

IMPORTANT: You are NOT analyzing what the user was discussing or the content
of their conversation. You are looking for PLATFORM-LEVEL errors — things
the Amplifier system did wrong, not what the user asked about.

TASK 1 — Session transcript analysis
Read the transcript at: {transcript_path}

Look ONLY for these event types that indicate infrastructure failures:
- tool:error events (tool execution failures, timeouts)
- provider:error events (LLM API errors: 429, 500, 529, timeouts)
- Unhandled exceptions with tracebacks
- Session lifecycle errors (failed resume, failed spawn)
- File I/O errors (permission denied, disk full, missing files)

For each error found, preserve the ORIGINAL event data shape from the
transcript. Extract the relevant stack trace frames (top 2-3 frames).

DO NOT include:
- The user's messages or what they asked about
- The assistant's responses or reasoning
- Tool calls that succeeded normally
- Content-level analysis of the conversation topic
{server_log_section}

TASK 3 — GitHub issue search
For each distinct error pattern found above, search for related issues:
  gh issue list --repo microsoft/amplifier-distro --search "<error type or message>" \
    --state all --limit 3 --json number,title,url,state

If no errors were found in Tasks 1-2, skip this task.

For each GitHub issue found, assess confidence using these definitions:
- "high": The session error's message, type, or stack trace directly matches what
  the issue describes. Same failure mode, same component.
- "medium": The issue is in the same component/module area and describes a related
  (but not identical) failure pattern. Plausibly the same root cause.
- "low": Only superficial keyword overlap. The issue mentions similar terms but
  describes a different problem or context.

OUTPUT FORMAT
Return a single flat JSON array. Output ONLY valid JSON — no markdown fences,
no commentary, no explanation before or after. Just the array.

Each item MUST have a "source" field: "github", "session", or "server_log".

Item schemas:
- GitHub: {{"source":"github","summary":"#N - title","url":"https://...","state":"open|closed","confidence":"high|medium|low","relevance":"why this matches"}}
- Session: {{"source":"session","summary":"one-line","timestamp":"ISO","turn":N,"event_type":"tool:error|provider:error","event_data":{{original event data from transcript}},"error":{{"type":"ErrorType","message":"...","traceback":["frame1","frame2"]}}}}
- Server log: {{"source":"server_log","summary":"one-line","timestamp":"ISO","log_level":"ERROR","log_line":"full line","context_lines":["surrounding lines"]}}

If NO infrastructure errors found at all, output: []
"""


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

        # S-25: Use the actual socket bind address from the ASGI scope, not the
        # client-controlled Host header.  request.base_url / request.headers["host"]
        # can be spoofed by an attacker to redirect the internal loopback call to an
        # arbitrary host (SSRF).  request.scope["server"] is injected by uvicorn
        # from the OS-level socket bind address and cannot be influenced by HTTP
        # headers.  The scheme is hardcoded to "http" because this is always a
        # loopback call to the same process.
        _host, _port = request.scope["server"]
        if _host in ("0.0.0.0", "::"):
            _host = "127.0.0.1"
        base_url = f"http://127.0.0.1:{_port}"

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
