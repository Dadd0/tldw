import pytest

from tldw.poll import run_poll


def test_poll_exits_silently_when_lock_is_held(tmp_path, monkeypatch, capsys):
    fcntl = pytest.importorskip("fcntl")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", "")

    with (tmp_path / ".poll.lock").open("a") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert run_poll() == 0

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
