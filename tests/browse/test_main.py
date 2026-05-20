import sys
from pathlib import Path

import pytest

from gitlab_admin.browse import __main__ as browse_main


def test_no_cache_exits_1(tmp_path, capsys):
    cache_path = tmp_path / "missing.sqlite"
    rc = browse_main.main(["--cache-path", str(cache_path)])
    captured = capsys.readouterr()
    assert rc == 1
    assert "No cache" in captured.err


def test_text_render_from_fixture(fixture_db, capsys):
    rc = browse_main.main(["--cache-path", str(fixture_db)])
    captured = capsys.readouterr()
    assert rc == 0
    assert "platform" in captured.out
    assert "auth-svc" in captured.out


def test_html_and_json_mutually_exclusive(fixture_db, capsys):
    with pytest.raises(SystemExit):
        browse_main.main([
            "--cache-path", str(fixture_db),
            "--json", "--html", "/tmp/x.html",
        ])


def test_refresh_without_credentials_exits_3(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("GITLAB_URL", raising=False)
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)
    rc = browse_main.main([
        "--cache-path", str(tmp_path / "x.sqlite"),
        "--refresh",
    ])
    captured = capsys.readouterr()
    assert rc == 3
    assert "GITLAB_URL" in captured.err or "GITLAB_TOKEN" in captured.err


def test_env_file_populates_credentials_when_shell_lacks_them(
    tmp_path, monkeypatch
):
    """--env-file should populate GITLAB_URL/GITLAB_TOKEN when the shell
    doesn't already have them. We don't run a refresh (no GitLab to hit);
    we just verify the env vars are set after main() processes the file."""
    monkeypatch.delenv("GITLAB_URL", raising=False)
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)

    env_file = tmp_path / "test.env"
    env_file.write_text(
        "GITLAB_URL=https://from-env-file.example.com\n"
        "GITLAB_TOKEN=token-from-file\n"
    )

    # Use --cache-path to a non-existent file so main exits 1 cleanly after
    # processing --env-file. We just need main() to run far enough to call
    # load_dotenv.
    browse_main.main([
        "--cache-path", str(tmp_path / "nope.sqlite"),
        "--env-file", str(env_file),
    ])

    import os
    assert os.environ.get("GITLAB_URL") == "https://from-env-file.example.com"
    assert os.environ.get("GITLAB_TOKEN") == "token-from-file"


def test_env_file_does_not_override_shell_env(tmp_path, monkeypatch):
    """Shell env vars must win over .env file values."""
    monkeypatch.setenv("GITLAB_URL", "https://shell-wins.example.com")
    monkeypatch.setenv("GITLAB_TOKEN", "shell-token")

    env_file = tmp_path / "loses.env"
    env_file.write_text(
        "GITLAB_URL=https://file-loses.example.com\n"
        "GITLAB_TOKEN=file-token\n"
    )

    browse_main.main([
        "--cache-path", str(tmp_path / "nope.sqlite"),
        "--env-file", str(env_file),
    ])

    import os
    assert os.environ.get("GITLAB_URL") == "https://shell-wins.example.com"
    assert os.environ.get("GITLAB_TOKEN") == "shell-token"
