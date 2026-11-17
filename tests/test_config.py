import pytest

from yt_smart_transcribe.config import load_channels, load_settings
from yt_smart_transcribe.errors import CONFIG, StageError

ENV = {
    "OPENROUTER_API_KEY": "key",
    "TRANSCRIPTION_MODEL_ID": "model",
    "SUPABASE_DB_URL": "postgresql://user:secret@host:5432/postgres",
}
CHANNEL = "UC" + "a" * 22


def test_settings_defaults_and_overrides():
    assert load_settings(ENV) == ENV | {"POLL_INTERVAL_MINUTES": 30, "CHUNK_SECONDS": 3600}
    assert load_settings(ENV | {"CHUNK_SECONDS": "90"})["CHUNK_SECONDS"] == 90


@pytest.mark.parametrize(
    "env",
    [
        {k: v for k, v in ENV.items() if k != "SUPABASE_DB_URL"},
        ENV | {"OPENROUTER_API_KEY": ""},
        ENV | {"CHUNK_SECONDS": "0"},
        ENV | {"POLL_INTERVAL_MINUTES": "ten"},
    ],
)
def test_settings_rejects_missing_or_invalid(env):
    with pytest.raises(StageError) as e:
        load_settings(env)
    assert e.value.code == CONFIG


def test_channels_skips_comments_blanks_and_duplicates(tmp_path):
    path = tmp_path / "channels.txt"
    path.write_text(f"# followed\n\n{CHANNEL}  # name\n{CHANNEL}\n")
    assert load_channels(path) == [CHANNEL]


@pytest.mark.parametrize("content", ["not-a-channel\n", CHANNEL + "x\n"])
def test_channels_rejects_invalid_id(tmp_path, content):
    path = tmp_path / "channels.txt"
    path.write_text(content)
    with pytest.raises(StageError) as e:
        load_channels(path)
    assert e.value.code == CONFIG


def test_channels_rejects_missing_file(tmp_path):
    with pytest.raises(StageError) as e:
        load_channels(tmp_path / "nope.txt")
    assert e.value.code == CONFIG
