"""Voice feature routes for the chat plugin — STT and TTS."""

from __future__ import annotations

import asyncio
import base64
import io
import logging
import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)

# Lazy imports — these are optional dependencies
_whisper_available = False
_tts_available = False

try:
    from pywhispercpp.model import Model as WhisperModel
    import av

    _whisper_available = True
except ImportError:
    pass

try:
    import edge_tts

    _tts_available = True
except ImportError:
    pass

# Model cache (singleton — loaded once, reused across requests)
_whisper_model: WhisperModel | None = None
_whisper_model_name: str = ""

# Default config
DEFAULT_STT_MODEL = "base"
DEFAULT_TTS_VOICE = "en-US-AriaNeural"

# User settings persistence
_SETTINGS_DIR = Path.home() / ".amplifier-chat"
_VOICE_SETTINGS_FILE = _SETTINGS_DIR / "voice-settings.json"

# All available models with metadata
STT_MODELS = {
    "tiny": {"size_mb": 75, "label": "Tiny — fastest, lower accuracy"},
    "base": {"size_mb": 142, "label": "Base — balanced"},
    "small": {"size_mb": 466, "label": "Small — accurate"},
    "medium": {"size_mb": 1500, "label": "Medium — high accuracy"},
    "large-v3-turbo": {"size_mb": 1500, "label": "Large Turbo — best quality"},
}


def _load_voice_settings() -> dict:
    """Load persisted voice settings."""
    try:
        if _VOICE_SETTINGS_FILE.exists():
            import json

            return json.loads(_VOICE_SETTINGS_FILE.read_text())
    except Exception:
        logger.warning(
            "Failed to load voice settings from %s", _VOICE_SETTINGS_FILE, exc_info=True
        )
    return {"stt_model": DEFAULT_STT_MODEL, "tts_voice": DEFAULT_TTS_VOICE}


def _save_voice_settings(settings: dict) -> None:
    """Persist voice settings atomically (tmp + rename)."""
    import json

    _SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _VOICE_SETTINGS_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    os.rename(tmp, _VOICE_SETTINGS_FILE)


# Where whisper models are cached
def _models_dir() -> Path:
    return Path.home() / ".local" / "share" / "whisper-cpp" / "models"


def _get_whisper_model(model_name: str) -> WhisperModel:
    """Get or create the whisper model (thread-safe singleton)."""
    global _whisper_model, _whisper_model_name
    if _whisper_model is not None and _whisper_model_name == model_name:
        return _whisper_model

    # Check if model file exists, download if not
    models_dir = _models_dir()
    model_file = models_dir / f"ggml-{model_name}.bin"

    if not model_file.exists():
        raise HTTPException(
            status_code=503,
            detail={
                "error": "model_not_downloaded",
                "model": model_name,
                "message": f"Whisper model '{model_name}' not found. Use POST /chat/voice/download-model to download it first.",
            },
        )

    _whisper_model = WhisperModel(
        str(model_file), n_threads=min(os.cpu_count() or 4, 8)
    )
    _whisper_model_name = model_name
    return _whisper_model


def _convert_audio_to_wav(audio_bytes: bytes, audio_format: str) -> bytes:
    """Convert any supported audio format to 16kHz mono WAV using PyAV."""
    input_buf = io.BytesIO(audio_bytes)
    output_buf = io.BytesIO()

    input_container = av.open(
        input_buf, format=audio_format if audio_format != "wav" else None
    )
    output_container = av.open(output_buf, mode="w", format="wav")

    out_stream = output_container.add_stream("pcm_s16le", rate=16000, layout="mono")
    resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)

    for frame in input_container.decode(audio=0):
        for resampled in resampler.resample(frame):
            for packet in out_stream.encode(resampled):
                output_container.mux(packet)

    for packet in out_stream.encode(None):
        output_container.mux(packet)

    output_container.close()
    input_container.close()

    return output_buf.getvalue()


def _transcribe_sync(wav_bytes: bytes, model_name: str, language: str | None) -> dict:
    """Synchronous transcription (runs in thread pool)."""
    model = _get_whisper_model(model_name)

    # Write WAV to temp file (pywhispercpp needs a file path)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(wav_bytes)
        tmp_path = f.name

    try:
        # Transcribe
        segments = model.transcribe(tmp_path, language=language)

        text_parts = []
        seg_list = []
        for seg in segments:
            text_parts.append(seg.text.strip())
            seg_list.append(
                {
                    "text": seg.text.strip(),
                    "start": seg.t0 / 100.0,
                    "end": seg.t1 / 100.0,
                }
            )

        return {
            "text": " ".join(text_parts),
            "segments": seg_list,
            "language": language or "auto",
        }
    finally:
        os.unlink(tmp_path)


