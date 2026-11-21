import pytest

from tldw.config import load_channels, load_settings
from tldw.errors import CONFIG, StageError

ENV = {
    "OPENROUTER_API_KEY": "key",
    "SUPABASE_DB_URL": "postgresql://user:secret@host:5432/postgres",
    "ESSAY_MODEL_ID": "essay-model",
    "CHAT_MODEL_ID": "chat-model",
}
CHANNEL = "UC" + "a" * 22


def test_settings_loads_required_keys():
    assert load_settings(ENV | {"UNUSED": "ignored"}) == ENV


@pytest.mark.parametrize(
    "env",
    [
        {k: v for k, v in ENV.items() if k != "SUPABASE_DB_URL"},
        {k: v for k, v in ENV.items() if k != "ESSAY_MODEL_ID"},
        {k: v for k, v in ENV.items() if k != "CHAT_MODEL_ID"},
        ENV | {"OPENROUTER_API_KEY": ""},
    ],
)
def test_settings_rejects_missing_or_empty(env):
    with pytest.raises(StageError) as e:
        load_settings(env)
    assert e.value.code == CONFIG


def test_channels_loads_optional_language_in_file_order(tmp_path):
    other_channel = "UC" + "b" * 22
    path = tmp_path / "channels.txt"
    path.write_text(
        f"# followed\n\n{CHANNEL}  # name\n{other_channel} IT\n{CHANNEL} de\n"
    )
    assert load_channels(path) == [(CHANNEL, None), (other_channel, "it")]


@pytest.mark.parametrize(
    "content",
    [
        "not-a-channel",
        CHANNEL + "x",
        f"{CHANNEL} ita",
        f"{CHANNEL} 1t",
        f"{CHANNEL} it extra",
    ],
)
def test_channels_rejects_invalid_line(tmp_path, content):
    path = tmp_path / "channels.txt"
    path.write_text(f"# followed\n{content}\n")
    with pytest.raises(StageError, match="line 2") as e:
        load_channels(path)
    assert e.value.code == CONFIG


def test_channels_rejects_missing_file(tmp_path):
    with pytest.raises(StageError) as e:
        load_channels(tmp_path / "nope.txt")
    assert e.value.code == CONFIG
