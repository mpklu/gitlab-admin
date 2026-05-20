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
