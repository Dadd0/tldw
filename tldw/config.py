"""Loads and validates the settings in .env and the channel IDs in channels.txt."""

import os
import re
from collections.abc import Mapping
from pathlib import Path

from dotenv import load_dotenv

from tldw.errors import CONFIG, StageError

CHANNELS_FILE = Path("channels.txt")
STYLE_FILE = Path("style.md")
REQUIRED = ("OPENROUTER_API_KEY", "SUPABASE_DB_URL", "ESSAY_MODEL_ID", "CHAT_MODEL_ID")
CHANNEL_ID = re.compile(r"UC[A-Za-z0-9_-]{22}")


def load_settings(env: Mapping[str, str] | None = None) -> dict[str, str]:
    """Return the settings keyed by variable name, reading .env when no mapping is given."""
    if env is None:
        load_dotenv()
        env = os.environ
    missing = [name for name in REQUIRED if not env.get(name)]
    if missing:
        raise StageError(CONFIG, "config", f"missing in .env: {', '.join(missing)}")
    return {name: env[name] for name in REQUIRED}


def load_channels(path: Path = CHANNELS_FILE) -> list[tuple[str, str | None]]:
    """Return (channel ID, language) pairs in file order, keeping the first occurrence."""
    try:
        lines = path.read_text().splitlines()
    except OSError as e:
        raise StageError(CONFIG, "config", f"cannot read {path}: {e}") from e

    channels: dict[str, str | None] = {}
    for number, line in enumerate(lines, 1):
        fields = line.split("#", 1)[0].split()
        if not fields:
            continue
        if len(fields) > 2:
            raise StageError(
                CONFIG,
                "config",
                f"{path} line {number}: expected an ID and optional language",
            )

        channel_id = fields[0]
        if not CHANNEL_ID.fullmatch(channel_id):
            raise StageError(
                CONFIG,
                "config",
                f"{path} line {number}: not a channel ID: {channel_id!r}",
            )

        language = fields[1].lower() if len(fields) == 2 else None
        if language is not None and re.fullmatch(r"[a-z]{2}", language) is None:
            raise StageError(
                CONFIG,
                "config",
                f"{path} line {number}: expected a two-letter language code",
            )

        channels.setdefault(channel_id, language)

    return list(channels.items())


def load_style(path: Path = STYLE_FILE) -> str:
    """Read the essay style instructions."""
    try:
        return path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError) as error:
        raise StageError(CONFIG, "config", f"cannot read {path}: {error}") from error
