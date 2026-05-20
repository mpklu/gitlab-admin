# GitLab Org Browser — Foundation (Plan 1 of 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the `gitlab_admin.browse` foundation: cache, model, fetch, text renderer, JSON renderer, and CLI scaffold. End state: `python -m gitlab_admin.browse [--refresh] [--json] [--group X] [--owner U] [--stale-days N] [--no-archived]` works against a real self-hosted GitLab instance.

**Architecture:** Single Python package `gitlab_admin/`. The `browse/` sub-package isolates network I/O to `fetch.py`, persists to a local SQLite snapshot via `cache.py`, builds a pure in-memory tree via `model.py`, and ships two renderers — `render_text.py` and `render_json.py` — for this plan. HTML and interactive renderers are Plan 2 and Plan 3.

**Tech Stack:** Python 3.11+, `python-gitlab` (API client), stdlib `sqlite3` (cache), stdlib `argparse` (CLI), `pytest` + `responses` (testing), `pip` + `pyproject.toml` (packaging).

**Spec:** [`docs/superpowers/specs/2026-05-19-gitlab-org-browser-design.md`](../specs/2026-05-19-gitlab-org-browser-design.md). This plan implements §1–§5, §6.1, §6.3, §7 (error paths reachable in this plan), §8, §9, §10, §11 (subset relevant to text/JSON), and §12.

---

## File map

Files this plan creates or modifies:

| File | Responsibility |
| --- | --- |
| `pyproject.toml` | Package metadata, deps, console script |
| `gitlab_admin/__init__.py` | Package marker; exposes `__version__` |
| `gitlab_admin/client.py` | `get_client()` factory from `GITLAB_URL`/`GITLAB_TOKEN` env vars |
| `gitlab_admin/browse/__init__.py` | Sub-package marker |
| `gitlab_admin/browse/__main__.py` | argparse CLI; routes to renderers |
| `gitlab_admin/browse/cache.py` | SQLite schema + read/write functions |
| `gitlab_admin/browse/model.py` | Dataclasses (`Group`, `Project`, `Member`, `Snapshot`) + tree builder + owner derivation |
| `gitlab_admin/browse/fetch.py` | Paginated GitLab API walk; writes to temp DB; atomic replace |
| `gitlab_admin/browse/render_text.py` | In-memory tree → indented stdout |
| `gitlab_admin/browse/render_json.py` | In-memory tree → JSON to stdout |
| `tests/__init__.py` | Test-package marker |
| `tests/conftest.py` | pytest fixtures (`fixture_db`, `tmp_cache`) |
| `tests/build_fixture.py` | Reproducibly generates `tests/fixtures/snapshot.sqlite` |
| `tests/fixtures/snapshot.sqlite` | Checked-in canonical test DB |
| `tests/test_client.py` | Tests for `client.get_client()` |
| `tests/browse/test_cache.py` | Round-trip tests for the cache |
| `tests/browse/test_model.py` | Tree build + owner derivation |
| `tests/browse/test_fetch.py` | HTTP-stubbed sync; pagination, atomic replace, dedup |
| `tests/browse/test_render_text.py` | Golden-file render |
| `tests/browse/test_render_json.py` | JSON shape |
| `tests/browse/test_main.py` | argparse routing + exit codes |
| `tests/browse/fixtures/expected_tree.txt` | Golden file for text renderer |
| `knowledge/concepts/gitlab-admin/purpose-and-scope.md` | Add discovery task family |
| `knowledge/concepts/gitlab-admin/tech-stack.md` | Add `responses` dev dep |
| `knowledge/concepts/gitlab-admin/browse-command.md` | NEW article documenting the browse subsystem |
| `CLAUDE.md` | Add row to article-mapping table |
| `knowledge/log.md` | Append bootstrap entry |
| `knowledge/index.md` | Link new article |

---

## Phase 0 — Project bootstrap

### Task 1: Create `pyproject.toml` and package skeleton

**Files:**
- Create: `pyproject.toml`
- Create: `gitlab_admin/__init__.py`
- Create: `gitlab_admin/browse/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/browse/__init__.py`

- [ ] **Step 1: Create `pyproject.toml`**

Write `pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "gitlab-admin"
version = "0.1.0"
description = "Toolkit for administering a self-hosted GitLab instance"
requires-python = ">=3.11"
dependencies = [
    "python-gitlab>=4.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "responses>=0.24",
]

[tool.setuptools.packages.find]
include = ["gitlab_admin*"]
exclude = ["tests*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Create package markers**

Write `gitlab_admin/__init__.py`:

```python
__version__ = "0.1.0"
```

Write `gitlab_admin/browse/__init__.py`, `tests/__init__.py`, `tests/browse/__init__.py` as empty files.

- [ ] **Step 3: Install in editable mode**

Run: `pip install -e ".[dev]"`
Expected: package installs, `pytest --version` succeeds.

- [ ] **Step 4: Verify**

Run: `python -c "import gitlab_admin; print(gitlab_admin.__version__)"`
Expected: `0.1.0`

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml gitlab_admin/ tests/__init__.py tests/browse/__init__.py
git commit -m "feat: bootstrap gitlab_admin package and dev deps

no knowledge impact: scaffolding only"
```

---

### Task 2: Implement `client.get_client()`

**Files:**
- Create: `gitlab_admin/client.py`
- Create: `tests/test_client.py`

- [ ] **Step 1: Write failing tests**

Write `tests/test_client.py`:

```python
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
```

- [ ] **Step 2: Run tests, verify failure**

Run: `pytest tests/test_client.py -v`
Expected: ImportError or AttributeError (`client.MissingCredentials` undefined).

- [ ] **Step 3: Implement `client.py`**

Write `gitlab_admin/client.py`:

```python
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
```

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/test_client.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add gitlab_admin/client.py tests/test_client.py
git commit -m "feat: add client.get_client() factory with env-var auth

no knowledge impact: tech-stack.md already commits to this shape"
```

---

### Task 3: Seed the `browse-command.md` thin article

The same-task rule says articles land alongside the code they document. Since the first browse code arrives in Task 4, we write a thin article now so subsequent tasks can update it as the surface grows.

**Files:**
- Create: `knowledge/concepts/gitlab-admin/browse-command.md`

- [ ] **Step 1: Write thin article**

Write `knowledge/concepts/gitlab-admin/browse-command.md`:

```markdown
---
title: browse command — org map of the GitLab instance
type: concept
area: gitlab-admin
updated: 2026-05-19
status: thin
load_bearing: true
---

## What this is

`browse` produces a navigable map of every group, subgroup, and project
visible to the admin token on the self-hosted GitLab instance. Three
output renderers — text tree, JSON, HTML report — and an interactive
mode share one fetch/cache/model pipeline. This plan implements text +
JSON; HTML and interactive land in follow-up plans.

## How it's wired

```text
GitLab API
    ↓ (network — only here)
fetch.py
    ↓ (writes via temp + os.replace)
cache.py  →  ~/.cache/gitlab-admin/browse.sqlite
    ↓ (reads)
model.py  →  in-memory Group/Project tree
    ↓
render_text.py  /  render_json.py
```

## Cache

Stored at `~/.cache/gitlab-admin/browse.sqlite` (overridable with
`--cache-path`). Four tables: `snapshot`, `groups`, `projects`, `members`.
Refresh is atomic: write to a temp file in the same directory, then
`os.replace()` over the live file. See the spec at
`docs/superpowers/specs/2026-05-19-gitlab-org-browser-design.md` §4 for
the full schema.

## Owner derivation

The displayed "Owner" for a project is derived, not stored:

1. First direct member with `access_level=50` (Owner) by `user_id` asc.
2. Else, owner of the namespace group (same rule, recursed).
3. Else, the namespace path.

The full member list ships with the model so the squish is a display
convenience, never a truth claim.

## CLI shape (this plan)

```text
python -m gitlab_admin.browse                        # text tree from cache
python -m gitlab_admin.browse --refresh              # re-fetch then text tree
python -m gitlab_admin.browse --json                 # JSON to stdout
python -m gitlab_admin.browse --group platform/services
python -m gitlab_admin.browse --owner kun.lu
python -m gitlab_admin.browse --stale-days 365
python -m gitlab_admin.browse --no-archived
python -m gitlab_admin.browse --cache-path ./snapshot.sqlite
```

Exit codes: 0 success, 1 missing/stale cache, 2 network error during
refresh, 3 auth error, 4 unexpected.

## What would invalidate this article

- A schema change in `cache.py` not reflected in the spec §4 schema.
- A change to owner-derivation rules.
- A new exit code or a change to existing exit-code semantics.
- A new mode flag combination rule.

## First commitments

- All network I/O is in `fetch.py`.
- `model.py` is pure: cache rows in, tree out, no I/O.
- Refresh is atomic-replace; partial state is unreachable.
- `~/.cache/gitlab-admin/browse.sqlite` is the canonical cache path.
```

- [ ] **Step 2: Validate**

Run: `scripts/validate-articles`
Expected: `✅ All 4 article(s) have valid frontmatter.`

- [ ] **Step 3: Commit**

```bash
git add knowledge/concepts/gitlab-admin/browse-command.md
git commit -m "docs: seed thin browse-command article

