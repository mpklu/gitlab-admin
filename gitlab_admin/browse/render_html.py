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
<script>{js}</script>
</body>
</html>
"""


def render(tree: Tree) -> str:
    """Return a complete self-contained HTML string for the org browser."""
    data_json = render_json.render(tree).rstrip()
    return _HTML_HEAD.format(css=_CSS) + _HTML_BODY_TEMPLATE.format(
        data_json=data_json, js=_JS
    )
