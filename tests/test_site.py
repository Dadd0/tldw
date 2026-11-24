from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from markdown_it import MarkdownIt

from tldw.site import (
    format_age,
    format_duration,
    reading_time,
    render_essay,
    submission_rows,
    submitted_video_id,
)


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


def test_submission_rows_follow_the_process_and_essay() -> None:
    """Show newest submissions first and hide a written essay during embedding."""
    now = datetime(2026, 11, 24, tzinfo=UTC)
    code = None
    process = SimpleNamespace(poll=lambda: code)
    entries = {
        "older": {
            "title": "First",
            "submitted_at": now - timedelta(minutes=2),
            "process": process,
        },
        "newer": {"title": "Second", "submitted_at": now, "process": process},
    }
    rows = submission_rows(entries, set(), now)
    assert [(r["title"], r["processing"]) for r in rows] == [
        ("Second", True),
        ("First", True),
    ]
    assert [r["video_id"] for r in submission_rows(entries, {"older"}, now)] == [
        "newer"
    ]
    code = 0
    assert submission_rows(entries, {"older", "newer"}, now) == []
    assert entries == {}


def test_submission_rows_retain_failures_for_a_day_or_until_published() -> None:
    """Give a failed job a day from detection, even if transcription took longer."""
    now = datetime(2026, 11, 24, tzinfo=UTC)
    entries = {
        video_id: {
            "title": video_id,
            "submitted_at": now - timedelta(days=2),
            "process": SimpleNamespace(poll=lambda: 7),
        }
        for video_id in ("failed", "published")
    }
    rows = submission_rows(entries, {"published"}, now)
    assert [(r["video_id"], r["processing"]) for r in rows] == [("failed", False)]
    assert list(entries) == ["failed"]
    assert submission_rows(entries, set(), now + timedelta(days=1)) == []
    assert entries == {}


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


def test_render_essay_gives_h2s_unique_ids() -> None:
    """Number repeated headings, strip Markdown, and leave other levels alone."""
    markdown = MarkdownIt("commonmark", {"html": False})
    body = "# Top\n\n## Why it works\n\ntext\n\n## Why it works\n\n### Detail\n\n## **Bold** `code` <b>\n"
    html, toc = render_essay(markdown, body)
    assert toc == [
        {"id": "section-why-it-works", "text": "Why it works"},
        {"id": "section-why-it-works-2", "text": "Why it works"},
        {"id": "section-bold-code-b", "text": "Bold code <b>"},
    ]
    assert '<h2 id="section-why-it-works-2">Why it works</h2>' in html
    assert "<h1>Top</h1>" in html and "<h3>Detail</h3>" in html
    assert "&lt;b&gt;" in html and "<b>" not in html


def test_render_essay_without_headings_is_unchanged() -> None:
    """Render an essay with no h2 exactly as plain Markdown, with an empty contents list."""
    markdown = MarkdownIt("commonmark", {"html": False})
    body = "Thesis first.\n\nSecond paragraph."
    assert render_essay(markdown, body) == (markdown.render(body), [])
