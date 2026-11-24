"""Serve the private essay site, chat, and video submission form."""

import re
import subprocess
from datetime import UTC, datetime
from math import ceil
from pathlib import Path
from urllib.parse import urlsplit

from markdown_it import MarkdownIt
from starlette.applications import Starlette
from starlette.datastructures import QueryParams
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

from tldw.answering import build_ask
from tldw.config import load_settings
from tldw.db import get_essay, list_essays

PAGE_SIZE = 30
VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}")


def submitted_video_id(value: str) -> str | None:
    """Extract one video ID from a bare ID or a supported YouTube video URL."""
    value = value.strip()
    if VIDEO_ID.fullmatch(value):
        return value
    if re.search(r"[\s\\\x00-\x1f\x7f]", value):
        return None
    try:
        url = urlsplit(value)
    except ValueError:
        return None
    if url.scheme not in {"http", "https"}:
        return None
    host = url.netloc.lower().removesuffix(":443" if url.scheme == "https" else ":80")
    if host == "youtu.be":
        candidate = url.path.removeprefix("/").removesuffix("/")
    elif host in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
        if url.path == "/watch":
            ids = QueryParams(url.query).getlist("v")
            candidate = ids[0] if len(ids) == 1 else ""
        elif url.path.startswith(("/shorts/", "/live/")):
            candidate = url.path.split("/", 2)[2].removesuffix("/")
        else:
            return None
    else:
        return None
    return candidate if VIDEO_ID.fullmatch(candidate) else None


def start_transcription(video_id: str, project_dir: Path) -> None:
    """Start the CLI in its own session and append both output streams to the log."""
    video = f"https://www.youtube.com/watch?v={video_id}"
    with (project_dir / "transcribe.log").open("ab") as log:
        subprocess.Popen(
            ["uv", "run", "main.py", "transcribe", video],
            cwd=project_dir,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )


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
    settings = load_settings()
    db_url = settings["SUPABASE_DB_URL"]
    markdown = MarkdownIt("commonmark", {"html": False})
    package_dir = Path(__file__).resolve().parent
    templates = Jinja2Templates(directory=package_dir / "templates")
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

    def ask_page(request: Request) -> Response:
        """Render the full-page chat."""
        return templates.TemplateResponse(request, "ask.html", {"mode": "ask"})

    async def submit(request: Request) -> Response:
        """Show the submission form or start a video from a same-origin form POST."""

        def page(status: int = 200, **fields: str | bool) -> Response:
            """Render the form, its error, or the confirmation."""
            return templates.TemplateResponse(
                request, "submit.html", {"mode": "submit", **fields}, status_code=status
            )

        if request.method != "POST":
            return page(started=request.query_params.get("started") == "1")
        host = request.headers.get("host", "").lower()
        if not re.fullmatch(
            r"(?:localhost|127\.0\.0\.1|\[::1\])(?::[0-9]+)?", host
        ) or (request.headers.get("origin") != f"{request.url.scheme}://{host}"):
            return page(403, error="Submit videos from the form on this site.")
        if (
            request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
            != "application/x-www-form-urlencoded"
        ):
            return page(415, error="Send the video using the submission form.")
        values = QueryParams(await request.body()).getlist("video")
        value = values[0] if len(values) == 1 else ""
        video_id = submitted_video_id(value)
        if video_id is None:
            return page(
                400,
                video=value,
                error="Enter a YouTube video URL or an 11-character video ID.",
            )
        try:
            start_transcription(video_id, package_dir.parent)
        except OSError:
            return page(
                500,
                video=value,
                error="Couldn’t start transcription. Check that uv is available and transcribe.log is writable.",
            )
        return RedirectResponse("/submit?started=1", status_code=303)

    return Starlette(
        routes=[
            Route("/", index, name="index"),
            Route("/essay/{video_id}", essay_page, name="essay"),
            Route("/ask", ask_page, name="ask"),
            Route("/submit", submit, methods=["GET", "POST"], name="submit"),
            Route("/api/ask", build_ask(settings), methods=["POST"]),
            Mount(
                "/static", StaticFiles(directory=package_dir / "static"), name="static"
            ),
        ]
    )
