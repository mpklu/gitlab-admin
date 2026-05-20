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


class _IdCollector(HTMLParser):
    """Collects element id attributes for structural assertions."""

    def __init__(self):
        super().__init__()
        self.ids: set[str] = set()
        self.classes: set[str] = set()

    def handle_starttag(self, tag, attrs):
        attr_dict = dict(attrs)
        if "id" in attr_dict:
            self.ids.add(attr_dict["id"])
        if "class" in attr_dict:
            for cls in attr_dict["class"].split():
                self.classes.add(cls)


def _parse_ids_classes(html: str) -> tuple[set[str], set[str]]:
    p = _IdCollector()
    p.feed(html)
    return p.ids, p.classes


def test_render_html_has_layout_b_markers(fixture_db):
    with cache.connect(fixture_db) as conn:
        tree = model.build_tree(conn)
    html = render_html.render(tree)

    ids, classes = _parse_ids_classes(html)

    # Top-bar filter controls
    assert "search" in ids, "search input must have id='search'"
    assert "show-archived" in ids
    assert "show-stale-only" in ids

    # Visibility chip group
    assert "vis-chips" in ids
    assert "vis-chip" in classes

    # Two-pane layout
    assert "tree" in ids, "left pane must have id='tree'"
    assert "detail" in ids, "right pane must have id='detail'"


def test_render_html_includes_inline_css(fixture_db):
    """The page is self-contained: no <link rel="stylesheet">.
    All styling is in <style> blocks."""
    with cache.connect(fixture_db) as conn:
        tree = model.build_tree(conn)
    html = render_html.render(tree)

    assert '<link rel="stylesheet"' not in html, "must not link external CSS"
    style_match = re.search(r"<style>(.*?)</style>", html, flags=re.DOTALL)
    assert style_match is not None
    assert len(style_match.group(1)) > 200, "<style> block looks too small"


def _extract_inline_scripts(html: str) -> str:
    """Concatenate all <script> blocks that are NOT the JSON data
    island, so we can assert on the JS code."""
    matches = re.findall(
        r"<script(?![^>]*type=\"application/json\")[^>]*>(.*?)</script>",
        html,
        flags=re.DOTALL,
    )
    return "\n\n".join(matches)


def test_render_html_js_defines_required_handlers(fixture_db):
    """JS must define the handlers the UI depends on. Light contract
    test — confirms the named functions exist so refactors don't
    silently drop them. Behavior is verified by manual browser smoke;
    adopting a headless-browser test dep is not justified for a single
    self-contained file."""
    with cache.connect(fixture_db) as conn:
        tree = model.build_tree(conn)
    js = _extract_inline_scripts(render_html.render(tree))

    for name in (
        "renderTree",       # populates #tree from the data island
        "showDetail",       # populates #detail for a clicked project
        "applyFilters",     # honours search + checkboxes + vis chips
        "copyToClipboard",  # behind the clone-URL Copy buttons
    ):
        assert name in js, f"expected JS function `{name}` to exist"

    assert "DOMContentLoaded" in js


def test_render_html_js_does_not_use_innerhtml(fixture_db):
    """The renderer must build DOM via createElement + replaceChildren,
    never via innerHTML/outerHTML — even with trusted admin data, this
    is a defense-in-depth rule the codebase commits to."""
    with cache.connect(fixture_db) as conn:
        tree = model.build_tree(conn)
    js = _extract_inline_scripts(render_html.render(tree))
    assert ".innerHTML" not in js, "JS must not use innerHTML"
    assert ".outerHTML" not in js, "JS must not use outerHTML"
    assert "createElement" in js
    assert "replaceChildren" in js


def test_render_html_detail_panel_template_has_copy_buttons(fixture_db):
    """When a project is selected, the detail panel injects DOM that
    includes two clone fields (HTTPS + SSH) each with a copy button.
    Asserting on the JS source ensures the template logic hasn't
    silently dropped these UI affordances."""
    with cache.connect(fixture_db) as conn:
        tree = model.build_tree(conn)
    js = _extract_inline_scripts(render_html.render(tree))

    assert "copy-btn" in js, "copy button class missing from JS template"
    assert "HTTPS" in js
    assert "SSH" in js
    assert "http_url_to_repo" in js
    assert "ssh_url_to_repo" in js
