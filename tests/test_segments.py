from tldw.segments import build_segments


def test_groups_consecutive_words_by_speaker() -> None:
    """Keep each turn separate, including when the first speaker returns."""
    words = [
        {"word": "Ciao", "start": 0.0, "end": 0.5, "speaker": 0},
        {"word": "Luca", "start": 0.5, "end": 1.0, "speaker": 0},
        {"word": "Ciao", "start": 1.0, "end": 1.5, "speaker": 1},
        {"word": "Arrivederci", "start": 2.0, "end": 2.5, "speaker": 0},
    ]

    segments = build_segments([words], 300)

    assert [segment["speaker"] for segment in segments] == ["0.0", "0.1", "0.0"]
    assert [segment["text"] for segment in segments] == [
        "Ciao Luca",
        "Ciao",
        "Arrivederci",
    ]
    assert segments[0]["start_seconds"] == 0.0
    assert segments[0]["end_seconds"] == 1.0


def test_splits_a_turn_after_200_words() -> None:
    """Put the 201st word in a new segment."""
    words = [
        {"word": f"parola{i}", "start": i, "end": i + 1, "speaker": 0}
        for i in range(201)
    ]

    first, second = build_segments([words], 300)

    assert first["word_count"] == 200
    assert second["word_count"] == 1
    assert second["text"] == "parola200"
    assert first["end_seconds"] == second["start_seconds"] == 200


def test_keeps_video_time_across_a_silent_chunk() -> None:
    """Count silent chunks in the timestamps and number only actual segments."""
    word = {"word": "Ciao", "start": 2.0, "end": 2.5, "speaker": 0}

    segments = build_segments([[word], [], [word]], 300)

    assert [segment["idx"] for segment in segments] == [0, 1]
    assert [segment["speaker"] for segment in segments] == ["0.0", "2.0"]
    assert [segment["start_seconds"] for segment in segments] == [2.0, 602.0]
    assert [segment["end_seconds"] for segment in segments] == [2.5, 602.5]


def test_empty_chunk_produces_no_segments() -> None:
    """Return an empty list when the only chunk has no words."""
    assert build_segments([[]], 300) == []
