"""Sends one audio chunk to OpenRouter and returns its timestamped words."""

import base64
from pathlib import Path

import requests

from tldw.errors import TRANSCRIPTION, StageError

URL = "https://openrouter.ai/api/v1/audio/transcriptions"
MODEL_ID = "x-ai/grok-stt-2.0"
TIMEOUT_SECONDS = 600


def transcribe(mp3: Path, api_key: str, language: str | None = None) -> list[dict]:
    """Return the words, timestamps, and speakers in one audio chunk."""
    try:
        audio = base64.b64encode(mp3.read_bytes()).decode()
        payload = {
            "model": MODEL_ID,
            "input_audio": {"data": audio, "format": "mp3"},
            "response_format": "verbose_json",
            "timestamp_granularities": ["segment", "word"],
            "provider": {"options": {"xai": {"diarize": True}}},
        }
        if language is not None:
            payload["language"] = language

        response = requests.post(
            URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
            timeout=TIMEOUT_SECONDS,
        )
        if response.status_code != 200:
            raise StageError(
                TRANSCRIPTION,
                "transcription",
                f"HTTP {response.status_code}: {response.text[:300]}",
            )
        result = response.json()
    except (OSError, requests.RequestException) as e:
        raise StageError(TRANSCRIPTION, "transcription", str(e)) from e

    words = result.get("words") if isinstance(result, dict) else None
    if not isinstance(words, list):
        raise StageError(
            TRANSCRIPTION, "transcription", "missing or invalid words list"
        )

    for word in words:
        if (
            not isinstance(word, dict)
            or not isinstance(word.get("word"), str)
            or not isinstance(word.get("start"), (int, float))
            or not isinstance(word.get("end"), (int, float))
            or not isinstance(word.get("speaker"), int)
        ):
            raise StageError(TRANSCRIPTION, "transcription", "invalid word in response")

    return words
