import asyncio
import json

import pytest
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.test import TestModel as LocalModel

from tldw.answering import parse_ask, stream_answer, strip_citations


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
    with pytest.raises(ValueError, match="Context must be all videos or one essay"):
        parse_ask({"question": "Find examples", "context": context, "turns": []})


def test_strip_citations_uses_only_current_search_results() -> None:
    """Drop known citations and reject answers with missing or unknown markers."""
    citations = {"[source:1]", "[source:2]"}

    assert strip_citations("They landed [source:2].", citations) == "They landed."
    assert strip_citations("Both [source:1][source:2].", citations) == "Both."
    assert strip_citations("They landed.", citations) is None
    assert strip_citations("They landed [source:2] [source:9].", citations) is None


@pytest.mark.parametrize(
    ("output", "video_id", "field", "expected"),
    [
        (
            "<b>Moon</b> [source:1]",
            "",
            "html",
            "<p>&lt;b&gt;Moon&lt;/b&gt;</p>\n",
        ),
        (
            "Unknown [source:9]",
            "",
            "error",
            "Couldn't verify the answer's sources. Try again.",
        ),
        (
            "NO_EVIDENCE",
            "moon",
            "answer",
            "I couldn't find relevant evidence in this essay.",
        ),
        (
            "NO_EVIDENCE",
            "",
            "answer",
            "I couldn't find relevant evidence in the collection.",
        ),
        (
            "No relevant transcript segments found.\n\nNO_EVIDENCE",
            "",
            "answer",
            "I couldn't find relevant evidence in the collection.",
        ),
    ],
)
def test_stream_answer(output: str, video_id: str, field: str, expected: str) -> None:
    """Send plain deltas before the cited, HTML-escaped answer or source error."""
    agent = Agent(LocalModel(custom_output_text=output), deps_type=dict)

    @agent.tool
    def cite(ctx: RunContext[dict]) -> str:
        """Return one source from a local fixture."""
        ctx.deps["citations"].add("[source:1]")
        return "[source:1]"

    async def collect() -> list[dict]:
        """Decode the records emitted by the real agent loop."""
        return [
            json.loads(line)
            async for line in stream_answer(agent, "Moon?", video_id, [])
        ]

    *partials, terminal = asyncio.run(collect())
    assert len(partials) > 1
    assert "".join(part["delta"] for part in partials) == output
    assert terminal[field] == expected
