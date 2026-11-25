import asyncio
import json

import pytest
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.test import TestModel as LocalModel

from tldw.answering import parse_ask, stream_answer


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


@pytest.mark.parametrize(
    ("output", "html"),
    [
        ("<b>Moon</b>", "<p>&lt;b&gt;Moon&lt;/b&gt;</p>\n"),
        (
            '**They landed** in *"the Sea of Tranquility"*.',
            "<p><strong>They landed</strong> in <em>&quot;the Sea of Tranquility&quot;</em>.</p>\n",
        ),
    ],
)
def test_stream_answer(output: str, html: str) -> None:
    """Send plain deltas before the answer rendered as escaped Markdown."""
    agent = Agent(LocalModel(custom_output_text=output), deps_type=dict)

    @agent.tool
    def search(ctx: RunContext[dict]) -> str:
        """Return one segment from a local fixture."""
        return "They landed."

    async def collect() -> list[dict]:
        """Decode the records emitted by the real agent loop."""
        return [
            json.loads(line) async for line in stream_answer(agent, "Moon?", "", [])
        ]

    *partials, terminal = asyncio.run(collect())
    assert len(partials) > 1
    assert "".join(part["delta"] for part in partials) == output
    assert terminal == {"answer": output, "html": html}