Living-docs same-task rule: article lands before code so subsequent
tasks can refine it as the surface grows."
```

---

## Phase 1 — Cache layer

### Task 4: Schema + write functions in `cache.py`

**Files:**
- Create: `gitlab_admin/browse/cache.py`
- Modify: `knowledge/concepts/gitlab-admin/browse-command.md` (none — schema already documented)

- [ ] **Step 1: Implement `cache.py`**

Write `gitlab_admin/browse/cache.py`:

```python
"""SQLite cache for the browse subsystem.

Schema in `SCHEMA_SQL`. The cache holds exactly one snapshot at a time;
each refresh overwrites the previous via atomic temp-file replace.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

SCHEMA_VERSION = 1

SCHEMA_SQL = """
CREATE TABLE schema_version (
  version INTEGER NOT NULL
);

CREATE TABLE snapshot (
  id           INTEGER PRIMARY KEY,
  started_at   TEXT NOT NULL,
  completed_at TEXT NOT NULL,
  gitlab_url   TEXT NOT NULL,
  tool_version TEXT NOT NULL
);

CREATE TABLE groups (
  id          INTEGER PRIMARY KEY,
  parent_id   INTEGER REFERENCES groups(id),
  full_path   TEXT NOT NULL UNIQUE,
  name        TEXT NOT NULL,
  visibility  TEXT NOT NULL,
  description TEXT,
  web_url     TEXT NOT NULL,
  created_at  TEXT NOT NULL
);
CREATE INDEX idx_groups_parent ON groups(parent_id);

