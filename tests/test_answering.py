import pytest

from tldw.answering import link_sources, parse_ask


def test_current_essay_uses_its_own_scope_with_prior_turns() -> None:
    """Keep earlier text as history and take the search scope from this question."""
    question, video_id, history = parse_ask(
        {
            "question": " What happened next? ",
            "context": {"mode": "essay", "video_id": "second"},
            "turns": [{"question": "What happened?", "answer": "They landed."}],
        }
    )

    assert question == "What happened next?"
    assert video_id == "second"
    assert [message.parts[0].content for message in history] == [
        "What happened?",
        "They landed.",
    ]


def test_all_knowledge_has_no_essay_filter() -> None:
    """A title or ID carried by the client does not narrow the global scope."""
    assert parse_ask(
        {
            "question": "Find examples",
            "context": {"mode": "all", "video_id": "first"},
            "turns": [],
        }
    ) == ("Find examples", "", [])


@pytest.mark.parametrize("context", [{"mode": "essay"}, {"mode": "unknown"}, None])
def test_ask_rejects_invalid_scope(context: object) -> None:
    """An incomplete or unknown scope never silently runs a global search."""
    with pytest.raises(ValueError, match="Choose All Knowledge or an essay"):
        parse_ask({"question": "Find examples", "context": context, "turns": []})


def test_link_sources_uses_only_current_search_results() -> None:
    """Convert known citations and reject a marker missing from this search."""
    citations = {"[source:2]": "[Video](https://www.youtube.com/watch?v=test&t=9s)"}

    assert link_sources("They landed [source:2].", citations) == (
        "They landed [Video](https://www.youtube.com/watch?v=test&t=9s)."
    )
    assert link_sources("They landed [source:2] [source:9].", citations) is None
