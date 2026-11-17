"""Reads and writes the channels and videos tables through a direct Postgres connection."""

from datetime import datetime

import psycopg
from psycopg.rows import dict_row

from yt_smart_transcribe.errors import DATABASE, StageError

CONNECT_TIMEOUT_SECONDS = 10


def query(db_url: str, sql: str, params: dict | None = None) -> list[dict]:
    """Run one statement in its own connection and return its rows, keyed by column name."""
    try:
        with psycopg.connect(db_url, connect_timeout=CONNECT_TIMEOUT_SECONDS, row_factory=dict_row) as connection:
            cursor = connection.execute(sql, params)
            return cursor.fetchall() if cursor.description else []
    except psycopg.Error as e:
        raise StageError(DATABASE, "database", str(e).strip()) from e


def get_tracking_since(db_url: str, channel_id: str) -> datetime | None:
    """Return the time a channel is tracked from, or None if the channel has never been seen."""
    rows = query(db_url, "SELECT tracking_since FROM channels WHERE channel_id = %(channel_id)s", {"channel_id": channel_id})
    return rows[0]["tracking_since"] if rows else None


def insert_channel(db_url: str, channel_id: str, tracking_since: datetime) -> None:
    """Record a channel seen for the first time."""
    query(
        db_url,
        "INSERT INTO channels (channel_id, tracking_since) VALUES (%(channel_id)s, %(tracking_since)s)",
        {"channel_id": channel_id, "tracking_since": tracking_since},
    )


def stored_video_ids(db_url: str, video_ids: list[str]) -> set[str]:
    """Return which of the video IDs already have a row."""
    rows = query(db_url, "SELECT video_id FROM videos WHERE video_id = ANY(%(video_ids)s)", {"video_ids": video_ids})
    return {row["video_id"] for row in rows}


def get_video(db_url: str, video_id: str) -> dict | None:
    """Return the stored row of a video keyed by column name, or None if it is not stored."""
    rows = query(db_url, "SELECT * FROM videos WHERE video_id = %(video_id)s", {"video_id": video_id})
    return rows[0] if rows else None


def upsert_video(db_url: str, video: dict) -> None:
    """Store the video row, replacing any existing row with the same video ID."""
    query(
        db_url,
        """
        INSERT INTO videos (video_id, channel_id, title, published_at, duration_seconds, status, transcript)
        VALUES (%(video_id)s, %(channel_id)s, %(title)s, %(published_at)s, %(duration_seconds)s, %(status)s, %(transcript)s)
        ON CONFLICT (video_id) DO UPDATE SET
          channel_id = EXCLUDED.channel_id,
          title = EXCLUDED.title,
          published_at = EXCLUDED.published_at,
          duration_seconds = EXCLUDED.duration_seconds,
          status = EXCLUDED.status,
          transcript = EXCLUDED.transcript
        """,
        video,
    )
