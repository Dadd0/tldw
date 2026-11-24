from shutil import which

import pytest

from tldw.audio import split_mp3
from tldw.errors import TRANSCRIPTION, StageError


def test_split_reports_ffmpeg_launch_failure(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", str(tmp_path))

    with pytest.raises(StageError, match="cannot start ffmpeg") as exc:
        split_mp3(tmp_path / "audio.mp3")

    assert exc.value.code == TRANSCRIPTION
    assert exc.value.stage == "chunking"


def test_split_reports_ffmpeg_exit_failure(tmp_path):
    if which("ffmpeg") is None:
        pytest.skip("ffmpeg is not installed")

    with pytest.raises(StageError) as exc:
        split_mp3(tmp_path / "missing.mp3")

    assert exc.value.code == TRANSCRIPTION
    assert exc.value.stage == "chunking"