def create_voice_routes() -> APIRouter:
    """Create the voice feature sub-router."""
    router = APIRouter(prefix="/chat", tags=["chat-voice"])

    @router.post("/transcribe")
    async def transcribe_audio(request: Request):
        """Transcribe audio using local whisper.cpp."""
        if not _whisper_available:
            raise HTTPException(
                status_code=501,
                detail="Speech-to-text not available. Install voice dependencies: uv sync --extra voice",
            )

        body = await request.json()
        audio_data_b64 = body.get("audio_data")
        audio_format = body.get("audio_format", "webm")
        language = body.get("language")  # None = auto-detect
        settings = _load_voice_settings()
        model_name = body.get("model", settings.get("stt_model", DEFAULT_STT_MODEL))

        if model_name not in STT_MODELS:
            raise HTTPException(status_code=400, detail=f"Unknown model: {model_name}")

        if not audio_data_b64:
            raise HTTPException(status_code=400, detail="Missing 'audio_data' field")

        try:
            audio_bytes = base64.b64decode(audio_data_b64)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid base64 audio data")

        # Convert to 16kHz mono WAV
        try:
            wav_bytes = await asyncio.to_thread(
                _convert_audio_to_wav, audio_bytes, audio_format
            )
        except Exception as e:
            logger.warning("Audio conversion failed: %s", e)
            raise HTTPException(status_code=400, detail=f"Audio conversion failed: {e}")

        # Transcribe in thread pool
        try:
            result = await asyncio.to_thread(
                _transcribe_sync, wav_bytes, model_name, language
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Transcription failed: %s", e)
            raise HTTPException(status_code=500, detail=f"Transcription failed: {e}")

        return result

    @router.post("/tts")
    async def text_to_speech(request: Request):
        """Stream TTS audio as MP3 using edge-tts."""
        if not _tts_available:
            raise HTTPException(
                status_code=501,
                detail="Text-to-speech not available. Install voice dependencies: uv sync --extra voice",
            )

        body = await request.json()
        text = body.get("text", "")
        settings = _load_voice_settings()
        voice = body.get("voice", settings.get("tts_voice", DEFAULT_TTS_VOICE))

        if not text or not text.strip():
            raise HTTPException(status_code=400, detail="Missing 'text' field")

        # Strip markdown for cleaner speech
        clean_text = _strip_markdown(text)

        communicate = edge_tts.Communicate(clean_text, voice)

        async def audio_stream():
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    yield chunk["data"]

        return StreamingResponse(
            audio_stream(),
            media_type="audio/mpeg",
            headers={"Content-Disposition": "inline"},
        )

    @router.get("/tts/voices")
    async def list_tts_voices():
        """List available TTS voices."""
        if not _tts_available:
            raise HTTPException(status_code=501, detail="TTS not available")

        voices = await edge_tts.list_voices()
        # Return a simplified list
        return {
            "voices": [
                {
                    "id": v["ShortName"],
                    "name": v["FriendlyName"],
                    "locale": v["Locale"],
                    "gender": v["Gender"],
                }
                for v in voices
            ],
            "default": DEFAULT_TTS_VOICE,
        }

    @router.get("/voice/config")
    async def voice_config():
        """Return current voice feature configuration."""
        settings = _load_voice_settings()
        active_model = settings.get("stt_model", DEFAULT_STT_MODEL)
        active_voice = settings.get("tts_voice", DEFAULT_TTS_VOICE)
        models_path = _models_dir()

        models = []
        for model_id, meta in STT_MODELS.items():
            model_file = models_path / f"ggml-{model_id}.bin"
            downloaded = model_file.exists()
            actual_size = (
                round(model_file.stat().st_size / (1024 * 1024), 1)
                if downloaded
                else None
            )
            models.append(
                {
                    "id": model_id,
                    "label": meta["label"],
                    "size_mb": meta["size_mb"],
                    "downloaded": downloaded,
                    "actual_size_mb": actual_size,
                    "active": model_id == active_model,
                }
            )

        active_model_downloaded = (models_path / f"ggml-{active_model}.bin").exists()

        return {
            "stt_available": _whisper_available,
            "tts_available": _tts_available,
            "stt_model": active_model,
            "stt_model_downloaded": active_model_downloaded,
            "tts_voice": active_voice,
            "models": models,
            "models_dir": str(models_path),
        }

    @router.post("/voice/settings")
    async def update_voice_settings(request: Request):
        """Update voice settings (active model, voice)."""
        body = await request.json()
        settings = _load_voice_settings()

        if "stt_model" in body:
            model = body["stt_model"]
            if model not in STT_MODELS:
                raise HTTPException(status_code=400, detail=f"Unknown model: {model}")
            model_file = _models_dir() / f"ggml-{model}.bin"
            if not model_file.exists():
                raise HTTPException(
                    status_code=400,
                    detail=f"Model '{model}' is not downloaded. Download it first.",
                )
            settings["stt_model"] = model
            # Clear cached model so next transcription loads the new one
            global _whisper_model, _whisper_model_name
            _whisper_model = None
            _whisper_model_name = ""

        if "tts_voice" in body:
            settings["tts_voice"] = body["tts_voice"]

        _save_voice_settings(settings)
        return {"status": "updated", "settings": settings}

    @router.post("/voice/download-model")
    async def download_stt_model(request: Request):
        """Download a whisper model for STT."""
        if not _whisper_available:
            raise HTTPException(
                status_code=501, detail="STT dependencies not installed"
            )

        body = await request.json() if await request.body() else {}
        model_name = body.get("model", DEFAULT_STT_MODEL)

        if model_name not in STT_MODELS:
            raise HTTPException(status_code=400, detail=f"Unknown model: {model_name}")

        models_dir = _models_dir()
        model_file = models_dir / f"ggml-{model_name}.bin"

        if model_file.exists():
            return {
                "status": "already_downloaded",
                "model": model_name,
                "path": str(model_file),
            }

        # Download from HuggingFace
        models_dir.mkdir(parents=True, exist_ok=True)
        url = f"https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-{model_name}.bin"

        import httpx

        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=300) as client:
                async with client.stream("GET", url) as resp:
                    if resp.status_code != 200:
                        raise HTTPException(
                            status_code=502,
                            detail=f"Failed to download model: HTTP {resp.status_code}",
                        )

                    tmp_path = model_file.with_suffix(".tmp")

                    with open(tmp_path, "wb") as f:
                        async for chunk in resp.aiter_bytes(chunk_size=1024 * 1024):
                            f.write(chunk)

                    tmp_path.rename(model_file)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Download failed: {e}")

        return {
            "status": "downloaded",
            "model": model_name,
            "size_mb": round(model_file.stat().st_size / (1024 * 1024), 1),
        }

    @router.post("/voice/delete-model")
    async def delete_stt_model(request: Request):
        """Delete a downloaded whisper model."""
        global _whisper_model, _whisper_model_name

        body = await request.json() if await request.body() else {}
        model_name = body.get("model", DEFAULT_STT_MODEL)

        if model_name not in STT_MODELS:
            raise HTTPException(status_code=400, detail=f"Unknown model: {model_name}")

        model_file = _models_dir() / f"ggml-{model_name}.bin"

        if not model_file.exists():
            return {"status": "not_found", "model": model_name}

        size_mb = round(model_file.stat().st_size / (1024 * 1024), 1)
        model_file.unlink()

        # Clear cached model if it was the one deleted
        if _whisper_model_name == model_name:
            _whisper_model = None
            _whisper_model_name = ""

        # If deleted model was the active one, reset to default
        settings = _load_voice_settings()
        if settings.get("stt_model") == model_name:
            settings["stt_model"] = DEFAULT_STT_MODEL
            _save_voice_settings(settings)

        return {"status": "deleted", "model": model_name, "freed_mb": size_mb}

    return router


def _strip_markdown(text: str) -> str:
    """Strip markdown formatting for cleaner TTS output."""
    import re

    # Remove code blocks
    text = re.sub(r"```[\s\S]*?```", "", text)
    # Remove inline code
    text = re.sub(r"`[^`]+`", "", text)
    # Remove links, keep text
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    # Remove images
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", "", text)
    # Remove headers markers
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # Remove bold/italic markers
    text = re.sub(r"[*_]{1,3}", "", text)
    # Remove horizontal rules
    text = re.sub(r"^[-*_]{3,}\s*$", "", text, flags=re.MULTILINE)
    # Remove list markers
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)
    # Remove table formatting
    text = re.sub(r"\|", " ", text)
    text = re.sub(r"^[-:| ]+$", "", text, flags=re.MULTILINE)
    # Collapse whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
