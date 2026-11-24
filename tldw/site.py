"""Serve the private essay site, chat, and video submission form."""

import re
import subprocess
from datetime import UTC, datetime, timedelta
from math import ceil
from pathlib import Path
from urllib.parse import urlsplit

import requests
from markdown_it import MarkdownIt
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import QueryParams
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

from tldw.answering import build_ask
from tldw.config import load_settings
from tldw.db import existing_essay_ids, get_essay, list_essays

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


def submission_title(video_id: str) -> str:
    """Look up the public title with a short timeout, falling back to the video ID."""
    try:
        response = requests.get(
            "https://www.youtube.com/oembed",
            params={
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "format": "json",
            },
            timeout=0.75,
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException:
        return video_id
    title = data.get("title") if isinstance(data, dict) else None
    return title.strip() if isinstance(title, str) and title.strip() else video_id


def start_transcription(video_id: str, project_dir: Path) -> subprocess.Popen:
    """Start the CLI in its own session and append both output streams to the log."""
    video = f"https://www.youtube.com/watch?v={video_id}"
    with (project_dir / "transcribe.log").open("ab") as log:
        return subprocess.Popen(
            ["uv", "run", "main.py", "transcribe", video],
            cwd=project_dir,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )


def submission_rows(
    submissions: dict, published: set[str], now: datetime
) -> list[dict]:
    """Return unpublished submissions newest first and discard finished entries."""
    rows = []
    for video_id, entry in list(submissions.items()):
        code = entry["process"].poll()
        if code is not None:
            if (
                code == 0
                or video_id in published
                or now - entry.setdefault("failed_at", now) >= timedelta(days=1)
            ):
                del submissions[video_id]
                continue
        if video_id not in published:
            rows.append(
                {
                    "video_id": video_id,
                    "title": entry["title"],
                    "submitted_at": entry["submitted_at"],
                    "processing": code is None,
                }
            )
    return sorted(rows, key=lambda row: row["submitted_at"], reverse=True)


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


def render_essay(markdown: MarkdownIt, body: str) -> tuple[str, list[dict]]:
    """Render an essay body with an id on each h2 and return its table of contents."""
    tokens = markdown.parse(body)
    toc = []
    for heading, inline in zip(tokens, tokens[1:]):
        if heading.type != "heading_open" or heading.tag != "h2":
            continue
        text = "".join(
            t.content for t in inline.children if t.type in ("text", "code_inline")
        )
        # The prefix keeps headings from taking page ids such as "chat".
        base = "section-" + (re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "x")
        slug, n = base, 1
        while any(row["id"] == slug for row in toc):
            n += 1
            slug = f"{base}-{n}"
        heading.attrSet("id", slug)
        toc.append({"id": slug, "text": text.strip()})
    return markdown.renderer.render(tokens, markdown.options, {}), toc


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
    # shortcut: forgotten on restart, persist submissions if they must survive a site restart.
    submissions: dict[str, dict] = {}

    async def index(request: Request) -> Response:
        """Render one page of essays."""
        try:
            page = int(request.query_params.get("p", "1"))
        except ValueError:
            raise HTTPException(404) from None

        offset = (page - 1) * PAGE_SIZE
        if not 0 <= offset < 2**63:
            raise HTTPException(404)

        pending = []
        now = datetime.now(UTC)
        if page == 1 and submissions:
            published = await run_in_threadpool(
                existing_essay_ids, db_url, list(submissions)
            )
            pending = submission_rows(submissions, published, now)
        essays = await run_in_threadpool(
            list_essays, db_url, limit=PAGE_SIZE + 1, offset=offset
        )
        # An essay may have been published between the two reads.
        listed_ids = {essay["video_id"] for essay in essays}
        pending = [row for row in pending if row["video_id"] not in listed_ids]
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "pending": pending,
                "processing": any(row["processing"] for row in pending),
                "essays": essays[:PAGE_SIZE],
                "first_rank": offset + 1,
                "next_page": page + 1 if len(essays) > PAGE_SIZE else None,
                "now": now,
            },
        )

    def essay_page(request: Request) -> Response:
        """Render one essay or return 404 if it does not exist."""
        essay = get_essay(db_url, request.path_params["video_id"])
        if essay is None:
            raise HTTPException(404)

        body_html, toc = render_essay(markdown, essay["body"])
        return templates.TemplateResponse(
            request,
            "essay.html",
            {
                "essay": essay,
                "body_html": body_html,
                "toc": toc,
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
        now = datetime.now(UTC)
        submission_rows(submissions, set(), now)
        entry = submissions.get(video_id)
        if entry and entry["process"].poll() is None:
            return RedirectResponse("/submit?started=1", status_code=303)
        try:
            process = start_transcription(video_id, package_dir.parent)
        except OSError:
            return page(
                500,
                video=value,
                error="Couldn’t start transcription. Check that uv is available and transcribe.log is writable.",
            )
        entry = {"process": process, "submitted_at": now, "title": video_id}
        submissions[video_id] = entry
        entry["title"] = await run_in_threadpool(submission_title, video_id)
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
