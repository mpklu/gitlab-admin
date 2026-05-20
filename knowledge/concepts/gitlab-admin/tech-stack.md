---
title: Tech stack and runtime conventions
type: concept
area: gitlab-admin
updated: 2026-05-19
status: thin
load_bearing: true
---

## What this is

The technical foundation of `gitlab-admin`: language, dependencies,
project layout, and the conventions every command follows.

- **Language:** Python 3.11+.
- **GitLab client:** `python-gitlab` (PyPI). Battle-tested, covers
  the admin endpoints we need, and matches the synchronous, script-shaped
  style the team will write.
- **Test runner:** `pytest`. HTTP stubbing via `responses` (dev dep).
- **Cache:** stdlib `sqlite3`. No ORM.
- **Packaging:** `pyproject.toml` defining the `gitlab_admin` package
  with dev extras. Installed editable for local work (`pip install -e ".[dev]"`).
  No published wheels; not a PyPI release.

## Why this shape, not the alternatives

Python beats shell here because admin operations need real data
structures (filtering, joins across users/groups/projects, CSV/JSON
output for audits). It beats Node and Go because the team already
reads Python comfortably and we are not chasing a single-binary
distribution target. `python-gitlab` beats hand-rolled `requests`
because authentication, pagination, and error mapping are already
solved for the admin endpoints.

## Folder layout (commitment)

```text
gitlab_admin/
  __init__.py
  client.py            # constructs the python-gitlab client from env vars
  commands/
    __init__.py
    <command>.py       # one module per command; exposes main()
tests/
  test_<command>.py
```

Every command module exposes a `main(argv: list[str] | None = None) -> int`
function so it is runnable as `python -m gitlab_admin.<command>` and easy
to test.

## What would invalidate this article

Switching language, replacing `python-gitlab` with a different client,
or moving to a CLI framework with subcommand routing (Click/Typer) instead
of `python -m`. Any of these changes the daily ergonomics enough that
the article must be rewritten.

## First commitments

- `gitlab_admin/client.py` exposes a `get_client()` factory reading
  `GITLAB_URL` and `GITLAB_TOKEN` from the environment.
- Commands return integer exit codes from `main()`.
- A `--dry-run` flag is mandatory on any command that performs writes.
- `gitlab_admin/browse/` follows the layered shape described in
  `browse-command.md`: network confined to `fetch.py`, pure model layer,
  thin renderers.
