import json
import re
from html.parser import HTMLParser

from gitlab_admin.browse import cache, model, render_html


def test_render_html_returns_string_with_doctype(fixture_db):
    with cache.connect(fixture_db) as conn:
        tree = model.build_tree(conn)
    html = render_html.render(tree)
    assert html.startswith("<!DOCTYPE html>")
    assert "</html>" in html


def test_render_html_embeds_json_data_island(fixture_db):
    """The data island is a <script type="application/json" id="org-data">
    block containing the same payload shape that render_json produces.
    JS will parse it on DOMContentLoaded."""
    with cache.connect(fixture_db) as conn:
        tree = model.build_tree(conn)
    html = render_html.render(tree)

    match = re.search(
        r'<script type="application/json" id="org-data">(.*?)</script>',
        html,
        flags=re.DOTALL,
    )
    assert match is not None, "data island script tag missing"
    payload = json.loads(match.group(1))

    assert payload["snapshot"]["gitlab_url"] == "https://gitlab.example.com"
    top_paths = sorted(g["full_path"] for g in payload["groups"])
    assert top_paths == ["data", "platform"]
    assert len(payload["personal_namespace_projects"]) == 1
