from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from yt_smart_transcribe.errors import FEED, StageError
from yt_smart_transcribe.feed import first_tracking_since, parse_feed, select_candidates

ENTRIES = parse_feed((Path(__file__).parent / "feed.xml").read_text())


def test_parse_returns_all_entries_oldest_first():
    assert len(ENTRIES) == 15
    assert ENTRIES[-1] == {
        "video_id": "olpH5z9Aue4",
        "title": "Considerazioni su GTA6 e sulla PS5 per l’inferenza locale ",
        "published": datetime(2026, 11, 16, 18, 23, 57, tzinfo=UTC),
    }
    assert [e["published"] for e in ENTRIES] == sorted(e["published"] for e in ENTRIES)


def test_parse_empty_feed():
    assert parse_feed('<feed xmlns="http://www.w3.org/2005/Atom"></feed>') == []


@pytest.mark.parametrize(
    "xml",
    [
        "not xml",
        '<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>no date</title></entry></feed>',
        '<feed xmlns="http://www.w3.org/2005/Atom"><entry><published>yesterday</published></entry></feed>',
    ],
)
def test_parse_rejects_broken_feed(xml):
    with pytest.raises(StageError) as e:
        parse_feed(xml)
    assert e.value.code == FEED


def test_first_sight_tracks_from_latest_entry():
    since = first_tracking_since(ENTRIES)
    assert since == ENTRIES[-1]["published"]
    assert select_candidates(ENTRIES, since, set()) == [ENTRIES[-1]]


def test_first_sight_of_empty_feed_tracks_from_now():
    assert datetime.now(UTC) - first_tracking_since([]) < timedelta(seconds=5)


def test_candidates_are_at_or_after_tracking_since_and_not_stored():
    since = ENTRIES[-3]["published"]
    assert select_candidates(ENTRIES, since, set()) == ENTRIES[-3:]
    assert select_candidates(ENTRIES, since, {ENTRIES[-2]["video_id"]}) == [ENTRIES[-3], ENTRIES[-1]]
    assert select_candidates(ENTRIES, since, {e["video_id"] for e in ENTRIES}) == []
