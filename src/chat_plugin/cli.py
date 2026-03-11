"""CLI entry point for amplifier-chat.

Boots a real amplifierd instance with the chat plugin. This is the
standalone-app pattern: amplifierd is the platform, plugins provide the
experience. When installed as a plugin into amplifierd (or amplifier-distro),
the same ``create_router`` entry point is used -- nothing changes.

For plugin UI development without amplifierd, use the mock dev server::

    python -m chat_plugin

Usage::

    amplifier-chat
    amplifier-chat --port 9000
    amplifier-chat --reload
    amplifier-chat --no-browser
"""

from __future__ import annotations

import logging

import click

_LOG_LEVELS: dict[str, int] = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}


@click.command()
@click.option("--host", default=None, type=str, help="Bind host address.")
@click.option("--port", default=None, type=int, help="Bind port number.")
@click.option(
    "--reload", is_flag=True, default=False, help="Enable hot-reload for development."
)
@click.option(
    "--log-level",
    default=None,
    type=click.Choice(["debug", "info", "warning", "error"], case_sensitive=False),
    help="Log level (overrides AMPLIFIERD_LOG_LEVEL).",
)
@click.option(
    "--no-browser",
    is_flag=True,
    default=False,
    help="Don't auto-open the browser.",
)
def main(
    host: str | None,
    port: int | None,
    reload: bool,
    log_level: str | None,
    no_browser: bool,
) -> None:
    """amplifier-chat -- Amplifier Chat standalone app."""
    import os
    import threading
    import time
    import webbrowser

    import uvicorn

    from amplifierd.config import DaemonSettings
    from amplifierd.daemon_session import create_session_dir, setup_session_log

    settings = DaemonSettings()

    effective_host = host if host is not None else settings.host
    effective_port = port if port is not None else settings.port
    effective_log_level = log_level if log_level is not None else settings.log_level

    logging.basicConfig(
        level=_LOG_LEVELS.get(effective_log_level.lower(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    session_path = create_session_dir(
        settings.daemon_run_dir,
        host=effective_host,
        port=effective_port,
        log_level=effective_log_level,
    )
    setup_session_log(session_path)
    os.environ["AMPLIFIERD_DAEMON_SESSION_PATH"] = str(session_path)

    url = f"http://{effective_host}:{effective_port}/chat/"

    if not no_browser:

        def _open_browser() -> None:
            time.sleep(1.5)
            webbrowser.open(url)

        threading.Thread(target=_open_browser, daemon=True).start()

    click.echo(f"amplifier-chat starting -- {url}")

    uvicorn.run(
        "amplifierd.app:create_app",
        host=effective_host,
        port=effective_port,
        reload=reload,
        log_level=effective_log_level,
        factory=True,
    )
