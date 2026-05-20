import pytest

from gitlab_admin import client


def test_get_client_returns_authenticated_client(monkeypatch):
    monkeypatch.setenv("GITLAB_URL", "https://gitlab.example.com")
    monkeypatch.setenv("GITLAB_TOKEN", "abc123")
    gl = client.get_client()
    assert gl.url == "https://gitlab.example.com"
    assert gl.private_token == "abc123"


def test_get_client_missing_url_raises(monkeypatch):
    monkeypatch.delenv("GITLAB_URL", raising=False)
    monkeypatch.setenv("GITLAB_TOKEN", "abc123")
    with pytest.raises(client.MissingCredentials) as exc:
        client.get_client()
    assert "GITLAB_URL" in str(exc.value)


def test_get_client_missing_token_raises(monkeypatch):
    monkeypatch.setenv("GITLAB_URL", "https://gitlab.example.com")
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)
    with pytest.raises(client.MissingCredentials) as exc:
        client.get_client()
    assert "GITLAB_TOKEN" in str(exc.value)
