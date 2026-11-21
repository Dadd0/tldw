"""Command line entry point: runs one command and turns a StageError into the exit code."""

import argparse
import sys
import re

from tldw.config import load_settings
from tldw.errors import StageError
from tldw.pipeline import process_video, write_essay
from tldw.poll import run_poll


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Turn YouTube videos into essays and a searchable Q&A."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    transcribe = commands.add_parser(
        "transcribe", help="transcribe one video, replacing any stored transcript"
    )
    transcribe.add_argument("video", help="video ID or URL")
    transcribe.add_argument(
        "--language",
        type=str.lower,
        metavar="CODE",
        help="two-letter language code (e.g. it)",
    )
    transcribe.add_argument(
        "--max-minutes",
        type=int,
        metavar="N",
        help="preview up to N minutes from the start of the video",
    )
    commands.add_parser("poll", help="transcribe new videos from followed channels")
    write = commands.add_parser("write", help="write or replace one essay")
    write.add_argument("video", metavar="video-id", help="stored YouTube video ID")
    args = parser.parse_args()

    try:
        if args.command == "poll":
            return run_poll()

        if (
            args.command == "transcribe"
            and args.language is not None
            and re.fullmatch(r"[a-z]{2}", args.language) is None
        ):
            transcribe.error("--language must be a two-letter code (e.g. it)")

        settings = load_settings()
    except StageError as e:
        print(f"FAILED {e.stage}: {e}", file=sys.stderr)
        return e.code
    try:
        if args.command == "write":
            write_essay(args.video, settings, replace=True)
        else:
            process_video(
                args.video,
                settings,
                language=args.language,
                max_minutes=args.max_minutes,
            )
    except StageError as error:
        message = str(error)
        for name in ("SUPABASE_DB_URL", "OPENROUTER_API_KEY"):
            message = message.replace(settings[name], "[redacted]")
        message = " ".join(message.splitlines())
        print(f"FAILED {args.video} {error.stage}: {message}", file=sys.stderr)
        return error.code
    return 0


if __name__ == "__main__":
    sys.exit(main())
