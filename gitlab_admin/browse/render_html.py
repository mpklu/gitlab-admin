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
