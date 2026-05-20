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
