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
