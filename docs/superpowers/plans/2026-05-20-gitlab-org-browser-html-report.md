# GitLab Org Browser — HTML Report (Plan 2 of 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `render_html.py` and wire `--html PATH` so `./run.sh --html out.html` produces a single self-contained HTML file with Layout B (lean tree on left, detail panel on right with clone URLs + copy buttons), client-side search and filtering, no external assets.

**Architecture:** A pure Python module `gitlab_admin/browse/render_html.py` returning a complete HTML string with embedded CSS, JS, and a JSON data island. The JS is vanilla (no framework, no CDN), reads the data island once on `DOMContentLoaded`, renders the tree via DOM `createElement` / `replaceChildren` (no `innerHTML`), wires search/filter inputs, and populates the right pane on row click. The CLI stub for `--html` is replaced with a writer that calls the renderer and writes to disk. Tests assert structural HTML correctness via stdlib `html.parser`; JS behavior is verified via manual browser smoke-test only (no browser test deps added).

**Tech Stack:** Pure Python 3.11 stdlib (`html.parser` for tests, `json` for the data island). No new runtime deps; no JS frameworks; no CSS frameworks.

**Spec:** [`docs/superpowers/specs/2026-05-19-gitlab-org-browser-design.md`](../specs/2026-05-19-gitlab-org-browser-design.md) §6.2 (Layout B + detail panel field set), §5 (CLI behaviour for `--html`), §11 (article impact).

---

## File map

| File | Responsibility |
| --- | --- |
| `gitlab_admin/browse/render_html.py` | New. Pure function `render(tree: Tree) -> str` returning a complete self-contained HTML document. |
| `gitlab_admin/browse/__main__.py` | Modify. Replace the `--html`/`-i` stub block with: if `args.html`, call `render_html.render(tree)` and write to `args.html`. |
| `tests/browse/test_render_html.py` | New. Structural tests via stdlib `html.parser` + `re` for JS-function presence + integration with the fixture DB. |
| `knowledge/concepts/gitlab-admin/browse-command.md` | Modify. Add an "HTML report (Layout B)" section documenting field set, filters, and the self-contained-file commitment. |
| `knowledge/log.md` | Modify. Append a `[2026-05-20] feature | HTML report` entry. |

---

## Layout B reminder

Top toolbar with search input + filter chips. Below, a 2-column flex layout:

- **Left (`#tree`)** — collapsible tree of groups + projects. Group rows show owner annotation; project rows show name + path + a subdued metadata line.
- **Right (`#detail`)** — initial placeholder ("Select a project"); on project click, populates with: name, breadcrumb path, owner, visibility pill, last-updated, default branch, HTTPS clone URL with `📋 Copy` button, SSH clone URL with `📋 Copy` button, maintainers list, "↗ Open in GitLab" link.

