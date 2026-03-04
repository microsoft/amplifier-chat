# amplifierd-plugin-chat

A chat UI plugin for [amplifierd](https://github.com/payneio/amplifierd). Adds a browser-based conversational interface for creating and managing Amplifier sessions.

## What it provides

When loaded into amplifierd, the plugin mounts these endpoints:

| Path | Description |
|------|-------------|
| `GET /chat/` | Single-page chat UI |
| `GET /chat/health` | Health check |
| `POST /chat/command` | Slash-command processing (`/help`, `/status`, `/clear`, etc.) |
| `GET /chat/api/sessions/history` | Discover past sessions from disk |
| `GET\|POST /chat/api/sessions/revisions` | Session change-detection for live refresh |
| `GET /chat/api/sessions/pins` | List pinned sessions |
| `POST\|DELETE /chat/api/sessions/{id}/pin` | Pin/unpin a session |

The UI uses amplifierd's native REST API for session lifecycle and SSE for streaming — no WebSocket required.

## Installation

If amplifierd is installed as a [uv tool](https://docs.astral.sh/uv/concepts/tools/), add the plugin with `--with`:

```bash
uv tool install git+https://github.com/payneio/amplifierd \
  --with git+https://github.com/<org>/amplifierd-plugin-chat
```

If amplifierd is already installed, pass `--force` to reinstall with the plugin:

```bash
uv tool install git+https://github.com/payneio/amplifierd --force \
  --with git+https://github.com/<org>/amplifierd-plugin-chat
```

Alternatively, if you manage amplifierd's environment directly, install the plugin with `uv pip`:

```bash
uv pip install git+https://github.com/<org>/amplifierd-plugin-chat
```

amplifierd discovers it automatically via the `amplifierd.plugins` entry point on next startup. Open `http://127.0.0.1:8410/chat/` once the daemon is running.

To disable the plugin without uninstalling:

```bash
amplifierd serve --disabled-plugins chat
```

## Configuration

The plugin stores pinned sessions in `~/.amplifier-chat/`. Override with:

```bash
export CHAT_PLUGIN_HOME_DIR=/path/to/chat-data
```

## Development

### Run tests

```bash
cd amplifierd-plugin-chat
uv run --extra test pytest -v
```

### Run a local amplifierd instance with the plugin

No global install needed. The `dev` extra pulls amplifierd from git and runs everything in an isolated `.venv`:

```bash
cd amplifierd-plugin-chat
uv run --extra dev amplifierd serve --log-level debug
```

Then open `http://127.0.0.1:8410/chat/`.

### Standalone dev server (UI only)

For iterating on the frontend without the full daemon:

```bash
cd amplifierd-plugin-chat
uv run --extra dev python -m chat_plugin
```

This starts a minimal FastAPI server with mock state. The UI loads and history/pin endpoints work, but session creation and execution require the full amplifierd daemon.

Options:

```
--host HOST           Bind address (default: 127.0.0.1)
--port PORT           Bind port (default: 8410)
--sessions-dir PATH   Point at a real sessions directory for history scanning
--reload              Auto-restart on code changes
```

### Project structure

```
src/chat_plugin/
    __init__.py          Plugin entry point (create_router)
    __main__.py          Standalone dev server
    commands.py          Slash-command processing
    config.py            Plugin settings (home dir)
    pin_storage.py       Persistent pin state with timestamps
    routes.py            FastAPI route factories
    session_history.py   Disk-based session discovery
    static/
        index.html       Single-page React UI (Preact + HTM)
        vendor.js         Bundled Preact/HTM runtime
```
