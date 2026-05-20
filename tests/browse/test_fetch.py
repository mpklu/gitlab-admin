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


def _stub_group_get(rsps, group_payload):
    rsps.add(
        responses.GET,
        f"https://gitlab.example.com/api/v4/groups/{group_payload['id']}",
        json=group_payload,
        status=200,
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


def _stub_project_get(rsps, project_payload):
    rsps.add(
        responses.GET,
        f"https://gitlab.example.com/api/v4/projects/{project_payload['id']}",
        json=project_payload,
        status=200,
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
    g1 = _group_payload(1, "platform")
    g2 = _group_payload(2, "platform/services", parent_id=1)
    p101 = _project_payload(101, 2, "platform/services/auth-svc")

    _stub_groups_list(stubbed_gitlab, [g1, g2])
    _stub_group_get(stubbed_gitlab, g1)
    _stub_group_get(stubbed_gitlab, g2)
    _stub_group_projects(stubbed_gitlab, 1, [])
    _stub_group_projects(stubbed_gitlab, 2, [p101])
    _stub_members_all(stubbed_gitlab, "group", 1, [
        _member_payload(10, "alice", 50),
    ])
    _stub_members_all(stubbed_gitlab, "group", 2, [])
    _stub_project_get(stubbed_gitlab, p101)
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

    g1 = _group_payload(1, "platform")

    # Stub a failure mid-sync.
    _stub_groups_list(stubbed_gitlab, [g1])
    _stub_group_get(stubbed_gitlab, g1)
    _stub_members_all(stubbed_gitlab, "group", 1, [])
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
    g1 = _group_payload(1, "platform")
    p101 = _project_payload(101, 1, "platform/auth")

    _stub_groups_list(stubbed_gitlab, [g1])
    _stub_group_get(stubbed_gitlab, g1)
    _stub_group_projects(stubbed_gitlab, 1, [p101])
    _stub_members_all(stubbed_gitlab, "group", 1, [])
    _stub_project_get(stubbed_gitlab, p101)
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


def test_sync_skips_project_already_seen_in_another_group(
    stubbed_gitlab, tmp_cache
):
    """Project 101 is in group 1's projects list AND in group 2's
    projects list (shared with the second group — common GitLab pattern
    for code-review/approvers groups). Sync must persist it only once
    and not crash on the UNIQUE constraint."""
    _stub_groups_list(stubbed_gitlab, [
        _group_payload(1, "team-platform"),
        _group_payload(2, "approvers"),
    ])
    _stub_group_get(stubbed_gitlab, _group_payload(1, "team-platform"))
    _stub_group_get(stubbed_gitlab, _group_payload(2, "approvers"))
    _stub_members_all(stubbed_gitlab, "group", 1, [])
    _stub_members_all(stubbed_gitlab, "group", 2, [])

    # Same project appears in both groups' project lists.
    shared = _project_payload(101, 1, "team-platform/billing")
    _stub_group_projects(stubbed_gitlab, 1, [shared])
    _stub_group_projects(stubbed_gitlab, 2, [shared])

    # Project get + members are stubbed ONCE — if we wrongly call them
    # twice, responses will raise ConnectionError because the second
    # call has no matching stub.
    _stub_project_get(stubbed_gitlab, shared)
    _stub_members_all(stubbed_gitlab, "project", 101, [])

    gl = client.get_client()
    fetch.sync_all(gl, cache_path=tmp_cache, tool_version="0.1.0")

    with cache.connect(tmp_cache) as conn:
        projects = cache.load_projects(conn)
    assert len(projects) == 1
    assert projects[0]["path_with_namespace"] == "team-platform/billing"


def test_sync_calls_progress_callback_with_status(stubbed_gitlab, tmp_cache):
    """The progress callback is invoked at each major step so the CLI
    can show live output instead of looking hung. Tests the wiring,
    not the exact wording."""
    _stub_groups_list(stubbed_gitlab, [_group_payload(1, "platform")])
    _stub_group_get(stubbed_gitlab, _group_payload(1, "platform"))
    _stub_members_all(stubbed_gitlab, "group", 1, [])
    _stub_group_projects(stubbed_gitlab, 1, [
        _project_payload(101, 1, "platform/auth"),
    ])
    _stub_project_get(stubbed_gitlab, _project_payload(101, 1, "platform/auth"))
    _stub_members_all(stubbed_gitlab, "project", 101, [])

    messages: list[str] = []
    gl = client.get_client()
    fetch.sync_all(
        gl,
        cache_path=tmp_cache,
        tool_version="0.1.0",
        progress=messages.append,
    )

    # Three things we depend on visually: a "listing" line at the start,
    # a per-group line containing the group's full_path, and a final
    # commit/done signal.
    joined = "\n".join(messages)
    assert "Listing groups" in joined
    assert "platform" in joined
    assert "[1/1]" in joined
    assert any("Committing" in m or "Done" in m for m in messages)


def test_sync_orphan_parent_id_becomes_top_level(stubbed_gitlab, tmp_cache):
    """If the API returns a subgroup whose parent isn't in the result
    set (admin can see the child but not the parent — rare but
    possible in self-hosted setups with quirks), sync nullifies the
    orphan parent_id so the group becomes top-level instead of
    crashing the FK constraint."""
    # Group 2 references parent_id=99, but group 99 is NOT returned.
    _stub_groups_list(stubbed_gitlab, [
        _group_payload(2, "lost-orphan", parent_id=99),
    ])
    _stub_group_get(stubbed_gitlab, _group_payload(2, "lost-orphan", parent_id=99))
    _stub_members_all(stubbed_gitlab, "group", 2, [])
    _stub_group_projects(stubbed_gitlab, 2, [])

    gl = client.get_client()
    fetch.sync_all(gl, cache_path=tmp_cache, tool_version="0.1.0")

    with cache.connect(tmp_cache) as conn:
        groups = cache.load_groups(conn)
    assert len(groups) == 1
    # Orphan parent_id was promoted to NULL (top-level).
    assert groups[0]["parent_id"] is None
    assert groups[0]["full_path"] == "lost-orphan"


def test_sync_handles_subgroup_before_parent_in_api_response(
    stubbed_gitlab, tmp_cache
):
    """GitLab's /api/v4/groups returns groups in API-defined order; there
    is no guarantee that parents arrive before their subgroups. The sync
    must defer FK checks so insertion order doesn't trip the
    `groups.parent_id REFERENCES groups(id)` constraint."""
    # Subgroup (2) is FIRST in the API response; its parent (1) is SECOND.
    _stub_groups_list(stubbed_gitlab, [
        _group_payload(2, "platform/services", parent_id=1),
        _group_payload(1, "platform"),
    ])
    _stub_group_get(stubbed_gitlab, _group_payload(2, "platform/services", parent_id=1))
    _stub_group_get(stubbed_gitlab, _group_payload(1, "platform"))
    _stub_members_all(stubbed_gitlab, "group", 2, [])
    _stub_members_all(stubbed_gitlab, "group", 1, [])
    _stub_group_projects(stubbed_gitlab, 2, [])
    _stub_group_projects(stubbed_gitlab, 1, [])

    gl = client.get_client()
    fetch.sync_all(gl, cache_path=tmp_cache, tool_version="0.1.0")

    with cache.connect(tmp_cache) as conn:
        groups = cache.load_groups(conn)
    assert {g["full_path"] for g in groups} == {"platform", "platform/services"}