CREATE TABLE projects (
  id                  INTEGER PRIMARY KEY,
  namespace_group_id  INTEGER REFERENCES groups(id),
  namespace_user_id   INTEGER,
  path_with_namespace TEXT NOT NULL UNIQUE,
  name                TEXT NOT NULL,
  default_branch      TEXT,
  visibility          TEXT NOT NULL,
  archived            INTEGER NOT NULL,
  last_activity_at    TEXT NOT NULL,
  http_url_to_repo    TEXT NOT NULL,
  ssh_url_to_repo     TEXT NOT NULL,
  web_url             TEXT NOT NULL,
  description         TEXT,
  topics              TEXT,
  star_count          INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_projects_namespace ON projects(namespace_group_id);
CREATE INDEX idx_projects_activity  ON projects(last_activity_at DESC);
CREATE INDEX idx_projects_archived  ON projects(archived);

CREATE TABLE members (
  entity_type  TEXT NOT NULL,
  entity_id    INTEGER NOT NULL,
  user_id      INTEGER NOT NULL,
  username     TEXT NOT NULL,
  name         TEXT NOT NULL,
  access_level INTEGER NOT NULL,
  expires_at   TEXT,
  PRIMARY KEY (entity_type, entity_id, user_id)
);
CREATE INDEX idx_members_entity ON members(entity_type, entity_id, access_level DESC);
"""


def default_cache_path() -> Path:
    base = os.environ.get("XDG_CACHE_HOME")
    root = Path(base) if base else Path.home() / ".cache"
    return root / "gitlab-admin" / "browse.sqlite"


@contextmanager
def connect(path: Path) -> Iterator[sqlite3.Connection]:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
    conn.commit()


def read_schema_version(conn: sqlite3.Connection) -> int | None:
    try:
        row = conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
    except sqlite3.OperationalError:
        return None
    return None if row is None else int(row["version"])


@dataclass(frozen=True)
class SnapshotRow:
    started_at: str
    completed_at: str
    gitlab_url: str
    tool_version: str


def write_snapshot(conn: sqlite3.Connection, snap: SnapshotRow) -> int:
    cur = conn.execute(
        "INSERT INTO snapshot (started_at, completed_at, gitlab_url, tool_version) "
        "VALUES (?, ?, ?, ?)",
        (snap.started_at, snap.completed_at, snap.gitlab_url, snap.tool_version),
    )
    return int(cur.lastrowid)


def write_group(conn: sqlite3.Connection, row: dict) -> None:
    conn.execute(
        "INSERT INTO groups (id, parent_id, full_path, name, visibility, "
        "description, web_url, created_at) VALUES "
        "(:id, :parent_id, :full_path, :name, :visibility, :description, "
        ":web_url, :created_at)",
        row,
    )


def write_project(conn: sqlite3.Connection, row: dict) -> None:
    conn.execute(
        "INSERT INTO projects (id, namespace_group_id, namespace_user_id, "
        "path_with_namespace, name, default_branch, visibility, archived, "
        "last_activity_at, http_url_to_repo, ssh_url_to_repo, web_url, "
        "description, topics, star_count) VALUES "
        "(:id, :namespace_group_id, :namespace_user_id, :path_with_namespace, "
        ":name, :default_branch, :visibility, :archived, :last_activity_at, "
        ":http_url_to_repo, :ssh_url_to_repo, :web_url, :description, "
        ":topics, :star_count)",
        row,
    )


def write_member(conn: sqlite3.Connection, row: dict) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO members (entity_type, entity_id, user_id, "
        "username, name, access_level, expires_at) VALUES "
        "(:entity_type, :entity_id, :user_id, :username, :name, "
        ":access_level, :expires_at)",
        row,
    )
```

- [ ] **Step 2: Commit (no tests yet — Task 5 adds them with the read functions)**

```bash
git add gitlab_admin/browse/cache.py
git commit -m "feat(browse): cache schema and write functions

no knowledge impact: schema documented in browse-command.md already"
```

---

### Task 5: Cache read functions + round-trip tests

**Files:**
- Modify: `gitlab_admin/browse/cache.py`
- Create: `tests/conftest.py`
- Create: `tests/browse/test_cache.py`

- [ ] **Step 1: Write failing tests**

Write `tests/conftest.py`:

```python
import sqlite3
from pathlib import Path

import pytest

from gitlab_admin.browse import cache


@pytest.fixture
def tmp_cache(tmp_path: Path) -> Path:
    return tmp_path / "browse.sqlite"


@pytest.fixture
def initialized_conn(tmp_cache: Path) -> sqlite3.Connection:
    with cache.connect(tmp_cache) as conn:
        cache.init_schema(conn)
        yield conn
```

Write `tests/browse/test_cache.py`:

```python
from gitlab_admin.browse import cache


def test_init_schema_sets_version(initialized_conn):
    assert cache.read_schema_version(initialized_conn) == cache.SCHEMA_VERSION


def test_read_schema_version_returns_none_on_empty_db(tmp_cache):
    with cache.connect(tmp_cache) as conn:
        assert cache.read_schema_version(conn) is None


def test_snapshot_round_trip(initialized_conn):
    snap = cache.SnapshotRow(
        started_at="2026-05-19T18:00:00Z",
        completed_at="2026-05-19T18:05:00Z",
        gitlab_url="https://gitlab.example.com",
        tool_version="0.1.0",
    )
    cache.write_snapshot(initialized_conn, snap)
    initialized_conn.commit()
    row = cache.load_latest_snapshot(initialized_conn)
    assert row.gitlab_url == "https://gitlab.example.com"
    assert row.tool_version == "0.1.0"


def test_group_round_trip(initialized_conn):
    cache.write_group(initialized_conn, {
        "id": 1, "parent_id": None, "full_path": "platform",
        "name": "platform", "visibility": "private", "description": None,
        "web_url": "https://gitlab.example.com/groups/platform",
        "created_at": "2026-01-01T00:00:00Z",
    })
    initialized_conn.commit()
    groups = cache.load_groups(initialized_conn)
    assert len(groups) == 1
    assert groups[0]["full_path"] == "platform"


def test_project_round_trip(initialized_conn):
    cache.write_group(initialized_conn, {
        "id": 1, "parent_id": None, "full_path": "platform",
        "name": "platform", "visibility": "private", "description": None,
        "web_url": "https://gitlab.example.com/groups/platform",
        "created_at": "2026-01-01T00:00:00Z",
    })
    cache.write_project(initialized_conn, {
        "id": 99, "namespace_group_id": 1, "namespace_user_id": None,
        "path_with_namespace": "platform/auth", "name": "auth",
        "default_branch": "main", "visibility": "private", "archived": 0,
        "last_activity_at": "2026-05-01T00:00:00Z",
        "http_url_to_repo": "https://gitlab.example.com/platform/auth.git",
        "ssh_url_to_repo": "git@gitlab.example.com:platform/auth.git",
        "web_url": "https://gitlab.example.com/platform/auth",
        "description": None, "topics": "[]", "star_count": 0,
    })
    initialized_conn.commit()
    projects = cache.load_projects(initialized_conn)
    assert len(projects) == 1
    assert projects[0]["path_with_namespace"] == "platform/auth"


def test_member_round_trip(initialized_conn):
    cache.write_member(initialized_conn, {
        "entity_type": "group", "entity_id": 1, "user_id": 42,
        "username": "alice", "name": "Alice", "access_level": 50,
        "expires_at": None,
    })
    initialized_conn.commit()
    members = cache.load_members(initialized_conn, entity_type="group", entity_id=1)
    assert len(members) == 1
    assert members[0]["username"] == "alice"
```

- [ ] **Step 2: Run tests, verify failure**

Run: `pytest tests/browse/test_cache.py -v`
Expected: AttributeError — `load_latest_snapshot`, `load_groups`, `load_projects`, `load_members` undefined.

- [ ] **Step 3: Add read functions to `cache.py`**

Append to `gitlab_admin/browse/cache.py`:

```python
def load_latest_snapshot(conn: sqlite3.Connection) -> SnapshotRow | None:
    row = conn.execute(
        "SELECT started_at, completed_at, gitlab_url, tool_version "
        "FROM snapshot ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return None
    return SnapshotRow(
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        gitlab_url=row["gitlab_url"],
        tool_version=row["tool_version"],
    )


def load_groups(conn: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT id, parent_id, full_path, name, visibility, description, "
        "web_url, created_at FROM groups ORDER BY full_path"
    )]


def load_projects(conn: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT id, namespace_group_id, namespace_user_id, path_with_namespace, "
        "name, default_branch, visibility, archived, last_activity_at, "
        "http_url_to_repo, ssh_url_to_repo, web_url, description, topics, "
        "star_count FROM projects ORDER BY path_with_namespace"
    )]


def load_members(
    conn: sqlite3.Connection, *, entity_type: str, entity_id: int
) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT user_id, username, name, access_level, expires_at "
        "FROM members WHERE entity_type = ? AND entity_id = ? "
        "ORDER BY access_level DESC, user_id ASC",
        (entity_type, entity_id),
    )]
```

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/browse/test_cache.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add gitlab_admin/browse/cache.py tests/conftest.py tests/browse/test_cache.py
git commit -m "feat(browse): cache read functions with round-trip tests

no knowledge impact: schema and shape already in browse-command.md"
```

---

## Phase 2 — Model layer

### Task 6: Dataclasses + tree builder + owner derivation

**Files:**
- Create: `gitlab_admin/browse/model.py`
- Create: `tests/build_fixture.py`
- Create: `tests/fixtures/snapshot.sqlite` (binary; generated by `build_fixture.py`)
- Create: `tests/browse/test_model.py`

- [ ] **Step 1: Write the fixture builder**

Write `tests/build_fixture.py`:

```python
"""Builds tests/fixtures/snapshot.sqlite — the canonical test cache.

Run this directly to regenerate the fixture. The output is checked into
the repo so unit tests don't depend on this script being runnable.

Covers:
- Two-deep group nesting (platform → platform/services)
- Multi-owner project (legacy-auth: Alice + Bob)
- No-direct-owner project (etl-jobs: inherits from group)
- Archived project (legacy-auth)
- Personal-namespace project (kun.lu/scratch)
- Expired member (Carol's access expired)
"""

from pathlib import Path

from gitlab_admin.browse import cache

OUT = Path(__file__).parent / "fixtures" / "snapshot.sqlite"


def build() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if OUT.exists():
        OUT.unlink()
    with cache.connect(OUT) as conn:
        cache.init_schema(conn)

        cache.write_snapshot(conn, cache.SnapshotRow(
            started_at="2026-05-19T18:00:00Z",
            completed_at="2026-05-19T18:05:00Z",
            gitlab_url="https://gitlab.example.com",
            tool_version="0.1.0",
        ))

        for g in [
            dict(id=1, parent_id=None, full_path="platform", name="platform",
                 visibility="private", description=None,
                 web_url="https://gitlab.example.com/groups/platform",
                 created_at="2026-01-01T00:00:00Z"),
            dict(id=2, parent_id=1, full_path="platform/services",
                 name="services", visibility="private", description=None,
                 web_url="https://gitlab.example.com/groups/platform/services",
                 created_at="2026-01-01T00:00:00Z"),
            dict(id=3, parent_id=None, full_path="data", name="data",
                 visibility="private", description=None,
                 web_url="https://gitlab.example.com/groups/data",
                 created_at="2026-01-01T00:00:00Z"),
        ]:
            cache.write_group(conn, g)

        for p in [
            dict(id=101, namespace_group_id=2, namespace_user_id=None,
                 path_with_namespace="platform/services/auth-svc",
                 name="auth-svc", default_branch="main", visibility="private",
                 archived=0, last_activity_at="2026-05-16T00:00:00Z",
                 http_url_to_repo="https://gitlab.example.com/platform/services/auth-svc.git",
                 ssh_url_to_repo="git@gitlab.example.com:platform/services/auth-svc.git",
                 web_url="https://gitlab.example.com/platform/services/auth-svc",
                 description=None, topics="[]", star_count=0),
            dict(id=102, namespace_group_id=2, namespace_user_id=None,
                 path_with_namespace="platform/services/legacy-auth",
                 name="legacy-auth", default_branch="master", visibility="private",
                 archived=1, last_activity_at="2024-05-19T00:00:00Z",
                 http_url_to_repo="https://gitlab.example.com/platform/services/legacy-auth.git",
                 ssh_url_to_repo="git@gitlab.example.com:platform/services/legacy-auth.git",
                 web_url="https://gitlab.example.com/platform/services/legacy-auth",
                 description=None, topics="[]", star_count=0),
            dict(id=201, namespace_group_id=3, namespace_user_id=None,
                 path_with_namespace="data/etl-jobs",
                 name="etl-jobs", default_branch="main", visibility="private",
                 archived=0, last_activity_at="2026-04-19T00:00:00Z",
                 http_url_to_repo="https://gitlab.example.com/data/etl-jobs.git",
                 ssh_url_to_repo="git@gitlab.example.com:data/etl-jobs.git",
                 web_url="https://gitlab.example.com/data/etl-jobs",
                 description=None, topics="[]", star_count=0),
            dict(id=301, namespace_group_id=None, namespace_user_id=999,
                 path_with_namespace="kun.lu/scratch",
                 name="scratch", default_branch="main", visibility="private",
                 archived=0, last_activity_at="2026-05-19T12:00:00Z",
                 http_url_to_repo="https://gitlab.example.com/kun.lu/scratch.git",
                 ssh_url_to_repo="git@gitlab.example.com:kun.lu/scratch.git",
                 web_url="https://gitlab.example.com/kun.lu/scratch",
                 description=None, topics="[]", star_count=0),
        ]:
            cache.write_project(conn, p)

        # Members: Alice owns platform; Eve owns data; legacy-auth has
        # direct owners Alice + Bob; auth-svc has direct maintainer Bob
        # (no direct owner); etl-jobs has no direct members (inherits
        # from data); kun.lu/scratch belongs to user 999.
        for m in [
            dict(entity_type="group", entity_id=1, user_id=10,
                 username="alice", name="Alice Wong", access_level=50, expires_at=None),
            dict(entity_type="group", entity_id=3, user_id=11,
                 username="eve", name="Eve Park", access_level=50, expires_at=None),
            dict(entity_type="project", entity_id=101, user_id=12,
                 username="bob", name="Bob Chen", access_level=40, expires_at=None),
            dict(entity_type="project", entity_id=102, user_id=10,
                 username="alice", name="Alice Wong", access_level=50, expires_at=None),
            dict(entity_type="project", entity_id=102, user_id=12,
                 username="bob", name="Bob Chen", access_level=50, expires_at=None),
            dict(entity_type="project", entity_id=102, user_id=13,
                 username="carol", name="Carol Lin", access_level=40,
                 expires_at="2024-01-01T00:00:00Z"),
        ]:
            cache.write_member(conn, m)

        conn.commit()


if __name__ == "__main__":
    build()
    print(f"wrote {OUT}")
```

- [ ] **Step 2: Generate the fixture**

Run: `python tests/build_fixture.py`
Expected: `wrote tests/fixtures/snapshot.sqlite`. Verify the file exists with `ls -la tests/fixtures/snapshot.sqlite`.

- [ ] **Step 3: Add `fixture_db` fixture to `conftest.py`**

Append to `tests/conftest.py`:

```python
@pytest.fixture
def fixture_db() -> Path:
    return Path(__file__).parent / "fixtures" / "snapshot.sqlite"
```

- [ ] **Step 4: Write failing tests for the model**

Write `tests/browse/test_model.py`:

```python
from gitlab_admin.browse import cache, model


def test_build_tree_top_level_groups(fixture_db):
    with cache.connect(fixture_db) as conn:
        tree = model.build_tree(conn)
    top_paths = sorted(g.full_path for g in tree.top_level_groups)
    assert top_paths == ["data", "platform"]


def test_build_tree_nests_subgroups(fixture_db):
    with cache.connect(fixture_db) as conn:
        tree = model.build_tree(conn)
    platform = next(g for g in tree.top_level_groups if g.full_path == "platform")
    assert [g.full_path for g in platform.subgroups] == ["platform/services"]


def test_build_tree_attaches_projects(fixture_db):
    with cache.connect(fixture_db) as conn:
        tree = model.build_tree(conn)
    platform = next(g for g in tree.top_level_groups if g.full_path == "platform")
    services = platform.subgroups[0]
    project_names = sorted(p.name for p in services.projects)
    assert project_names == ["auth-svc", "legacy-auth"]


def test_personal_namespace_projects_separated(fixture_db):
    with cache.connect(fixture_db) as conn:
        tree = model.build_tree(conn)
    assert len(tree.personal_projects) == 1
    assert tree.personal_projects[0].path_with_namespace == "kun.lu/scratch"


def test_owner_direct_owner_wins(fixture_db):
    with cache.connect(fixture_db) as conn:
        tree = model.build_tree(conn)
    services = tree.top_level_groups[1].subgroups[0]  # platform/services
    legacy = next(p for p in services.projects if p.name == "legacy-auth")
    # legacy-auth has direct owners Alice (user_id=10) and Bob (user_id=12);
    # owner-derivation picks lowest user_id with access_level=50.
    assert legacy.owner == "alice"


def test_owner_falls_back_to_namespace_group_owner(fixture_db):
    with cache.connect(fixture_db) as conn:
        tree = model.build_tree(conn)
    services = tree.top_level_groups[1].subgroups[0]
    auth_svc = next(p for p in services.projects if p.name == "auth-svc")
    # auth-svc has direct maintainer Bob (access_level=40, not owner).
    # Owner derivation walks up to the namespace group (platform/services),
    # which has no members of its own → up to platform → Alice (owner).
    assert auth_svc.owner == "alice"


def test_owner_falls_back_to_namespace_path(fixture_db):
    with cache.connect(fixture_db) as conn:
        tree = model.build_tree(conn)
    scratch = tree.personal_projects[0]
    # Personal-namespace projects have no group members to walk; we
    # fall back to the namespace path.
    assert scratch.owner == "kun.lu"


def test_expired_member_excluded_from_owner(fixture_db):
    """Carol is expired on legacy-auth — must not be considered for owner."""
    with cache.connect(fixture_db) as conn:
        tree = model.build_tree(conn)
    services = tree.top_level_groups[1].subgroups[0]
    legacy = next(p for p in services.projects if p.name == "legacy-auth")
    # Alice and Bob are both Owner (50); Carol's access_level is 40 anyway,
    # but the test also confirms we don't crash on expired entries.
    assert legacy.owner in ("alice", "bob")
    # And the full member list still includes Carol, tagged as expired.
    expired_usernames = [m.username for m in legacy.members if m.is_expired]
    assert "carol" in expired_usernames
```

- [ ] **Step 5: Run tests, verify failure**

Run: `pytest tests/browse/test_model.py -v`
Expected: ImportError on `gitlab_admin.browse.model`.

- [ ] **Step 6: Implement `model.py`**

Write `gitlab_admin/browse/model.py`:

```python
"""Pure in-memory tree built from cache rows. No I/O, no clock, no env."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from . import cache

ACCESS_LEVEL_OWNER = 50


@dataclass
class Member:
    user_id: int
    username: str
    name: str
    access_level: int
    expires_at: Optional[str]

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        try:
            dt = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
        except ValueError:
            return False
        return dt < datetime.now(timezone.utc)

    @property
    def is_owner(self) -> bool:
        return self.access_level == ACCESS_LEVEL_OWNER and not self.is_expired


@dataclass
class Project:
    id: int
    name: str
    path_with_namespace: str
    namespace_group_id: Optional[int]
    namespace_user_id: Optional[int]
    default_branch: Optional[str]
    visibility: str
    archived: bool
    last_activity_at: str
    http_url_to_repo: str
    ssh_url_to_repo: str
    web_url: str
    description: Optional[str]
    topics: list[str]
    star_count: int
    members: list[Member] = field(default_factory=list)
    owner: str = ""  # filled by owner-derivation pass


@dataclass
class Group:
    id: int
    parent_id: Optional[int]
    full_path: str
    name: str
    visibility: str
    description: Optional[str]
    web_url: str
    created_at: str
    subgroups: list["Group"] = field(default_factory=list)
    projects: list[Project] = field(default_factory=list)
    members: list[Member] = field(default_factory=list)


@dataclass
class Snapshot:
    started_at: str
    completed_at: str
    gitlab_url: str
    tool_version: str


@dataclass
class Tree:
    snapshot: Optional[Snapshot]
    top_level_groups: list[Group]
    personal_projects: list[Project]


def _members_for(conn: sqlite3.Connection, entity_type: str, entity_id: int) -> list[Member]:
    rows = cache.load_members(conn, entity_type=entity_type, entity_id=entity_id)
    return [Member(
        user_id=r["user_id"],
        username=r["username"],
        name=r["name"],
        access_level=r["access_level"],
        expires_at=r["expires_at"],
    ) for r in rows]


def _derive_owner(project: Project, groups_by_id: dict[int, Group]) -> str:
    # 1. Direct owner on the project, lowest user_id wins.
    direct_owners = sorted(
        (m for m in project.members if m.is_owner),
        key=lambda m: m.user_id,
    )
    if direct_owners:
        return direct_owners[0].username

    # 2. Walk up namespace group chain.
    gid = project.namespace_group_id
    while gid is not None:
        group = groups_by_id.get(gid)
        if group is None:
            break
        group_owners = sorted(
            (m for m in group.members if m.is_owner),
            key=lambda m: m.user_id,
        )
        if group_owners:
            return group_owners[0].username
        gid = group.parent_id

    # 3. Namespace path fallback.
    return project.path_with_namespace.rsplit("/", 1)[0]


def build_tree(conn: sqlite3.Connection) -> Tree:
    snap_row = cache.load_latest_snapshot(conn)
    snapshot = None if snap_row is None else Snapshot(
        started_at=snap_row.started_at,
        completed_at=snap_row.completed_at,
        gitlab_url=snap_row.gitlab_url,
        tool_version=snap_row.tool_version,
    )

    groups_by_id: dict[int, Group] = {}
    for row in cache.load_groups(conn):
        g = Group(
            id=row["id"],
            parent_id=row["parent_id"],
            full_path=row["full_path"],
            name=row["name"],
            visibility=row["visibility"],
            description=row["description"],
            web_url=row["web_url"],
            created_at=row["created_at"],
            members=_members_for(conn, "group", row["id"]),
        )
        groups_by_id[g.id] = g

    # Wire subgroup edges.
    top_level: list[Group] = []
    for g in groups_by_id.values():
        if g.parent_id is None:
            top_level.append(g)
        else:
            parent = groups_by_id.get(g.parent_id)
            if parent is not None:
                parent.subgroups.append(g)
    top_level.sort(key=lambda g: g.full_path)
    for g in groups_by_id.values():
        g.subgroups.sort(key=lambda x: x.full_path)

    # Attach projects.
    personal: list[Project] = []
    import json

    def _topics(s: Optional[str]) -> list[str]:
        if not s:
            return []
        try:
            value = json.loads(s)
        except ValueError:
            return []
        return value if isinstance(value, list) else []

    for row in cache.load_projects(conn):
        p = Project(
            id=row["id"],
            name=row["name"],
            path_with_namespace=row["path_with_namespace"],
            namespace_group_id=row["namespace_group_id"],
            namespace_user_id=row["namespace_user_id"],
            default_branch=row["default_branch"],
            visibility=row["visibility"],
            archived=bool(row["archived"]),
            last_activity_at=row["last_activity_at"],
            http_url_to_repo=row["http_url_to_repo"],
            ssh_url_to_repo=row["ssh_url_to_repo"],
            web_url=row["web_url"],
            description=row["description"],
            topics=_topics(row["topics"]),
            star_count=row["star_count"],
            members=_members_for(conn, "project", row["id"]),
        )
        p.owner = _derive_owner(p, groups_by_id)
        if p.namespace_group_id is not None:
            groups_by_id[p.namespace_group_id].projects.append(p)
        else:
            personal.append(p)

    for g in groups_by_id.values():
        g.projects.sort(key=lambda x: x.name)
    personal.sort(key=lambda x: x.path_with_namespace)

    return Tree(
        snapshot=snapshot,
        top_level_groups=top_level,
        personal_projects=personal,
    )
```

- [ ] **Step 7: Run tests, verify pass**

Run: `pytest tests/browse/test_model.py -v`
Expected: 8 passed.

- [ ] **Step 8: Commit**

```bash
git add gitlab_admin/browse/model.py tests/build_fixture.py tests/fixtures/snapshot.sqlite tests/conftest.py tests/browse/test_model.py
git commit -m "feat(browse): in-memory tree model with owner derivation

no knowledge impact: owner-derivation rule already in browse-command.md"
```

---

## Phase 3 — Fetch layer

### Task 7: Paginated group + project + member fetch with atomic-replace sync

**Files:**
- Create: `gitlab_admin/browse/fetch.py`
- Create: `tests/browse/test_fetch.py`

- [ ] **Step 1: Write failing tests**

Write `tests/browse/test_fetch.py`:

```python
import json
import sqlite3

import pytest
import responses

from gitlab_admin import client
from gitlab_admin.browse import cache, fetch


@pytest.fixture
def stubbed_gitlab(monkeypatch):
    monkeypatch.setenv("GITLAB_URL", "https://gitlab.example.com")
    monkeypatch.setenv("GITLAB_TOKEN", "test-token")
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        yield rsps


def _stub_groups_list(rsps, groups):
    rsps.add(
        responses.GET,
        "https://gitlab.example.com/api/v4/groups",
        json=groups,
        status=200,
        adding_headers={"X-Total-Pages": "1", "X-Next-Page": ""},
    )


def _stub_group_projects(rsps, group_id, projects):
    rsps.add(
        responses.GET,
        f"https://gitlab.example.com/api/v4/groups/{group_id}/projects",
        json=projects,
        status=200,
        adding_headers={"X-Total-Pages": "1", "X-Next-Page": ""},
    )


def _stub_members_all(rsps, entity_type, entity_id, members):
    plural = "groups" if entity_type == "group" else "projects"
    rsps.add(
        responses.GET,
        f"https://gitlab.example.com/api/v4/{plural}/{entity_id}/members/all",
        json=members,
        status=200,
        adding_headers={"X-Total-Pages": "1", "X-Next-Page": ""},
    )


def _group_payload(id_, full_path, parent_id=None):
    return {
        "id": id_, "parent_id": parent_id, "full_path": full_path,
        "name": full_path.split("/")[-1], "visibility": "private",
        "description": None,
        "web_url": f"https://gitlab.example.com/groups/{full_path}",
        "created_at": "2026-01-01T00:00:00Z",
    }


def _project_payload(id_, namespace_id, path):
    return {
        "id": id_, "namespace": {"id": namespace_id, "kind": "group"},
        "path_with_namespace": path, "name": path.split("/")[-1],
        "default_branch": "main", "visibility": "private", "archived": False,
        "last_activity_at": "2026-05-01T00:00:00Z",
        "http_url_to_repo": f"https://gitlab.example.com/{path}.git",
        "ssh_url_to_repo": f"git@gitlab.example.com:{path}.git",
        "web_url": f"https://gitlab.example.com/{path}",
        "description": None, "topics": [], "star_count": 0,
    }


def _member_payload(user_id, username, access_level, expires_at=None):
    return {
        "id": user_id, "username": username, "name": username.title(),
        "access_level": access_level, "expires_at": expires_at,
    }


def test_full_sync_writes_groups_projects_members(stubbed_gitlab, tmp_cache):
    _stub_groups_list(stubbed_gitlab, [
        _group_payload(1, "platform"),
        _group_payload(2, "platform/services", parent_id=1),
    ])
    _stub_group_projects(stubbed_gitlab, 1, [])
    _stub_group_projects(stubbed_gitlab, 2, [
        _project_payload(101, 2, "platform/services/auth-svc"),
    ])
    _stub_members_all(stubbed_gitlab, "group", 1, [
        _member_payload(10, "alice", 50),
    ])
    _stub_members_all(stubbed_gitlab, "group", 2, [])
    _stub_members_all(stubbed_gitlab, "project", 101, [
        _member_payload(12, "bob", 40),
    ])

    gl = client.get_client()
    fetch.sync_all(gl, cache_path=tmp_cache, tool_version="0.1.0")

    with cache.connect(tmp_cache) as conn:
        assert cache.read_schema_version(conn) == cache.SCHEMA_VERSION
        groups = cache.load_groups(conn)
        assert {g["full_path"] for g in groups} == {"platform", "platform/services"}
        projects = cache.load_projects(conn)
        assert projects[0]["path_with_namespace"] == "platform/services/auth-svc"


def test_sync_atomic_replace_preserves_old_cache_on_failure(stubbed_gitlab, tmp_cache):
    # Seed an existing cache with one group.
    with cache.connect(tmp_cache) as conn:
        cache.init_schema(conn)
        cache.write_group(conn, _group_payload(99, "old-group"))
        conn.commit()

    # Stub a failure mid-sync.
    _stub_groups_list(stubbed_gitlab, [_group_payload(1, "platform")])
    stubbed_gitlab.add(
        responses.GET,
        "https://gitlab.example.com/api/v4/groups/1/projects",
        status=500,
    )

    gl = client.get_client()
    with pytest.raises(fetch.SyncFailed):
        fetch.sync_all(gl, cache_path=tmp_cache, tool_version="0.1.0")

    # Old cache must still be readable and unchanged.
    with cache.connect(tmp_cache) as conn:
        groups = cache.load_groups(conn)
        assert len(groups) == 1
        assert groups[0]["full_path"] == "old-group"


def test_sync_dedups_inherited_members_keeping_highest_access(stubbed_gitlab, tmp_cache):
    _stub_groups_list(stubbed_gitlab, [_group_payload(1, "platform")])
    _stub_group_projects(stubbed_gitlab, 1, [
        _project_payload(101, 1, "platform/auth"),
    ])
    _stub_members_all(stubbed_gitlab, "group", 1, [])
    # /members/all returns alice twice: as direct (40) and inherited (50).
    # The endpoint already returns the highest-access copy per user, but
    # we test fetch's dedup logic against duplicate input regardless.
    _stub_members_all(stubbed_gitlab, "project", 101, [
        _member_payload(10, "alice", 40),
        _member_payload(10, "alice", 50),
    ])

    gl = client.get_client()
    fetch.sync_all(gl, cache_path=tmp_cache, tool_version="0.1.0")

    with cache.connect(tmp_cache) as conn:
        members = cache.load_members(conn, entity_type="project", entity_id=101)
    assert len(members) == 1
    assert members[0]["access_level"] == 50
```

- [ ] **Step 2: Run tests, verify failure**

Run: `pytest tests/browse/test_fetch.py -v`
Expected: ImportError on `gitlab_admin.browse.fetch`.

- [ ] **Step 3: Implement `fetch.py`**

Write `gitlab_admin/browse/fetch.py`:

```python
"""Network-touching layer: walks the GitLab API and populates a fresh
SQLite cache via temp-file + atomic os.replace().

This is the ONLY module in browse/ that talks to GitLab. Everything
downstream reads the cache.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import gitlab

from . import cache


class SyncFailed(RuntimeError):
    """A sync failed before the atomic replace; existing cache is untouched."""


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _group_row(g) -> dict:
    return {
        "id": g.id,
        "parent_id": getattr(g, "parent_id", None),
        "full_path": g.full_path,
        "name": g.name,
        "visibility": g.visibility,
        "description": getattr(g, "description", None),
        "web_url": g.web_url,
        "created_at": g.created_at,
    }


def _project_row(p) -> dict:
    namespace = getattr(p, "namespace", {}) or {}
    is_group_ns = namespace.get("kind") == "group"
    return {
        "id": p.id,
        "namespace_group_id": namespace.get("id") if is_group_ns else None,
        "namespace_user_id": namespace.get("id") if not is_group_ns else None,
        "path_with_namespace": p.path_with_namespace,
        "name": p.name,
        "default_branch": getattr(p, "default_branch", None),
        "visibility": p.visibility,
        "archived": 1 if p.archived else 0,
        "last_activity_at": p.last_activity_at,
        "http_url_to_repo": p.http_url_to_repo,
        "ssh_url_to_repo": p.ssh_url_to_repo,
        "web_url": p.web_url,
        "description": getattr(p, "description", None),
        "topics": json.dumps(getattr(p, "topics", []) or []),
        "star_count": getattr(p, "star_count", 0),
    }


def _member_row(entity_type: str, entity_id: int, m) -> dict:
    return {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "user_id": m.id,
        "username": m.username,
        "name": getattr(m, "name", m.username),
        "access_level": m.access_level,
        "expires_at": getattr(m, "expires_at", None),
    }


def _write_members_deduped(conn, entity_type: str, entity_id: int, member_objs) -> None:
    """For each user, keep only the row with highest access_level."""
    best: dict[int, dict] = {}
    for m in member_objs:
        row = _member_row(entity_type, entity_id, m)
        existing = best.get(m.id)
        if existing is None or row["access_level"] > existing["access_level"]:
            best[m.id] = row
    for row in best.values():
        cache.write_member(conn, row)


def sync_all(gl: gitlab.Gitlab, *, cache_path: Path, tool_version: str) -> None:
    """Fetch everything visible to the token and replace `cache_path`
    atomically. Raises SyncFailed on any API error; existing cache is
    not touched on failure.
    """
    started = _utcnow_iso()
    cache_path = Path(cache_path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_str = tempfile.mkstemp(
        prefix="browse-", suffix=".sqlite.tmp", dir=cache_path.parent
    )
    os.close(fd)
    tmp_path = Path(tmp_str)
    try:
        with cache.connect(tmp_path) as conn:
            cache.init_schema(conn)
            try:
                groups = gl.groups.list(all=True, all_available=True)
            except gitlab.exceptions.GitlabError as exc:
                raise SyncFailed(f"failed to list groups: {exc}") from exc
            for g in groups:
                cache.write_group(conn, _group_row(g))
                try:
                    g_members = gl.groups.get(g.id).members_all.list(all=True)
                except gitlab.exceptions.GitlabError as exc:
                    raise SyncFailed(f"failed to list members for group {g.full_path}: {exc}") from exc
                _write_members_deduped(conn, "group", g.id, g_members)

                try:
                    projects = gl.groups.get(g.id).projects.list(all=True, include_subgroups=False)
                except gitlab.exceptions.GitlabError as exc:
                    raise SyncFailed(f"failed to list projects for group {g.full_path}: {exc}") from exc
                for p in projects:
                    cache.write_project(conn, _project_row(p))
                    try:
                        p_members = gl.projects.get(p.id).members_all.list(all=True)
                    except gitlab.exceptions.GitlabError as exc:
                        raise SyncFailed(f"failed to list members for project {p.path_with_namespace}: {exc}") from exc
                    _write_members_deduped(conn, "project", p.id, p_members)

            cache.write_snapshot(conn, cache.SnapshotRow(
                started_at=started,
                completed_at=_utcnow_iso(),
                gitlab_url=gl.url,
                tool_version=tool_version,
            ))
            conn.commit()

        os.replace(tmp_path, cache_path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise
```

**Note on test/impl symmetry:** The tests in Step 1 stub `responses` at the HTTP level. `python-gitlab` issues GET requests that match the stubbed URLs. The `python-gitlab` library returns Python objects whose attributes our `_group_row`/`_project_row`/`_member_row` helpers access — `responses` makes those attributes available because `python-gitlab` populates them from the JSON response. If a test fails with `AttributeError: 'Mock' has no attribute 'X'`, add `X` to the stubbed JSON.

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/browse/test_fetch.py -v`
Expected: 3 passed. If `responses` complains about unexpected requests, list the missing URL the test failed to stub.

- [ ] **Step 5: Update `browse-command.md` (fetch landed)**

The article already documents the fetch shape and atomic-replace. No content change needed. Bump `updated:` to today.

Edit `knowledge/concepts/gitlab-admin/browse-command.md` frontmatter only:

```yaml
updated: 2026-05-19
```

(Already that date — leave as-is or refresh if implementing on a different day.)

- [ ] **Step 6: Commit**

```bash
git add gitlab_admin/browse/fetch.py tests/browse/test_fetch.py
git commit -m "feat(browse): API fetch with atomic-replace sync

no knowledge impact: fetch architecture already in browse-command.md"
```

---

## Phase 4 — Text renderer + CLI

### Task 8: Text renderer with golden file

**Files:**
- Create: `gitlab_admin/browse/render_text.py`
- Create: `tests/browse/fixtures/expected_tree.txt`
- Create: `tests/browse/test_render_text.py`

- [ ] **Step 1: Write the golden file**

Write `tests/browse/fixtures/expected_tree.txt`:

```text
📁 data                                                           — eve (owner)
└── ▢ etl-jobs                                eve · 2026-04-19 · prv
📁 platform                                                       — alice (owner)
└── 📁 services                                                   — alice
    ├── ▢ auth-svc                            alice · 2026-05-16 · prv
    └── ▢ legacy-auth         [archived]      alice · 2024-05-19 · prv

👤 Personal projects
└── ▢ kun.lu/scratch                          kun.lu · 2026-05-19 · prv

Snapshot: 2026-05-19T18:05:00Z · https://gitlab.example.com · 4 projects across 3 groups
```

- [ ] **Step 2: Write failing test**

Write `tests/browse/test_render_text.py`:

```python
from pathlib import Path

from gitlab_admin.browse import cache, model, render_text


def test_render_text_matches_golden(fixture_db):
    with cache.connect(fixture_db) as conn:
        tree = model.build_tree(conn)
    output = render_text.render(tree, use_ansi=False)
    expected = (Path(__file__).parent / "fixtures" / "expected_tree.txt").read_text()
    assert output.rstrip() == expected.rstrip()


def test_render_text_filters_archived(fixture_db):
    with cache.connect(fixture_db) as conn:
        tree = model.build_tree(conn)
    output = render_text.render(tree, use_ansi=False, include_archived=False)
    assert "legacy-auth" not in output
    assert "auth-svc" in output


def test_render_text_filters_by_group(fixture_db):
    with cache.connect(fixture_db) as conn:
        tree = model.build_tree(conn)
    output = render_text.render(tree, use_ansi=False, root_group="data")
    assert "data" in output
    assert "platform" not in output


def test_render_text_filters_by_owner(fixture_db):
    with cache.connect(fixture_db) as conn:
        tree = model.build_tree(conn)
    output = render_text.render(tree, use_ansi=False, owner="eve")
    assert "etl-jobs" in output
    assert "auth-svc" not in output


def test_render_text_filters_by_stale_days(fixture_db):
    with cache.connect(fixture_db) as conn:
        tree = model.build_tree(conn)
    # Fixture's "today" anchor: cap activity at 2026-05-19 (snapshot date).
    output = render_text.render(
        tree, use_ansi=False, stale_days=365, today="2026-05-19"
    )
    assert "legacy-auth" in output  # last activity 2024-05-19 → 2 years stale
    assert "auth-svc" not in output  # last activity 2026-05-16 → 3 days, not stale
```

- [ ] **Step 3: Run tests, verify failure**

Run: `pytest tests/browse/test_render_text.py -v`
Expected: ImportError on `render_text`.

- [ ] **Step 4: Implement `render_text.py`**

Write `gitlab_admin/browse/render_text.py`:

```python
"""Indented tree → stdout. Renderer is pure: takes a Tree, returns a string."""

from __future__ import annotations

from datetime import date, datetime
from io import StringIO
from typing import Optional

from .model import Group, Project, Tree

_VIS_SHORT = {"private": "prv", "internal": "int", "public": "pub"}


def _short_date(iso: str) -> str:
    return iso.split("T")[0]


def _project_line(p: Project, indent: str) -> str:
    arch = "  [archived]" if p.archived else "            "
    return (
        f"{indent}▢ {p.name:<24}{arch}    "
        f"{p.owner} · {_short_date(p.last_activity_at)} · {_VIS_SHORT.get(p.visibility, p.visibility)}"
    )


def _walk_group(g: Group, prefix: str, is_last: bool, out: StringIO, *, depth: int) -> None:
    # Group header line.
    if depth == 0:
        head = f"📁 {g.name:<60}"
    else:
        connector = "└── " if is_last else "├── "
        head = f"{prefix}{connector}📁 {g.name:<55}"
    # Owner annotation: lowest-user_id Owner-access member, if any.
    owners = sorted((m for m in g.members if m.is_owner), key=lambda m: m.user_id)
    if owners:
        head += f"— {owners[0].username} (owner)"
    elif depth > 0:
        head += f"— {len(g.projects)} project(s)"
    out.write(head.rstrip() + "\n")

    # Children (subgroups + projects).
    child_prefix = prefix + ("    " if is_last else "│   ") if depth > 0 else ""
    entries = [("g", sg) for sg in g.subgroups] + [("p", p) for p in g.projects]
    for i, (kind, child) in enumerate(entries):
        last = i == len(entries) - 1
        if kind == "g":
            _walk_group(child, child_prefix, last, out, depth=depth + 1)
        else:
            connector = "└── " if last else "├── "
            out.write(_project_line(child, child_prefix + connector).rstrip() + "\n")


def _filter_tree(
    tree: Tree,
    *,
    include_archived: bool,
    owner: Optional[str],
    root_group: Optional[str],
    stale_days: Optional[int],
    today: Optional[str],
) -> Tree:
    """Return a shallow-copied Tree with non-matching projects removed."""
    if today is None:
        today_d = date.today()
    else:
        today_d = date.fromisoformat(today)

    def project_keeps(p: Project) -> bool:
        if not include_archived and p.archived:
            return False
        if owner and p.owner != owner:
            return False
        if stale_days is not None:
            activity = date.fromisoformat(_short_date(p.last_activity_at))
            if (today_d - activity).days < stale_days:
                return False
        return True

    def prune_group(g: Group) -> Optional[Group]:
        new_subs = [s for s in (prune_group(sg) for sg in g.subgroups) if s is not None]
        new_projects = [p for p in g.projects if project_keeps(p)]
        if not new_subs and not new_projects and (owner or stale_days is not None or not include_archived):
            return None
        # shallow copy with replaced children
        return Group(
            id=g.id, parent_id=g.parent_id, full_path=g.full_path, name=g.name,
            visibility=g.visibility, description=g.description, web_url=g.web_url,
            created_at=g.created_at, subgroups=new_subs, projects=new_projects,
            members=g.members,
        )

    top = [g for g in (prune_group(g) for g in tree.top_level_groups) if g is not None]
    if root_group is not None:
        top = [g for g in top if g.full_path == root_group or g.full_path.startswith(root_group + "/")]
        # Also filter subgroups recursively if root targets a deeper path.
    personal = [p for p in tree.personal_projects if project_keeps(p)]
    if root_group is not None:
        personal = []  # personal projects are outside the group tree
    return Tree(snapshot=tree.snapshot, top_level_groups=top, personal_projects=personal)


def render(
    tree: Tree,
    *,
    use_ansi: bool = True,
    include_archived: bool = True,
    owner: Optional[str] = None,
    root_group: Optional[str] = None,
    stale_days: Optional[int] = None,
    today: Optional[str] = None,
) -> str:
    """Render the tree to a plain string. ANSI not yet implemented; the
    flag is accepted so the CLI can pass it through unchanged once ANSI
    lands in a follow-up."""
    tree = _filter_tree(
        tree,
        include_archived=include_archived,
        owner=owner,
        root_group=root_group,
        stale_days=stale_days,
        today=today,
    )

    out = StringIO()
    for g in tree.top_level_groups:
        _walk_group(g, "", is_last=True, out=out, depth=0)

    if tree.personal_projects:
        out.write("\n👤 Personal projects\n")
        for i, p in enumerate(tree.personal_projects):
            last = i == len(tree.personal_projects) - 1
            connector = "└── " if last else "├── "
            line = (
                f"{connector}▢ {p.path_with_namespace:<30}              "
                f"{p.owner} · {_short_date(p.last_activity_at)} · "
                f"{_VIS_SHORT.get(p.visibility, p.visibility)}"
            )
            out.write(line.rstrip() + "\n")

    if tree.snapshot is not None:
        total_projects = sum(
            len(g.projects) + sum(len(sg.projects) for sg in g.subgroups)
            for g in tree.top_level_groups
        ) + len(tree.personal_projects)
        total_groups = sum(1 + len(g.subgroups) for g in tree.top_level_groups)
        out.write(
            f"\nSnapshot: {tree.snapshot.completed_at} · "
            f"{tree.snapshot.gitlab_url} · "
            f"{total_projects} projects across {total_groups} groups\n"
        )

    return out.getvalue()
```

- [ ] **Step 5: Run tests, verify pass**

Run: `pytest tests/browse/test_render_text.py -v`
Expected: 5 passed. If the golden test fails, the diff in pytest output tells you which line drifted — update either the renderer or the golden file (whichever is wrong).

- [ ] **Step 6: Commit**

```bash
git add gitlab_admin/browse/render_text.py tests/browse/test_render_text.py tests/browse/fixtures/expected_tree.txt
git commit -m "feat(browse): text renderer with filters and golden test

no knowledge impact: CLI flags listed in browse-command.md already"
```

---

### Task 9: CLI entry point

**Files:**
- Create: `gitlab_admin/browse/__main__.py`
- Create: `tests/browse/test_main.py`

- [ ] **Step 1: Write failing tests**

Write `tests/browse/test_main.py`:

```python
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
```

- [ ] **Step 2: Run tests, verify failure**

Run: `pytest tests/browse/test_main.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `__main__.py`**

Write `gitlab_admin/browse/__main__.py`:

```python
"""argparse CLI for `python -m gitlab_admin.browse`.

Exit codes (per spec §5):
  0 success
  1 cache missing / schema mismatch (not --refresh)
  2 network error during refresh
  3 auth error (env vars missing or rejected)
  4 unexpected error / arg violation
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from gitlab_admin import __version__, client
from . import cache, fetch, model, render_text


EXIT_OK = 0
EXIT_NO_CACHE = 1
EXIT_NETWORK = 2
EXIT_AUTH = 3
EXIT_UNEXPECTED = 4


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m gitlab_admin.browse")
    p.add_argument("--refresh", action="store_true",
                   help="Re-fetch from GitLab before rendering.")
    p.add_argument("--cache-path", type=Path, default=cache.default_cache_path(),
                   help=f"SQLite cache path (default: {cache.default_cache_path()}).")
    p.add_argument("--gitlab-url", help="Override GITLAB_URL for this invocation.")
    p.add_argument("--gitlab-token", help="Override GITLAB_TOKEN for this invocation.")

    # Output modes (mutually exclusive)
    modes = p.add_mutually_exclusive_group()
    modes.add_argument("--json", action="store_true",
                       help="Emit JSON to stdout instead of a text tree.")
    modes.add_argument("--html", type=Path, metavar="PATH",
                       help="Write HTML report to PATH (not implemented in this plan).")
    modes.add_argument("-i", "--interactive", action="store_true",
                       help="Interactive menu mode (not implemented in this plan).")

    # Text-tree filters
    p.add_argument("--group", dest="root_group", metavar="PATH",
                   help="Root the tree at this group.")
    p.add_argument("--owner", help="Show only projects owned by this username.")
    p.add_argument("--stale-days", type=int, metavar="N",
                   help="Show only projects with no activity in the last N days.")
    p.add_argument("--no-archived", action="store_true",
                   help="Hide archived projects.")
    return p


def _refresh(args, cache_path: Path) -> int:
    try:
        gl = client.get_client(url=args.gitlab_url, token=args.gitlab_token)
    except client.MissingCredentials as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_AUTH
    try:
        fetch.sync_all(gl, cache_path=cache_path, tool_version=__version__)
    except fetch.SyncFailed as exc:
        print(f"refresh failed: {exc}", file=sys.stderr)
        print(
            f"existing cache (if any) unchanged at {cache_path}",
            file=sys.stderr,
        )
        return EXIT_NETWORK
    return EXIT_OK


def _ensure_cache(cache_path: Path) -> int:
    if not cache_path.exists():
        print(
            f"No cache at {cache_path}. Run with --refresh first.",
            file=sys.stderr,
        )
        return EXIT_NO_CACHE
    with cache.connect(cache_path) as conn:
        version = cache.read_schema_version(conn)
    if version != cache.SCHEMA_VERSION:
        print(
            f"Cache schema is v{version}; tool expects v{cache.SCHEMA_VERSION}. "
            "Re-run with --refresh.",
            file=sys.stderr,
        )
        return EXIT_NO_CACHE
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.html is not None or args.interactive:
        print(
            "--html and --interactive land in Plan 2 / Plan 3. Use the text "
            "renderer or --json for now.",
            file=sys.stderr,
        )
        return EXIT_UNEXPECTED

    cache_path: Path = args.cache_path

    if args.refresh:
        rc = _refresh(args, cache_path)
        if rc != EXIT_OK:
            return rc

    rc = _ensure_cache(cache_path)
    if rc != EXIT_OK:
        return rc

    with cache.connect(cache_path) as conn:
        tree = model.build_tree(conn)

    if args.json:
        from . import render_json
        sys.stdout.write(render_json.render(tree))
        return EXIT_OK

    output = render_text.render(
        tree,
        use_ansi=sys.stdout.isatty(),
        include_archived=not args.no_archived,
        owner=args.owner,
        root_group=args.root_group,
        stale_days=args.stale_days,
    )
    sys.stdout.write(output)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/browse/test_main.py -v`
Expected: 4 passed. Note: `test_html_and_json_mutually_exclusive` expects argparse to raise SystemExit — `add_mutually_exclusive_group()` produces that.

- [ ] **Step 5: Smoke-test the CLI manually**

Run: `python -m gitlab_admin.browse --cache-path tests/fixtures/snapshot.sqlite`
Expected: a text tree similar to `tests/browse/fixtures/expected_tree.txt`.

Run: `python -m gitlab_admin.browse --cache-path tests/fixtures/snapshot.sqlite --no-archived`
Expected: `legacy-auth` not in output.

Run: `python -m gitlab_admin.browse --cache-path /tmp/nope.sqlite`
Expected: exit 1, error message "No cache at /tmp/nope.sqlite. Run with --refresh first."

- [ ] **Step 6: Commit**

```bash
git add gitlab_admin/browse/__main__.py tests/browse/test_main.py
git commit -m "feat(browse): CLI entry with --refresh, --json placeholder, filters

no knowledge impact: CLI shape already in browse-command.md"
```

---

## Phase 5 — JSON renderer

### Task 10: JSON renderer

**Files:**
- Create: `gitlab_admin/browse/render_json.py`
- Create: `tests/browse/test_render_json.py`

- [ ] **Step 1: Write failing test**

Write `tests/browse/test_render_json.py`:

```python
import json

from gitlab_admin.browse import cache, model, render_json


def test_render_json_shape(fixture_db):
    with cache.connect(fixture_db) as conn:
        tree = model.build_tree(conn)
    data = json.loads(render_json.render(tree))

    assert data["snapshot"]["gitlab_url"] == "https://gitlab.example.com"
    assert data["snapshot"]["tool_version"] == "0.1.0"

    top_paths = sorted(g["full_path"] for g in data["groups"])
    assert top_paths == ["data", "platform"]

    platform = next(g for g in data["groups"] if g["full_path"] == "platform")
    assert platform["children_groups"][0]["full_path"] == "platform/services"

    auth_svc = next(
        p for p in platform["children_groups"][0]["projects"]
        if p["name"] == "auth-svc"
    )
    assert auth_svc["http_url_to_repo"].endswith("/platform/services/auth-svc.git")
    assert auth_svc["ssh_url_to_repo"].startswith("git@gitlab.example.com:")
    assert auth_svc["owner"] == "alice"
    assert any(m["username"] == "bob" for m in auth_svc["members"])

    assert len(data["personal_namespace_projects"]) == 1
    assert data["personal_namespace_projects"][0]["path_with_namespace"] == "kun.lu/scratch"


def test_render_json_handles_empty_tree():
    tree = model.Tree(snapshot=None, top_level_groups=[], personal_projects=[])
    data = json.loads(render_json.render(tree))
    assert data == {
        "snapshot": None,
        "groups": [],
        "personal_namespace_projects": [],
    }
```

- [ ] **Step 2: Run tests, verify failure**

Run: `pytest tests/browse/test_render_json.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `render_json.py`**

Write `gitlab_admin/browse/render_json.py`:

```python
"""Tree → JSON to stdout. Stable shape; see spec §6.3."""

from __future__ import annotations

import json

from .model import Group, Project, Tree


def _project_dict(p: Project) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "path_with_namespace": p.path_with_namespace,
        "default_branch": p.default_branch,
        "visibility": p.visibility,
        "archived": p.archived,
        "last_activity_at": p.last_activity_at,
        "http_url_to_repo": p.http_url_to_repo,
        "ssh_url_to_repo": p.ssh_url_to_repo,
        "web_url": p.web_url,
        "description": p.description,
        "topics": p.topics,
        "star_count": p.star_count,
        "owner": p.owner,
        "members": [
            {
                "user_id": m.user_id,
                "username": m.username,
                "name": m.name,
                "access_level": m.access_level,
                "expires_at": m.expires_at,
                "is_expired": m.is_expired,
            }
            for m in p.members
        ],
    }


def _group_dict(g: Group) -> dict:
    return {
        "id": g.id,
        "full_path": g.full_path,
        "name": g.name,
        "visibility": g.visibility,
        "description": g.description,
        "web_url": g.web_url,
        "children_groups": [_group_dict(sg) for sg in g.subgroups],
        "projects": [_project_dict(p) for p in g.projects],
    }


def render(tree: Tree) -> str:
    payload = {
        "snapshot": (
            None if tree.snapshot is None else {
                "started_at": tree.snapshot.started_at,
                "completed_at": tree.snapshot.completed_at,
                "gitlab_url": tree.snapshot.gitlab_url,
                "tool_version": tree.snapshot.tool_version,
            }
        ),
        "groups": [_group_dict(g) for g in tree.top_level_groups],
        "personal_namespace_projects": [
            _project_dict(p) for p in tree.personal_projects
        ],
    }
    return json.dumps(payload, indent=2) + "\n"
```

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/browse/test_render_json.py -v`
Expected: 2 passed.

- [ ] **Step 5: Run full test suite**

Run: `pytest -v`
Expected: all tests pass (cache, model, fetch, render_text, render_json, main, client).

- [ ] **Step 6: Smoke-test JSON output**

Run: `python -m gitlab_admin.browse --cache-path tests/fixtures/snapshot.sqlite --json | python -m json.tool | head -30`
Expected: pretty-printed JSON with `snapshot`, `groups`, `personal_namespace_projects`.

- [ ] **Step 7: Commit**

```bash
git add gitlab_admin/browse/render_json.py tests/browse/test_render_json.py
git commit -m "feat(browse): JSON renderer

no knowledge impact: JSON shape already in browse-command.md"
```

---

## Phase 6 — Living-doc finalization + scope expansion

### Task 11: Update `purpose-and-scope.md` (fourth task family)

**Files:**
- Modify: `knowledge/concepts/gitlab-admin/purpose-and-scope.md`

- [ ] **Step 1: Add the fourth task family**

Edit `knowledge/concepts/gitlab-admin/purpose-and-scope.md`. Find the numbered list of three task families and replace with:

```markdown
The toolkit targets four task families:

1. **User & group lifecycle** — onboarding, offboarding, role changes,
   periodic membership audits.
2. **Project/repo housekeeping** — applying consistent settings across
   projects (visibility, protected branches, MR rules, CI/CD config).
3. **Access & permissions audit** — reporting who has what access,
   flagging deviation from policy, surfacing stale tokens and deploy keys.
4. **Discovery / org navigation** — browsing the full org map (groups,
   projects, owners, clone URLs, last activity) when GitLab's own web
   UI can't keep up. See `browse-command.md`.
```

Bump `updated:` to today's date (2026-05-19).

- [ ] **Step 2: Validate**

Run: `scripts/validate-articles`
Expected: `✅ All 4 article(s) have valid frontmatter.`

- [ ] **Step 3: Commit**

```bash
git add knowledge/concepts/gitlab-admin/purpose-and-scope.md
git commit -m "docs: add discovery/org-navigation as the fourth task family

Triggered by the `browse` command landing. Same-task rule: scope
article updated in the same change-set as the code that motivated it."
```

---

### Task 12: Update `tech-stack.md` and `CLAUDE.md`; append `log.md`; update `index.md`

**Files:**
- Modify: `knowledge/concepts/gitlab-admin/tech-stack.md`
- Modify: `CLAUDE.md`
- Modify: `knowledge/index.md`
- Modify: `knowledge/log.md`

- [ ] **Step 1: Update `tech-stack.md`**

In `knowledge/concepts/gitlab-admin/tech-stack.md`, find the dependency list and add a dev-dep entry:

```markdown
- **Test runner:** `pytest`. HTTP stubbing via `responses` (dev dep).
- **Cache:** stdlib `sqlite3`. No ORM.
```

In the "First commitments" section, add:

```markdown
- `gitlab_admin/browse/` follows the layered shape described in
  `browse-command.md`: network confined to `fetch.py`, pure model layer,
  thin renderers.
```

Bump `updated:` to today's date.

- [ ] **Step 2: Update `CLAUDE.md` article-mapping**

In `CLAUDE.md`, find the article-mapping table. Add a row:

```markdown
| Anything in `gitlab_admin/browse/**` (cache schema, owner derivation, exit codes, renderers) | `concepts/gitlab-admin/browse-command.md` |
```

Place it after the existing "GitLab API client wrapper" row.

- [ ] **Step 3: Update `index.md`**

In `knowledge/index.md`, add a row to the "gitlab-admin (this repo)" table:

```markdown
| [browse command — org map](concepts/gitlab-admin/browse-command.md) | Cache + renderers for browsing the GitLab instance. | 2026-05-19 |
```

- [ ] **Step 4: Append `log.md`**

Prepend a new entry to `knowledge/log.md` (newest at top, after the title and intro):

```markdown
## [2026-05-19] feature | gitlab-admin browse — foundation

- Implemented the `browse` foundation per Plan 1 of the design at
  `docs/superpowers/specs/2026-05-19-gitlab-org-browser-design.md`.
- Landed: `gitlab_admin/client.py`, `gitlab_admin/browse/` (cache, model,
  fetch, text and JSON renderers, CLI entry).
- Scope: expanded `purpose-and-scope.md` to a fourth task family
  (discovery / org navigation).
- Added: `concepts/gitlab-admin/browse-command.md` (load-bearing).
- HTML and interactive renderers tracked for Plans 2 and 3.
- Test surface: `pytest -v` runs across cache, model, fetch, both
  renderers, and CLI; fetch tests stub HTTP via `responses`.
```

- [ ] **Step 5: Validate everything**

Run: `scripts/validate-articles`
Expected: `✅ All 4 article(s) have valid frontmatter.`

Run: `pytest -v`
Expected: full suite passes.

- [ ] **Step 6: Commit**

```bash
git add knowledge/concepts/gitlab-admin/tech-stack.md CLAUDE.md knowledge/index.md knowledge/log.md
git commit -m "docs: finalize living-doc updates for browse foundation

Per same-task rule, all four doc updates land alongside the code they
describe:
- tech-stack.md gets the new dev-dep (responses) and sqlite note
- CLAUDE.md article-mapping points gitlab_admin/browse/** at the new article
- index.md links the new article
- log.md gets the feature entry"
```

---

## Acceptance criteria

After all 12 tasks, the following are true:

1. `pytest -v` passes (all tests across `tests/`).
2. `scripts/validate-articles` passes (4 articles, valid frontmatter).
3. `python -m gitlab_admin.browse --cache-path tests/fixtures/snapshot.sqlite` prints the expected tree from the golden file (with the snapshot footer).
4. `python -m gitlab_admin.browse --cache-path tests/fixtures/snapshot.sqlite --json | python -m json.tool` produces valid JSON matching the shape in spec §6.3.
5. `python -m gitlab_admin.browse --cache-path /tmp/nope.sqlite` exits 1 with the expected message.
6. `python -m gitlab_admin.browse --refresh` against a real GitLab instance (manual smoke test, not in CI) successfully writes `~/.cache/gitlab-admin/browse.sqlite` and prints a tree.
7. `git log --oneline` shows roughly 12 focused commits, each touching only the files for its task.

## What's not in this plan (Plans 2 & 3)

- HTML report renderer (`render_html.py`), Layout B, clipboard copy buttons.
- Interactive mode (`render_interactive.py`), `questionary` dep, action menu.
- ANSI colors in text tree output (the flag is wired through, the impl is a follow-up).

---

## Self-review notes

Internal checks I ran after writing this plan:

- **Spec coverage:** §1 (overview) → Task 1+3 articulate the shape. §2 (scope) → Task 11 expands purpose-and-scope. §3 (architecture) → Tasks 2, 4, 5, 6, 7. §4 (cache) → Tasks 4-5. §5 (CLI) → Task 9 (HTML/interactive flags return error 4 as a placeholder, mode-flag mutex enforced via argparse). §6.1 text → Task 8. §6.3 JSON → Task 10. §6.2 HTML and §6.4 interactive → out of scope by design (Plans 2 & 3). §7 error handling → Tasks 7, 9 (auth, network, cache-missing covered; per-entity 403 skip is a Plan 1 stretch not paid for). §8 edge cases → fixture covers archived, personal namespace, multi-owner, expired member; dedup tested in Task 7. §9 testing → covered by Tasks 5, 6, 7, 8, 9, 10. §10 not-built → carried forward. §11 living-doc impact → Tasks 3, 11, 12.
- **Placeholder scan:** no TBDs/TODOs found in the plan.
- **Type consistency:** `Tree`, `Group`, `Project`, `Member`, `Snapshot` defined in `model.py` (Task 6) and used identically in Tasks 8, 9, 10. `SnapshotRow` defined in `cache.py` (Task 4), used in Tasks 5, 7. `MissingCredentials` and `SyncFailed` defined in Tasks 2 and 7, used in Task 9.
- **Scope:** focused on text + JSON foundation. HTML and interactive get their own plans.
- **Ambiguity:** §7 mentions "per-entity 403 skip" — I scoped this *out* of Plan 1 because it requires a richer error model in `fetch.py` than the current "fail fast and atomic-replace" approach. If you want it, it lives in a future "harden fetch" plan or as an addendum to Plan 1.
