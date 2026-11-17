"""Sends one audio chunk to OpenRouter and returns its text."""

import base64
from pathlib import Path

import requests

from yt_smart_transcribe.errors import TRANSCRIPTION, StageError

URL = "https://openrouter.ai/api/v1/audio/transcriptions"
TIMEOUT_SECONDS = 600


def transcribe(mp3: Path, api_key: str, model_id: str) -> str:
    """Return the text spoken in the mp3."""
    audio = base64.b64encode(mp3.read_bytes()).decode()
    try:
        response = requests.post(
            URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": model_id, "input_audio": {"data": audio, "format": "mp3"}},
            timeout=TIMEOUT_SECONDS,
        )
        if response.status_code != 200:
            raise StageError(TRANSCRIPTION, "transcription", f"HTTP {response.status_code}: {response.text[:300]}")
        text = (response.json().get("text") or "").strip()
    except requests.RequestException as e:
        raise StageError(TRANSCRIPTION, "transcription", str(e)) from e
    if not text:
        raise StageError(TRANSCRIPTION, "transcription", "empty transcript")
    return text
