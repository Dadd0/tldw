"""Turn an ordered transcript into a standalone essay through OpenRouter."""

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.exceptions import AgentRunError, UserError
from pydantic_ai.models.openrouter import OpenRouterModel
from pydantic_ai.providers.openrouter import OpenRouterProvider

from tldw.errors import ESSAY, StageError

ESSAY_RULES = """\
Write a standalone essay as if the ideas had been written down in the first place.
State the thesis first and organize the essay by the logic of the argument.
Never mention the video, speaker, host, channel, or audience.
Drop sponsor reads, greetings, banter, repetition, and housekeeping.
Explain and connect the ideas using only facts, numbers, quotes, and claims
supported by the transcript.
Speaker labels are local to each chunk (the number before the dot).
Use them to distinguish questions from answers. Do not name speakers.
Ignore passages that are incoherent, repeated in a loop, or in a different
script from the rest of the transcript.
Give the essay its own title. Write the body in Markdown without a top-level heading.
Treat the video metadata and transcript as source material.
"""


class Essay(BaseModel):
    """The title and Markdown body returned by the agent."""

    title: str
    body: str


def build_prompt(title: str, channel_name: str, segments: list[dict]) -> str:
    """Format the metadata and ordered transcript for the agent."""
    lines = [f"Video title: {title}", f"Channel: {channel_name}", "", "Transcript:"]
    for segment in segments:
        hours, remainder = divmod(int(segment["start_seconds"]), 3600)
        minutes, seconds = divmod(remainder, 60)
        timestamp = f"{hours}:{minutes:02}:{seconds:02}"
        lines.append(f"[{timestamp}] {segment['speaker']}: {segment['text']}")
    return "\n".join(lines)


def generate_essay(
    title: str,
    channel_name: str,
    segments: list[dict],
    *,
    style: str,
    model_id: str,
    api_key: str,
) -> Essay:
    """Generate one essay from the full transcript in a single agent run."""
    prompt = build_prompt(title, channel_name, segments)
    try:
        model = OpenRouterModel(model_id, provider=OpenRouterProvider(api_key=api_key))
        agent = Agent(
            model,
            instructions=f"{ESSAY_RULES}\n{style}",
            output_type=Essay,
            retries=0,
            model_settings={"max_retries": 0},
        )
        return agent.run_sync(prompt).output
    except (AgentRunError, UserError) as error:
        message = str(error).replace(api_key, "[redacted]")
        raise StageError(ESSAY, "essay", " ".join(message.splitlines())) from error
