"""Fetches and parses a channel's RSS feed and selects the videos to process."""

from datetime import UTC, datetime
from xml.etree import ElementTree

import requests

from tldw.errors import FEED, StageError

URL = "https://www.youtube.com/feeds/videos.xml"
TIMEOUT_SECONDS = 30
NAMESPACES = {
    "a": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
}


def fetch_feed(channel_id: str) -> list[dict]:
    """Return the entries of the channel's feed, oldest first."""
    try:
        response = requests.get(
            URL, params={"channel_id": channel_id}, timeout=TIMEOUT_SECONDS
        )
    except requests.RequestException as e:
        raise StageError(FEED, "feed", str(e)) from e
    if response.status_code != 200:
        raise StageError(FEED, "feed", f"HTTP {response.status_code}")
    return parse_feed(response.text)


def parse_feed(xml: str) -> list[dict]:
    """Return the feed's entries as {video_id, title, published}, oldest first."""
    try:
        entries = [
            {
                "video_id": e.findtext("yt:videoId", namespaces=NAMESPACES),
                "title": e.findtext("a:title", namespaces=NAMESPACES),
                "published": datetime.fromisoformat(
                    e.findtext("a:published", namespaces=NAMESPACES)
                ),
            }
            for e in ElementTree.fromstring(xml).findall("a:entry", NAMESPACES)
        ]
    except (ElementTree.ParseError, TypeError, ValueError) as e:
        raise StageError(FEED, "feed", f"cannot parse feed: {e}") from e
    return sorted(entries, key=lambda e: e["published"])


def first_tracking_since(entries: list[dict]) -> datetime:
    """Return where tracking starts for a channel seen for the first time: its latest video, or now."""
    return entries[-1]["published"] if entries else datetime.now(UTC)


def select_candidates(
    entries: list[dict], tracking_since: datetime, stored_ids: set[str]
) -> list[dict]:
    """Return the entries published at or after tracking_since that are not stored yet, oldest first."""
    return [
        e
        for e in entries
        if e["published"] >= tracking_since and e["video_id"] not in stored_ids
    ]
