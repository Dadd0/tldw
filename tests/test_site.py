from datetime import UTC, datetime, timedelta

import pytest

from tldw.site import format_age, format_duration, reading_time, submitted_video_id


@pytest.mark.parametrize(
    "value",
    [
        "  -BcdeF0_123  ",
        "https://www.youtube.com/watch?t=4&v=-BcdeF0_123",
        "https://youtu.be/-BcdeF0_123?si=shared",
        "https://m.youtube.com/shorts/-BcdeF0_123",
        "http://youtube.com/live/-BcdeF0_123/#t=5",
    ],
)
def test_submitted_video_id_accepts_shared_links_and_ids(value: str) -> None:
    """Extract the same ID from each supported video link."""
    assert submitted_video_id(value) == "-BcdeF0_123"


@pytest.mark.parametrize(
    "value",
    [
        "",
        "too-short",
        "abcdefghijkl",
        "abcdefghij!",
        "https://example.org/watch?v=-BcdeF0_123",
        "https://youtube.com.example.org/watch?v=-BcdeF0_123",
        "https://user@youtube.com/watch?v=-BcdeF0_123",
        "ftp://youtube.com/watch?v=-BcdeF0_123",
        "https://youtube.com/playlist?list=-BcdeF0_123",
        "https://youtube.com/watch?v=-BcdeF0_123&v=abcdefghijk",
        "https://youtube.com/watch?v=",
        "https://youtu.be/-BcdeF0_123/another",
        "https://youtube.com/shorts/too-short",
        "https://youtube.com/live/Missing ID",
        "https://[bad-host",
    ],
)
def test_submitted_video_id_rejects_invalid_input(value: str) -> None:
    """Require a supported YouTube host and one well-formed video ID."""
    assert submitted_video_id(value) is None


@pytest.mark.parametrize(
    ("word_count", "expected"),
    [(0, 0), (1, 1), (230, 1), (231, 2)],
)
def test_reading_time_rounds_up(word_count: int, expected: int) -> None:
    """Start a new reading minute after every 230 words."""
    assert reading_time("word " * word_count) == expected


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [(42, "42s"), (60, "1m"), (3_599, "59m"), (3_600, "1h 0m"), (6_120, "1h 42m")],
)
def test_format_duration(seconds: int, expected: str) -> None:
    """Format durations below a minute, below an hour, and above an hour."""
    assert format_duration(seconds) == expected


@pytest.mark.parametrize(
    ("elapsed_seconds", "expected"),
    [
        (-1, "just now"),
        (59, "just now"),
        (60, "1 minute ago"),
        (7_200, "2 hours ago"),
        (86_400, "1 day ago"),
    ],
)
def test_format_age(elapsed_seconds: int, expected: str) -> None:
    """Format a video's age relative to a fixed time."""
    now = datetime(2026, 11, 22, 12, tzinfo=UTC)
    published_at = now - timedelta(seconds=elapsed_seconds)

    assert format_age(published_at, now) == expected
