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


def test_selected_text_uses_the_originating_essay_scope() -> None:
    """Use the excerpt to interpret the question within its essay transcript."""
    question, video_id, history = parse_ask(
        {
            "question": " Explain this. ",
            "context": {
                "mode": "selected",
                "video_id": "first",
                "selected_text": " Shared weights save memory. ",
            },
            "turns": [{"question": "What is looping?", "answer": "Repeating layers."}],
        }
    )

    assert (
        question
        == "Question: Explain this.\nSelected essay passage: 'Shared weights save memory.'"
    )
    assert video_id == "first"
    assert len(history) == 2


@pytest.mark.parametrize(
    "context",
    [
        {"mode": "selected", "video_id": "first"},
        {"mode": "selected", "video_id": "first", "selected_text": "  "},
        {"mode": "selected", "video_id": "first", "selected_text": 1},
        {"mode": "selected", "selected_text": "A passage"},
    ],
)
def test_selected_text_requires_an_essay_and_a_passage(context: dict) -> None:
    """Incomplete selected context never falls back to another scope."""
    with pytest.raises(ValueError, match="Choose an essay and select a passage"):
        parse_ask({"question": "Explain this", "context": context, "turns": []})


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
