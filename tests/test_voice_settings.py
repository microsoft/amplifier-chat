"""Tests for voice settings atomicity."""

import json
from pathlib import Path
from unittest.mock import patch


def test_save_voice_settings_uses_atomic_write(tmp_path):
    """S-19: _save_voice_settings must use tmp+rename for atomicity."""
    settings_file = tmp_path / "voice-settings.json"

    with (
        patch("chat_plugin.voice._SETTINGS_DIR", tmp_path),
        patch("chat_plugin.voice._VOICE_SETTINGS_FILE", settings_file),
    ):
        from chat_plugin.voice import _save_voice_settings

        _save_voice_settings({"stt_model": "base", "tts_voice": "en-US-AriaNeural"})

    # File should exist with correct content
    assert settings_file.exists()
    data = json.loads(settings_file.read_text())
    assert data["stt_model"] == "base"

    # No .tmp file should be left behind
    tmp_files = list(tmp_path.glob("*.tmp"))
    assert tmp_files == [], f"Leftover .tmp files found: {tmp_files}"
