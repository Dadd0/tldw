"""Command line entry point: runs one command and turns a StageError into the exit code."""

import argparse
import sys

from yt_smart_transcribe.config import load_settings
from yt_smart_transcribe.errors import StageError
from yt_smart_transcribe.pipeline import process_video


def main() -> int:
    parser = argparse.ArgumentParser(description="Store transcripts of YouTube videos in Supabase.")
    commands = parser.add_subparsers(dest="command", required=True)
    transcribe = commands.add_parser("transcribe", help="transcribe one video, replacing any stored transcript")
    transcribe.add_argument("video", help="video ID or URL")
    args = parser.parse_args()

    try:
        settings = load_settings()
    except StageError as e:
        print(f"FAILED {e.stage}: {e}", file=sys.stderr)
        return e.code
    try:
        process_video(args.video, settings, skip_short=False)
    except StageError as e:
        print(f"FAILED {args.video} {e.stage}: {e}", file=sys.stderr)
        return e.code
    return 0


if __name__ == "__main__":
    sys.exit(main())
