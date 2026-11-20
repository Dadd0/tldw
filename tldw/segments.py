"""Builds transcript segments from timestamped words."""

from itertools import batched, groupby

MAX_SEGMENT_WORDS = 200


def build_segments(chunks: list[list[dict]], chunk_seconds: int) -> list[dict]:
    """Group consecutive words by speaker and convert their times to video time."""
    segments = []
    for chunk_index, words in enumerate(chunks):
        offset = chunk_index * chunk_seconds
        for speaker, speaker_words in groupby(words, key=lambda word: word["speaker"]):
            for batch in batched(speaker_words, MAX_SEGMENT_WORDS):
                segments.append(
                    {
                        "idx": len(segments),
                        "start_seconds": offset + batch[0]["start"],
                        "end_seconds": offset + batch[-1]["end"],
                        "speaker": f"{chunk_index}.{speaker}",
                        "text": " ".join(word["word"] for word in batch),
                        "word_count": len(batch),
                    }
                )
    return segments
