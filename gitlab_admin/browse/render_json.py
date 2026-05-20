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
