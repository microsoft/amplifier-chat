"""Standalone dev server for the chat plugin.

Usage:
    cd amplifierd-plugin-chat
    uv run --extra dev python -m chat_plugin

The UI loads at http://127.0.0.1:8410/chat/
Session creation and execution require amplifierd, but the UI, history,
and pin endpoints work standalone.
"""

from __future__ import annotations

import argparse
from pathlib import Path


class _MockSettings:
    sessions_dir: Path | None = None


class _MockState:
    session_manager = None
    event_bus = None
    bundle_registry = None
    settings = _MockSettings()


def main() -> None:
    parser = argparse.ArgumentParser(description="Chat plugin dev server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8410)
    parser.add_argument("--sessions-dir", type=Path, default=None,
                        help="Path to sessions directory for history scanning")
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    import uvicorn
    from fastapi import FastAPI

    from chat_plugin import create_router

    state = _MockState()
    if args.sessions_dir:
        state.settings.sessions_dir = args.sessions_dir

    app = FastAPI(title="amplifierd-plugin-chat (dev)")
    app.include_router(create_router(state))

    print(f"Chat plugin dev server → http://{args.host}:{args.port}/chat/")
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
