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
