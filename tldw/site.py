"""Serve the private essay index and individual essays."""

from datetime import UTC, datetime
from math import ceil
from pathlib import Path

from markdown_it import MarkdownIt
from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route
from starlette.templating import Jinja2Templates

from tldw.config import load_settings
from tldw.db import get_essay, list_essays

PAGE_SIZE = 30
CHAT_URL = "http://localhost:7932"


def reading_time(body: str) -> int:
    """Return the reading time in whole minutes, rounded up."""
    return ceil(len(body.split()) / 230)


def format_duration(seconds: int) -> str:
    """Format the video duration in hours, minutes, or seconds."""
    hours, minutes = divmod(seconds // 60, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m"
    return f"{seconds}s"


def format_age(date: datetime, now: datetime) -> str:
    """Format the elapsed time since the video's display date."""
    seconds = max(0, int((now - date).total_seconds()))
    for unit, unit_seconds in (("day", 86_400), ("hour", 3_600), ("minute", 60)):
        amount = seconds // unit_seconds
        if amount:
            suffix = "" if amount == 1 else "s"
            return f"{amount} {unit}{suffix} ago"
    return "just now"


def build_site() -> Starlette:
    """Build the essay site using the project's settings."""
    db_url = load_settings()["SUPABASE_DB_URL"]
    markdown = MarkdownIt("commonmark", {"html": False})
    templates = Jinja2Templates(directory=Path(__file__).with_name("templates"))
    templates.env.globals["chat_url"] = CHAT_URL
    templates.env.filters.update(
        reading_time=reading_time,
        format_duration=format_duration,
        format_age=format_age,
    )

    def index(request: Request) -> Response:
        """Render one page of essays."""
        try:
            page = int(request.query_params.get("p", "1"))
        except ValueError:
            raise HTTPException(404) from None

        offset = (page - 1) * PAGE_SIZE
        if not 0 <= offset < 2**63:
            raise HTTPException(404)

        essays = list_essays(db_url, limit=PAGE_SIZE + 1, offset=offset)
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "essays": essays[:PAGE_SIZE],
                "first_rank": offset + 1,
                "next_page": page + 1 if len(essays) > PAGE_SIZE else None,
                "now": datetime.now(UTC),
            },
        )

    def essay_page(request: Request) -> Response:
        """Render one essay or return 404 if it does not exist."""
        essay = get_essay(db_url, request.path_params["video_id"])
        if essay is None:
            raise HTTPException(404)

        return templates.TemplateResponse(
            request,
            "essay.html",
            {
                "essay": essay,
                "body_html": markdown.render(essay["body"]),
                "now": datetime.now(UTC),
            },
        )

    return Starlette(
        routes=[
            Route("/", index, name="index"),
            Route("/essay/{video_id}", essay_page, name="essay"),
        ]
    )
