from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path


class PinStorage:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._pins: list[str] = []
        self._pinned_at: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                raw_pinned = data.get("pinned", [])
                self._pins = list(raw_pinned) if isinstance(raw_pinned, list) else []
                raw_at = data.get("pinned_at", {})
                self._pinned_at = dict(raw_at) if isinstance(raw_at, dict) else {}
            except (json.JSONDecodeError, KeyError, ValueError):
                self._pins = []
                self._pinned_at = {}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(
                {"pinned": self._pins, "pinned_at": self._pinned_at},
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        os.rename(tmp, self._path)

    def list_pins(self) -> set[str]:
        return set(self._pins)

    def get_pins_with_timestamps(self) -> dict[str, str]:
        """Return pinned session IDs mapped to their pin timestamps."""
        return {sid: self._pinned_at.get(sid, "") for sid in self._pins}

    def add(self, session_id: str) -> None:
        if session_id in self._pins:
            return
        self._pins.append(session_id)
        self._pinned_at[session_id] = datetime.now(UTC).isoformat()
        self._save()

    def remove(self, session_id: str) -> None:
        if session_id not in self._pins:
            return
        self._pins.remove(session_id)
        self._pinned_at.pop(session_id, None)
        self._save()
