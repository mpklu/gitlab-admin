"""Pure in-memory tree built from cache rows. No I/O, no clock, no env."""

from __future__ import annotations

import json
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


def _topics(s: Optional[str]) -> list[str]:
    if not s:
        return []
    try:
        value = json.loads(s)
    except ValueError:
        return []
    return value if isinstance(value, list) else []


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
