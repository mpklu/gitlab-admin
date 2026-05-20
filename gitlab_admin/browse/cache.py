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
