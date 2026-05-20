"""GitLab API client factory.

Reads `GITLAB_URL` and `GITLAB_TOKEN` from the environment and returns a
configured `gitlab.Gitlab` instance. Every command should obtain its
client via `get_client()` so credential handling is in one place.
"""

from __future__ import annotations

import os

import gitlab


class MissingCredentials(RuntimeError):
    """Raised when GITLAB_URL or GITLAB_TOKEN is not set."""


def get_client(*, url: str | None = None, token: str | None = None) -> gitlab.Gitlab:
    url = url or os.environ.get("GITLAB_URL")
    token = token or os.environ.get("GITLAB_TOKEN")
    if not url:
        raise MissingCredentials("GITLAB_URL is not set")
    if not token:
        raise MissingCredentials("GITLAB_TOKEN is not set")
    return gitlab.Gitlab(url, private_token=token)