Filters (top-bar):
- Search box (matches against project path-with-namespace and group full-path).
- `Show archived` checkbox (default OFF — hide archived).
- `Only stale (>1y)` checkbox (default OFF).
- Visibility chip group: three chips for `private`, `internal`, `public` (all ON by default; clicking a chip toggles that visibility's projects).

**Security note:** the JS uses `document.createElement` + `replaceChildren` exclusively. It never assigns to `innerHTML` or `outerHTML`. The data island is parsed via `JSON.parse`, never interpolated as HTML. This keeps the renderer safe against XSS from project names, descriptions, member names, etc., even though the data ultimately comes from a trusted admin source.

---

## Task 1: `render_html.py` skeleton + JSON data island

**Files:**
- Create: `gitlab_admin/browse/render_html.py`
- Create: `tests/browse/test_render_html.py`

- [ ] **Step 1: Write failing test**

Create `tests/browse/test_render_html.py`:

```python
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
```

- [ ] **Step 2: Run test, verify failure**

Run: `uv run pytest tests/browse/test_render_html.py -v`
Expected: `ImportError: cannot import name 'render_html' from 'gitlab_admin.browse'`

- [ ] **Step 3: Implement `render_html.py` skeleton**

Create `gitlab_admin/browse/render_html.py`:

```python
"""Tree -> single self-contained HTML report (Layout B).

The output is a complete HTML5 document with inline CSS, inline JS,
and a JSON data island. No external assets, no CDN.

Security: the JS never uses innerHTML / outerHTML. All DOM construction
goes through createElement + replaceChildren so untrusted strings
(project names, descriptions) can't be interpreted as HTML.
"""

from __future__ import annotations

from . import render_json
from .model import Tree

# CSS and JS land in Tasks 2 and 3. For now the template is the minimum
# that surfaces the data island and a stub body.

_HTML_HEAD = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>gitlab-admin — org browser</title>
<style>/* CSS lands in Task 2 */</style>
</head>
"""

_HTML_BODY_STUB = """\
<body>
<script type="application/json" id="org-data">{data_json}</script>
<script>/* JS lands in Task 3 */</script>
</body>
</html>
"""


def render(tree: Tree) -> str:
    """Return a complete self-contained HTML string."""
    data_json = render_json.render(tree).rstrip()
    return _HTML_HEAD + _HTML_BODY_STUB.format(data_json=data_json)
```

- [ ] **Step 4: Run tests, verify pass**

Run: `uv run pytest tests/browse/test_render_html.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add gitlab_admin/browse/render_html.py tests/browse/test_render_html.py
git commit -m "feat(browse): render_html skeleton with JSON data island

DRY data shape: reuses render_json.render() so the data island matches
the standalone --json output exactly. CSS and JS land in subsequent
tasks; this commit just establishes the module and the data-island
contract."
```

---

## Task 2: HTML layout + inline CSS for Layout B

**Files:**
- Modify: `gitlab_admin/browse/render_html.py`
- Modify: `tests/browse/test_render_html.py`

- [ ] **Step 1: Write failing tests for the layout**

Append to `tests/browse/test_render_html.py`:

```python
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
```

- [ ] **Step 2: Run tests, verify failure**

Run: `uv run pytest tests/browse/test_render_html.py -v`
Expected: 2 new tests fail (ids `search`, `show-archived`, etc. missing).

- [ ] **Step 3: Replace render_html.py with the layout + CSS version**

Replace the contents of `gitlab_admin/browse/render_html.py` with:

```python
"""Tree -> single self-contained HTML report (Layout B).

The output is a complete HTML5 document with inline CSS, inline JS,
and a JSON data island. No external assets, no CDN. Email it, drop
it on a shared drive, AirDrop it — it works offline.

Security: the JS never uses innerHTML / outerHTML. All DOM construction
goes through createElement + replaceChildren so untrusted strings
(project names, descriptions) can't be interpreted as HTML.
"""

from __future__ import annotations

from . import render_json
from .model import Tree

_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body {
  height: 100%;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui,
               sans-serif;
  font-size: 14px;
  color: #ddd;
  background: #14171c;
}
body { display: flex; flex-direction: column; }

header {
  flex: 0 0 auto;
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 12px 16px;
  background: #1c1f24;
  border-bottom: 1px solid #2a2e36;
}
header h1 {
  font-size: 15px;
  font-weight: 600;
  margin-right: 12px;
}
#search {
  flex: 1;
  max-width: 480px;
  background: #0f1115;
  border: 1px solid #2a2e36;
  border-radius: 4px;
  color: #ddd;
  padding: 6px 10px;
  font-size: 13px;
}
#search:focus { outline: 1px solid #6cb6ff; border-color: #6cb6ff; }
.toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #aaa;
  font-size: 12px;
  cursor: pointer;
  user-select: none;
}
.toggle input { accent-color: #6cb6ff; }
#vis-chips { display: flex; gap: 4px; margin-left: auto; }
.vis-chip {
  background: #2a2e36;
  border: 1px solid #3a3e46;
  color: #aaa;
  padding: 3px 9px;
  border-radius: 999px;
  font-size: 11px;
  cursor: pointer;
  user-select: none;
}
.vis-chip.active { background: #243a4a; border-color: #2c5577; color: #cfe; }

main {
  flex: 1 1 auto;
  display: flex;
  min-height: 0;
}
#tree {
  flex: 0 0 50%;
  overflow-y: auto;
  padding: 12px 8px 24px 12px;
  border-right: 1px solid #2a2e36;
}
#detail {
  flex: 1 1 auto;
  overflow-y: auto;
  padding: 18px 22px;
}

.group { margin: 1px 0; }
.group-header {
  display: flex;
  gap: 6px;
  align-items: baseline;
  padding: 2px 4px;
  border-radius: 3px;
  cursor: pointer;
  user-select: none;
}
.group-header:hover { background: #1f2329; }
.group-header .caret {
  display: inline-block;
  width: 10px;
  color: #888;
  font-size: 10px;
}
.group-header .name { color: #e8a93a; font-weight: 500; }
.group-header .meta { color: #888; font-size: 11px; }
.group-children { padding-left: 18px; }
.group.collapsed > .group-children { display: none; }

.project {
  display: flex;
  gap: 8px;
  align-items: baseline;
  padding: 2px 6px;
  border-radius: 3px;
  cursor: pointer;
  user-select: none;
}
.project:hover { background: #1f2329; }
.project.selected { background: #243a4a; }
.project .name { color: #6cb6ff; }
.project .meta { color: #888; font-size: 11px; margin-left: auto; }

.pill {
  display: inline-block;
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 3px;
  background: #2a2e36;
  color: #aaa;
}
.pill.archived { background: #4a2424; color: #f4a; }
.pill.prv { background: #243a4a; color: #6cf; }
.pill.int { background: #2a3d2a; color: #9c6; }
.pill.pub { background: #3a2a3a; color: #c69; }

#detail .placeholder { color: #666; font-style: italic; }
#detail h2 { font-size: 18px; font-weight: 600; color: #fff; margin-bottom: 4px; }
#detail .crumb { color: #888; font-size: 12px; margin-bottom: 18px; }
#detail .label {
  color: #888;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 4px;
}
#detail .section { margin-bottom: 16px; }
#detail .row { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 10px; }
#detail .row > div { flex: 1 1 140px; }
#detail .clone-field {
  display: flex;
  align-items: center;
  gap: 8px;
}
#detail .clone-field code {
  flex: 1;
  font-family: ui-monospace, "SF Mono", monospace;
  font-size: 12px;
  background: #0f1115;
  padding: 6px 10px;
  border-radius: 4px;
  color: #ddd;
  border: 1px solid #2a2e36;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.copy-btn {
  background: #2a2e36;
  border: 1px solid #3a3e46;
  color: #ddd;
  padding: 5px 10px;
  border-radius: 4px;
  font-size: 11px;
  cursor: pointer;
}
.copy-btn:hover { background: #3a3e46; }
.copy-btn.copied { background: #2c5a2c; color: #cfd; }
#detail a.gitlab-link { color: #6cb6ff; text-decoration: none; font-size: 12px; }
#detail a.gitlab-link:hover { text-decoration: underline; }

.snapshot-footer {
  padding: 8px 16px;
  font-size: 11px;
  color: #666;
  background: #1c1f24;
  border-top: 1px solid #2a2e36;
}
"""

_HTML_HEAD = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>gitlab-admin — org browser</title>
<style>{css}</style>
</head>
"""

_HTML_BODY_TEMPLATE = """\
<body>
<header>
  <h1>gitlab-admin · org browser</h1>
  <input id="search" type="search" placeholder="search project or group path…" autocomplete="off">
  <label class="toggle"><input type="checkbox" id="show-archived"> archived</label>
  <label class="toggle"><input type="checkbox" id="show-stale-only"> stale &gt;1y</label>
  <div id="vis-chips">
    <span class="vis-chip active" data-vis="private">private</span>
    <span class="vis-chip active" data-vis="internal">internal</span>
    <span class="vis-chip active" data-vis="public">public</span>
  </div>
</header>
<main>
  <div id="tree"></div>
  <div id="detail"><p class="placeholder">Select a project on the left to see its details.</p></div>
</main>
<div class="snapshot-footer" id="snapshot-footer"></div>
<script type="application/json" id="org-data">{data_json}</script>
<script>/* JS lands in Task 3 */</script>
</body>
</html>
"""


def render(tree: Tree) -> str:
    """Return a complete self-contained HTML string for the org browser."""
    data_json = render_json.render(tree).rstrip()
    return _HTML_HEAD.format(css=_CSS) + _HTML_BODY_TEMPLATE.format(data_json=data_json)
```

- [ ] **Step 4: Run tests, verify pass**

Run: `uv run pytest tests/browse/test_render_html.py -v`
Expected: all 4 tests pass.

- [ ] **Step 5: Smoke check**

Run:

```bash
uv run python -c "from gitlab_admin.browse import cache, model, render_html; \
from pathlib import Path; \
ctx = cache.connect(Path('tests/fixtures/snapshot.sqlite')); conn = ctx.__enter__(); \
tree = model.build_tree(conn); \
Path('/tmp/preview.html').write_text(render_html.render(tree)); \
ctx.__exit__(None, None, None); \
print('wrote /tmp/preview.html')"
```

Open `/tmp/preview.html` in a browser. You should see the header bar (title, search box, two toggles, three visibility chips) and the left/right panes — but the tree pane is empty and clicking does nothing (Task 3 adds the JS).

- [ ] **Step 6: Commit**

```bash
git add gitlab_admin/browse/render_html.py tests/browse/test_render_html.py
git commit -m "feat(browse): HTML layout B + inline CSS

Static structure with the IDs/classes the JS in Task 3 will hook into:
#search, #show-archived, #show-stale-only, #vis-chips, .vis-chip,
#tree, #detail, #snapshot-footer. Self-contained: no external <link>s.
JS is still a stub; interactivity lands next."
```

---

## Task 3: Inline JS — tree rendering, detail panel, filters, copy buttons

**Files:**
- Modify: `gitlab_admin/browse/render_html.py`
- Modify: `tests/browse/test_render_html.py`

- [ ] **Step 1: Write failing tests for JS presence**

Append to `tests/browse/test_render_html.py`:

```python
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
    # Allow the word `innerHTML` to appear in comments only — assert no
    # assignment patterns. We're strict here: no `.innerHTML` at all.
    assert ".innerHTML" not in js, "JS must not use innerHTML"
    assert ".outerHTML" not in js, "JS must not use outerHTML"
    # Positive: createElement and replaceChildren are present.
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
```

- [ ] **Step 2: Run tests, verify failure**

Run: `uv run pytest tests/browse/test_render_html.py -v`
Expected: 3 new tests fail (no `renderTree`, no `createElement`, no `copy-btn`).

- [ ] **Step 3: Add the JS constant and interpolate it into the body template**

In `gitlab_admin/browse/render_html.py`, add a `_JS` constant right after `_CSS`:

```python
_JS = """
(function() {
  'use strict';

  // ── State ────────────────────────────────────────────────
  const ORG = JSON.parse(document.getElementById('org-data').textContent);
  const STATE = {
    search: '',
    showArchived: false,
    showStaleOnly: false,
    visibility: { private: true, internal: true, public: true },
  };
  const ONE_YEAR_MS = 365 * 24 * 60 * 60 * 1000;

  // ── Helpers ──────────────────────────────────────────────
  // Build a DOM element without ever parsing HTML. attrs can include
  // `class`, `dataset` (a sub-object), event listeners under `on<Event>`
  // keys, or plain attributes. children is an array of strings (text)
  // or other Nodes; nulls are skipped.
  function el(tag, attrs, children) {
    const e = document.createElement(tag);
    if (attrs) {
      for (const k in attrs) {
        if (k === 'class') e.className = attrs[k];
        else if (k === 'dataset') {
          for (const d in attrs.dataset) e.dataset[d] = attrs.dataset[d];
        } else if (k.startsWith('on')) {
          e.addEventListener(k.slice(2).toLowerCase(), attrs[k]);
        } else e.setAttribute(k, attrs[k]);
      }
    }
    if (children) {
      for (const c of children) {
        if (c == null) continue;
        e.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
      }
    }
    return e;
  }

  function shortDate(iso) { return iso ? iso.split('T')[0] : ''; }

  function visClass(v) { return v === 'private' ? 'prv' : v === 'internal' ? 'int' : 'pub'; }

  // ── Tree rendering ──────────────────────────────────────
  function renderTree() {
    const root = document.getElementById('tree');
    const children = [];
    for (const g of ORG.groups) children.push(renderGroup(g));
    if (ORG.personal_namespace_projects && ORG.personal_namespace_projects.length > 0) {
      const personal = el('div', { class: 'group' }, [
        el('div', { class: 'group-header' }, [
          el('span', { class: 'caret' }, ['▾']),
          el('span', { class: 'name' }, ['👤 Personal projects']),
        ]),
        el('div', { class: 'group-children' },
          ORG.personal_namespace_projects.map(function(p) { return renderProject(p); })),
      ]);
      children.push(personal);
    }
    root.replaceChildren.apply(root, children);
  }

  function renderGroup(g) {
    const header = el('div', { class: 'group-header' }, [
      el('span', { class: 'caret' }, ['▾']),
      el('span', { class: 'name' }, ['📁 ' + g.full_path]),
    ]);
    const childKids = [];
    for (const sg of g.children_groups) childKids.push(renderGroup(sg));
    for (const p of g.projects) childKids.push(renderProject(p));
    const childrenEl = el('div', { class: 'group-children' }, childKids);
    const groupEl = el('div', { class: 'group' }, [header, childrenEl]);
    header.addEventListener('click', function() {
      groupEl.classList.toggle('collapsed');
    });
    return groupEl;
  }

  function renderProject(p) {
    const archivedPill = p.archived
      ? el('span', { class: 'pill archived' }, ['archived'])
      : null;
    const projEl = el('div', {
      class: 'project',
      dataset: {
        path: p.path_with_namespace,
        visibility: p.visibility,
        archived: String(p.archived),
        lastActivity: p.last_activity_at,
      },
    }, [
      el('span', { class: 'name' }, ['▢ ' + p.name]),
      archivedPill,
      el('span', { class: 'meta' }, [
        p.owner + ' · ' + shortDate(p.last_activity_at) + ' · ',
      ]),
      el('span', { class: 'pill ' + visClass(p.visibility) }, [visClass(p.visibility)]),
    ]);
    projEl.addEventListener('click', function() { showDetail(p, projEl); });
    return projEl;
  }

  // ── Detail panel ────────────────────────────────────────
  function showDetail(p, rowEl) {
    const previouslySelected = document.querySelectorAll('.project.selected');
    for (const s of previouslySelected) s.classList.remove('selected');
    if (rowEl) rowEl.classList.add('selected');

    const detail = document.getElementById('detail');

    const breadcrumb = p.path_with_namespace.split('/').slice(0, -1).join(' / ') || '(personal)';

    const maintainers = (p.members || [])
      .filter(function(m) { return m.access_level >= 40 && !m.is_expired; })
      .map(function(m) { return m.username; })
      .join(', ') || '(none)';

    const sections = [
      el('h2', null, [p.name]),
      el('div', { class: 'crumb' }, [breadcrumb]),
      el('div', { class: 'section row' }, [
        el('div', null, [
          el('div', { class: 'label' }, ['Owner']),
          document.createTextNode(p.owner),
        ]),
        el('div', null, [
          el('div', { class: 'label' }, ['Visibility']),
          el('span', { class: 'pill ' + visClass(p.visibility) }, [p.visibility]),
        ]),
      ]),
      el('div', { class: 'section row' }, [
        el('div', null, [
          el('div', { class: 'label' }, ['Last updated']),
          document.createTextNode(shortDate(p.last_activity_at)),
        ]),
        el('div', null, [
          el('div', { class: 'label' }, ['Default branch']),
          document.createTextNode(p.default_branch || '(none)'),
        ]),
      ]),
      cloneField('Clone — HTTPS', p.http_url_to_repo),
      cloneField('Clone — SSH', p.ssh_url_to_repo),
      el('div', { class: 'section' }, [
        el('div', { class: 'label' }, ['Maintainers (Owner / Maintainer access)']),
        document.createTextNode(maintainers),
      ]),
    ];

    if (p.web_url) {
      sections.push(el('div', { class: 'section' }, [
        el('a', { class: 'gitlab-link', href: p.web_url, target: '_blank', rel: 'noopener' },
          ['↗ Open in GitLab']),
      ]));
    }

    detail.replaceChildren.apply(detail, sections);
  }

  function cloneField(label, url) {
    // The URL field references http_url_to_repo / ssh_url_to_repo
    // from the project payload. Naming them explicitly so test
    // assertions on the JS source can verify the binding hasn't
    // silently dropped.
    return el('div', { class: 'section' }, [
      el('div', { class: 'label' }, [label]),
      el('div', { class: 'clone-field' }, [
        el('code', null, [url]),
        el('button', {
          class: 'copy-btn',
          onclick: function(ev) { copyToClipboard(url, ev.target); },
        }, ['📋 Copy']),
      ]),
    ]);
  }

  function copyToClipboard(text, btn) {
    navigator.clipboard.writeText(text).then(function() {
      const original = btn.textContent;
      btn.textContent = '✓ Copied';
      btn.classList.add('copied');
      setTimeout(function() {
        btn.textContent = original;
        btn.classList.remove('copied');
      }, 1200);
    }).catch(function() {
      btn.textContent = '✗ failed';
      setTimeout(function() { btn.textContent = '📋 Copy'; }, 1200);
    });
  }

  // ── Filters ─────────────────────────────────────────────
  function applyFilters() {
    const q = STATE.search.toLowerCase();
    const now = Date.now();
    const rows = document.querySelectorAll('#tree .project');
    for (const row of rows) {
      const path = (row.dataset.path || '').toLowerCase();
      const vis = row.dataset.visibility;
      const archived = row.dataset.archived === 'true';
      const lastIso = row.dataset.lastActivity;
      const ageMs = lastIso ? (now - Date.parse(lastIso)) : 0;
      const stale = ageMs > ONE_YEAR_MS;

      let keep = true;
      if (q && !path.includes(q)) keep = false;
      if (!STATE.showArchived && archived) keep = false;
      if (STATE.showStaleOnly && !stale) keep = false;
      if (!STATE.visibility[vis]) keep = false;

      row.style.display = keep ? '' : 'none';
    }
    // Hide empty groups whose children are all filtered out.
    const groups = document.querySelectorAll('#tree .group');
    for (const g of groups) {
      const visibleProjects = g.querySelectorAll('.project:not([style*="display: none"])');
      g.style.display = visibleProjects.length > 0 ? '' : 'none';
    }
  }

  // ── Snapshot footer ─────────────────────────────────────
  function renderFooter() {
    const f = document.getElementById('snapshot-footer');
    if (!ORG.snapshot) {
      f.textContent = '(no snapshot recorded — was this rendered from an empty cache?)';
      return;
    }
    const totalProjects =
      countProjects(ORG.groups) + (ORG.personal_namespace_projects || []).length;
    const totalGroups = countGroups(ORG.groups);
    f.textContent =
      'Snapshot: ' + ORG.snapshot.completed_at +
      ' · ' + ORG.snapshot.gitlab_url +
      ' · ' + totalProjects + ' projects across ' + totalGroups + ' groups';
  }
  function countProjects(groups) {
    return groups.reduce(function(n, g) {
      return n + g.projects.length + countProjects(g.children_groups);
    }, 0);
  }
  function countGroups(groups) {
    return groups.reduce(function(n, g) {
      return n + 1 + countGroups(g.children_groups);
    }, 0);
  }

  // ── Wire up ─────────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', function() {
    renderTree();
    renderFooter();

    document.getElementById('search').addEventListener('input', function(ev) {
      STATE.search = ev.target.value;
      applyFilters();
    });
    document.getElementById('show-archived').addEventListener('change', function(ev) {
      STATE.showArchived = ev.target.checked;
      applyFilters();
    });
    document.getElementById('show-stale-only').addEventListener('change', function(ev) {
      STATE.showStaleOnly = ev.target.checked;
      applyFilters();
    });
    const chips = document.querySelectorAll('.vis-chip');
    for (const chip of chips) {
      chip.addEventListener('click', function() {
        const v = chip.dataset.vis;
        STATE.visibility[v] = !STATE.visibility[v];
        chip.classList.toggle('active');
        applyFilters();
      });
    }
  });
})();
"""
```

Then in the same file, change the body template's `<script>` line and the `render()` function to interpolate `_JS`:

Replace the existing `<script>/* JS lands in Task 3 */</script>` line inside `_HTML_BODY_TEMPLATE` with `<script>{js}</script>`.

Replace the existing `render()` function body with:

```python
def render(tree: Tree) -> str:
    """Return a complete self-contained HTML string for the org browser."""
    data_json = render_json.render(tree).rstrip()
    return _HTML_HEAD.format(css=_CSS) + _HTML_BODY_TEMPLATE.format(
        data_json=data_json, js=_JS
    )
```

- [ ] **Step 4: Run tests, verify pass**

Run: `uv run pytest tests/browse/test_render_html.py -v`
Expected: all 7 tests pass.

- [ ] **Step 5: Browser smoke test**

Run:

```bash
uv run python -c "from gitlab_admin.browse import cache, model, render_html; \
from pathlib import Path; \
ctx = cache.connect(Path('tests/fixtures/snapshot.sqlite')); conn = ctx.__enter__(); \
tree = model.build_tree(conn); \
Path('/tmp/preview.html').write_text(render_html.render(tree)); \
ctx.__exit__(None, None, None); \
print('open /tmp/preview.html')"
open /tmp/preview.html   # macOS; on Linux: xdg-open /tmp/preview.html
```

In the browser, verify:
- The tree shows `platform` (expandable) and `data` and the personal-projects pseudo-root.
- Clicking a project (e.g. `auth-svc`) populates the right pane.
- The right pane shows owner, visibility pill, last-updated, default branch, two clone-URL fields with Copy buttons, maintainers list, and an "Open in GitLab" link.
- Clicking "📋 Copy" briefly shows "✓ Copied" and writes the URL to the clipboard (paste somewhere to verify).
- Typing in the search box filters the tree live.
- Toggling "archived" makes `legacy-auth` appear/disappear.
- Clicking a visibility chip greys it out and hides projects of that visibility.

If anything misbehaves, fix in `_JS` and re-run the smoke step. Open DevTools to catch JS errors; the structural tests above can't see runtime issues.

- [ ] **Step 6: Commit**

```bash
git add gitlab_admin/browse/render_html.py tests/browse/test_render_html.py
git commit -m "feat(browse): inline JS for tree, filters, detail panel, clipboard copy

Vanilla JS, no framework. Builds DOM with createElement +
replaceChildren — never innerHTML — so untrusted strings can't be
interpreted as HTML. Reads the data island once on DOMContentLoaded,
renders the tree, wires search/archived/stale/visibility filters,
populates #detail on row click with clone URLs + Copy buttons via
navigator.clipboard.writeText. JS is behind structural tests
asserting the named functions exist; behavior verified by manual
browser smoke."
```

---

## Task 4: Wire `--html PATH` in the CLI

**Files:**
- Modify: `gitlab_admin/browse/__main__.py`
- Modify: `tests/browse/test_main.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/browse/test_main.py`:

```python
def test_html_flag_writes_file(fixture_db, tmp_path):
    out = tmp_path / "report.html"
    rc = browse_main.main([
        "--cache-path", str(fixture_db),
        "--html", str(out),
    ])
    assert rc == 0
    assert out.exists()
    content = out.read_text()
    assert content.startswith("<!DOCTYPE html>")
    assert "auth-svc" in content  # project data made it in via data island


def test_html_flag_overwrites_existing(fixture_db, tmp_path):
    out = tmp_path / "report.html"
    out.write_text("OLD CONTENT")
    rc = browse_main.main([
        "--cache-path", str(fixture_db),
        "--html", str(out),
    ])
    assert rc == 0
    assert "OLD CONTENT" not in out.read_text()
    assert "<!DOCTYPE html>" in out.read_text()


def test_html_flag_returns_4_when_path_is_a_directory(
    fixture_db, tmp_path, capsys
):
    """Writing to a directory must surface a clear error, not a stack
    trace. Spec §7 specifies exit 4 for I/O failures on --html PATH."""
    rc = browse_main.main([
        "--cache-path", str(fixture_db),
        "--html", str(tmp_path),  # directory, not a file
    ])
    captured = capsys.readouterr()
    assert rc == 4
    assert "cannot write" in captured.err.lower() or "is a directory" in captured.err.lower()
```

- [ ] **Step 2: Run tests, verify failure**

Run: `uv run pytest tests/browse/test_main.py -v -k html_flag`
Expected: all three tests fail because `--html` currently returns `EXIT_UNEXPECTED` (4) immediately, before ever attempting a write.

- [ ] **Step 3: Remove the stub and wire `--html`**

In `gitlab_admin/browse/__main__.py`, locate the block:

```python
    if args.html is not None or args.interactive:
        print(
            "--html and --interactive land in Plan 2 / Plan 3. Use the text "
            "renderer or --json for now.",
            file=sys.stderr,
        )
        return EXIT_UNEXPECTED
```

Replace it with:

```python
    if args.interactive:
        print(
            "--interactive lands in Plan 3. Use the text renderer, --json, "
            "or --html for now.",
            file=sys.stderr,
        )
        return EXIT_UNEXPECTED
```

Next, find this section:

```python
    with cache.connect(cache_path) as conn:
        tree = model.build_tree(conn)

    if args.json:
        from . import render_json
        sys.stdout.write(render_json.render(tree))
        return EXIT_OK
```

And add an `--html` branch right after the `--json` branch (still inside `main()`):

```python
    with cache.connect(cache_path) as conn:
        tree = model.build_tree(conn)

    if args.json:
        from . import render_json
        sys.stdout.write(render_json.render(tree))
        return EXIT_OK

    if args.html is not None:
        from . import render_html
        try:
            args.html.write_text(render_html.render(tree), encoding="utf-8")
        except OSError as exc:
            print(f"error: cannot write {args.html}: {exc}", file=sys.stderr)
            return EXIT_UNEXPECTED
        print(f"[browse] wrote {args.html}", file=sys.stderr)
        return EXIT_OK
```

- [ ] **Step 4: Run all tests, verify pass**

Run: `uv run pytest -v`
Expected: all tests pass.

- [ ] **Step 5: End-to-end smoke**

Run:

```bash
./run.sh --cache-path tests/fixtures/snapshot.sqlite --html /tmp/preview.html
open /tmp/preview.html
```

Should print `[browse] wrote /tmp/preview.html` to stderr and exit 0. The browser should show a working Layout B page.

Also verify mutex:

```bash
./run.sh --cache-path tests/fixtures/snapshot.sqlite --html /tmp/a.html --json
```

Should fail with argparse's mutex error (exit 2 from argparse), not run anything.

- [ ] **Step 6: Commit**

```bash
git add gitlab_admin/browse/__main__.py tests/browse/test_main.py
git commit -m "feat(browse): wire --html flag to render_html.render()

Removes the Plan-1 stub for --html (still keeps the --interactive stub
since Plan 3 hasn't landed). The CLI writes a self-contained HTML
file to the given path on a successful render; argparse already
guarantees --html is mutually exclusive with --json and -i.

A friendly '[browse] wrote PATH' notice goes to stderr so it doesn't
clash with the renderer's own (empty) stdout output. Writing to a
non-writeable target (e.g. a directory) returns exit 4 with a clear
error message per spec §7."
```

---

## Task 5: Living-doc updates

**Files:**
- Modify: `knowledge/concepts/gitlab-admin/browse-command.md`
- Modify: `knowledge/log.md`

- [ ] **Step 1: Refresh the "CLI shape" section in `browse-command.md`**

Open `knowledge/concepts/gitlab-admin/browse-command.md`. Find the section currently titled `## CLI shape (this plan)` and its code block. Use Edit to change both the heading and the contents so it reads:

```markdown
## CLI shape

```text
./run.sh                                      # text tree from cache
./run.sh --refresh                            # re-fetch then text tree
./run.sh --json                               # JSON to stdout
./run.sh --html out.html                      # write Layout B HTML report
./run.sh --group platform/services
./run.sh --owner kun.lu
./run.sh --stale-days 365
./run.sh --no-archived
./run.sh --cache-path ./snapshot.sqlite
```
```

- [ ] **Step 2: Add an "HTML report (Layout B)" section**

In the same file, find the existing "Per-entity 403 handling" section and add a new section immediately AFTER it (and before "Owner derivation"):

```markdown
### HTML report (Layout B)

`--html PATH` writes a single self-contained `.html` file: inline CSS,
inline JS, and a JSON data island holding the same payload as `--json`.
No external assets, no CDN, no fonts. Email it, drop it on a shared
drive, AirDrop it — it works offline.

Layout B: lean collapsible tree on the left; detail panel on the right
that populates when a project row is clicked. Detail-panel fields:

- Name and breadcrumb path
- Owner (derived per the rules above) and a visibility pill
- Last-updated date and default branch
- HTTPS clone URL with a `📋 Copy` button (writes to clipboard via
  `navigator.clipboard.writeText`)
- SSH clone URL with a `📋 Copy` button
- Maintainers (de-duplicated, Owner or Maintainer access only,
  expired members excluded)
- "↗ Open in GitLab" link to the project's `web_url`

Client-side filters in the top toolbar:

- **Search** matches against project path-with-namespace (case-insensitive).
- **Archived** checkbox — hidden by default; tick to include archived projects.
- **Stale &gt;1y** checkbox — show only projects with no activity in the last year.
- **Visibility chips** — three toggleable chips (`private` / `internal` /
  `public`). Clicking a chip hides that visibility class.

Empty groups (all children filtered out) collapse to nothing so the
tree stays scannable.

The JS is vanilla — no framework, no external scripts. It builds the
DOM with `createElement` + `replaceChildren` and never uses
`innerHTML`, so project names / descriptions / member names cannot be
interpreted as HTML even though they ultimately come from a trusted
admin source. Tests assert this contract.

Structural HTML and JS-presence tests run in CI; behaviour is verified
by manual browser smoke since adopting a headless-browser test dep
isn't justified for a single self-contained file.
```

Bump the `updated:` field in the frontmatter to `2026-05-20`.

- [ ] **Step 3: Prepend a log entry**

Open `knowledge/log.md`. Prepend a new entry immediately after the intro paragraph (before the most recent existing entry):

```markdown
## [2026-05-20] feature | HTML report (Layout B)

- Implemented Plan 2 of the design at
  `docs/superpowers/specs/2026-05-19-gitlab-org-browser-design.md`.
- Added: `gitlab_admin/browse/render_html.py` — pure renderer returning
  a single self-contained HTML string with inline CSS, inline JS, and
  a JSON data island.
- Updated: `gitlab_admin/browse/__main__.py` — replaced the `--html`
  stub with a writer that emits the report to the given path.
- Updated: `concepts/gitlab-admin/browse-command.md` adds an
  HTML report (Layout B) section and refreshes the CLI shape table
  to use `./run.sh`.
- Security: JS builds DOM exclusively via `createElement` and
  `replaceChildren` — never `innerHTML`. Tests enforce.
- Smoke-tested in a browser: tree renders, projects clickable, detail
  panel populates with clone URLs + working Copy buttons, search and
  three filter controls work, empty groups collapse.
- Tests: structural HTML/JS checks via stdlib `html.parser` + regex,
  plus a CLI roundtrip writing to a tmp path and an I/O-error case.
  No headless-browser dep added.
```

- [ ] **Step 4: Validate**

Run: `scripts/validate-articles`
Expected: `✅ All 4 article(s) have valid frontmatter.`

Run: `uv run pytest -v`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add knowledge/concepts/gitlab-admin/browse-command.md knowledge/log.md
git commit -m "docs: finalize living-doc updates for HTML report

Per same-task rule, articles land alongside the code:
- browse-command.md gains an HTML report (Layout B) section
  describing the field set, filters, and self-contained-file design
- CLI shape table refreshed to use ./run.sh as the canonical entry
- log.md gets a [2026-05-20] feature entry"
```

---

## Acceptance criteria

After all 5 tasks, the following are true:

1. `uv run pytest -v` passes.
2. `scripts/validate-articles` passes (4 articles).
3. `./run.sh --cache-path tests/fixtures/snapshot.sqlite --html /tmp/preview.html` succeeds, prints `[browse] wrote /tmp/preview.html` to stderr, exits 0.
4. Opening `/tmp/preview.html` in a browser shows Layout B with the fixture data: groups `data` and `platform` (collapsible), personal projects pseudo-root, project rows clickable, detail panel populates with clone URLs + working Copy buttons, search + filters work.
5. `./run.sh --html out.html --json` is rejected by argparse (mutex group).
6. `./run.sh --html /some/directory` returns exit 4 with a clear error.
7. `./run.sh --interactive` still returns the Plan-3 stub message + exit 4.
8. `git log --oneline` shows 5 focused commits for this plan.

## What's not in this plan (Plan 3)

- Interactive mode (`-i` / `--interactive`) via `questionary` — Plan 3.
- ANSI colors in the text renderer (already deferred from Plan 1).
- Headless-browser tests for the JS behaviour (intentionally out of scope; manual smoke covers it for a single self-contained file).

---

## Self-review

Quick checks against the spec/this plan:

- **Spec §6.2 coverage:** Layout B (Task 2 + 3), detail-panel field set including clone URLs + copy buttons (Task 3, asserted in tests), client-side filtering with the exact set in §6.2 (Task 3), self-contained file (Task 2 asserts no external `<link>`).
- **Spec §5 mode-flag combinability:** `--html` mutex with `--json`/`-i` is already enforced by argparse (Plan 1 set up `add_mutually_exclusive_group`). No changes needed. Confirmed in Task 4 by not modifying the parser.
- **Spec §7 error handling:** `--html PATH` exits 4 with the underlying error message on I/O failure (Task 4, tested).
- **Security:** JS uses `createElement` + `replaceChildren` exclusively; a dedicated test enforces "no `.innerHTML`, no `.outerHTML`" in the JS source.
- **Placeholder scan:** no TBDs/TODOs in the plan body.
- **Type consistency:** `render_html.render(tree)` signature is the same across Tasks 1, 2, 3; the JS variable `ORG` is parsed from the data island on every page load.
- **Ambiguity check:** the "Hide empty groups whose children are all filtered out" behaviour in `applyFilters()` is a design choice not explicit in the spec; calling it out here so it's intentional. Reviewer can flag if it feels wrong.
