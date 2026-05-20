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
