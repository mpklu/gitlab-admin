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
