# GitLab Org Browser — Design Spec

**Status:** approved (brainstorm) — pending implementation plan
**Date:** 2026-05-19
**Repo:** `mpklu/gitlab-admin`
**Lands as:** new `gitlab_admin/browse/` package + a fourth task family in `purpose-and-scope.md`

---

## 1. Overview

Add a `browse` command to `gitlab-admin` that produces an org map of an
entire self-hosted GitLab instance — every group, subgroup, and project
visible to the admin token, with owners, last-updated, clone URLs, and
visibility.

Four output renderers share one fetch/cache/model pipeline:

| Renderer | Invocation | When you reach for it |
| --- | --- | --- |
| Text tree (default) | `python -m gitlab_admin.browse` | Quick lookup; pipe into `grep`, `less`, `fzf` |
| HTML report | `… --html out.html` | Browse the full map visually; share with teammates |
| JSON | `… --json` | Feed downstream tooling |
| Interactive | `… -i` / `--interactive` | Drill into the hierarchy by arrow keys with type-to-filter |

Data is fetched once via the GitLab API and stored in a local SQLite
snapshot. Browsing reads the cache instantly; `--refresh` is the only
operation that touches the network.

## 2. Scope

### In scope
- Whole-instance admin view: every group/subgroup/project the admin PAT can see.
- Owners + last-updated + clone URLs (HTTPS and SSH) + visibility + archived flag, surfaced per project.
- Discovery / org navigation as a primary use case.

### Out of scope (deliberate)
- Bulk migrations or archive operations driven from the browser.
- Multi-instance support in a single invocation.
- Incremental / delta refresh.
- Snapshot history (we keep one snapshot, overwritten on refresh).
- Performance work tuned for 10K+ projects (revisit when needed).

### Living-doc scope-expansion note
The current `concepts/gitlab-admin/purpose-and-scope.md` names three task
families (lifecycle, housekeeping, audit). This design adds a fourth:
**discovery / org navigation**. That article gets a new paragraph and a
new row in the article-mapping table in the same commit that lands the
first browse code.

## 3. Architecture

```text
gitlab_admin/
  client.py                 # python-gitlab factory from GITLAB_URL / GITLAB_TOKEN (existing plan)
  browse/
    __init__.py
    __main__.py             # argparse CLI; routes to renderers
    fetch.py                # ONLY module that talks to GitLab
    cache.py                # SQLite read/write
    model.py                # pure: cache rows -> in-memory tree of Group/Project
    render_text.py          # tree -> stdout (ANSI if isatty)
    render_html.py          # tree -> single self-contained HTML file (Layout B)
    render_json.py          # tree -> JSON on stdout
    render_interactive.py   # `questionary`-driven hierarchical menus
```

### One-way data flow

```text
GitLab API
   │  (network — only here)
   ▼
client.py  →  fetch.py
                │  (writes)
                ▼
            cache.py  →  ~/.cache/gitlab-admin/browse.sqlite
                │  (reads)
                ▼
            model.py  →  in-memory Group/Project tree (pure, no I/O)
                │
   ┌────────────┼────────────┬──────────────┐
   ▼            ▼            ▼              ▼
render_text  render_html  render_json  render_interactive
```

### Layering rules (load-bearing)
- Network access is confined to `fetch.py`. The other modules are
  importable in offline tests.
- `model.py` is pure: cache rows in, tree out. No I/O, no clock, no env.
- Renderers consume the model and produce output. They do not read the
  cache directly. Adding a new renderer (CSV, graphviz) costs one file.
- Only `render_interactive.py` imports `questionary`. The other
  renderers remain stdlib-only at runtime. (We still install `questionary`
  as a base dep — the audience is small and an extras gate is overkill.)

### Dependencies
- `python-gitlab` (existing plan in `tech-stack.md`).
- `questionary` — new, base dep, used only by interactive renderer.
- `pytest` (existing).
- `responses` — new dev-only, used to stub the GitLab API in `fetch.py` tests.
- SQLite via stdlib `sqlite3`. No ORM.

## 4. Cache schema

Stored at `~/.cache/gitlab-admin/browse.sqlite` (XDG-aware; overridable
with `--cache-path`). Atomic-replace on refresh: write to a temp file in
the same directory, then `os.replace()` over the live file.

```sql
-- one row per --refresh; we keep only the latest
CREATE TABLE snapshot (
  id           INTEGER PRIMARY KEY,
  started_at   TEXT NOT NULL,         -- ISO 8601
  completed_at TEXT NOT NULL,
  gitlab_url   TEXT NOT NULL,
  tool_version TEXT NOT NULL
);

CREATE TABLE groups (
  id          INTEGER PRIMARY KEY,     -- gitlab group id
  parent_id   INTEGER REFERENCES groups(id),
  full_path   TEXT NOT NULL UNIQUE,    -- "platform/services"
  name        TEXT NOT NULL,
  visibility  TEXT NOT NULL,           -- private|internal|public
  description TEXT,
  web_url     TEXT NOT NULL,
  created_at  TEXT NOT NULL
);
CREATE INDEX idx_groups_parent ON groups(parent_id);

CREATE TABLE projects (
  id                  INTEGER PRIMARY KEY,
  namespace_group_id  INTEGER REFERENCES groups(id),  -- NULL for personal-namespace
  namespace_user_id   INTEGER,                        -- set for personal-namespace
  path_with_namespace TEXT NOT NULL UNIQUE,
  name                TEXT NOT NULL,
  default_branch      TEXT,
  visibility          TEXT NOT NULL,
  archived            INTEGER NOT NULL,               -- 0/1
  last_activity_at    TEXT NOT NULL,
  http_url_to_repo    TEXT NOT NULL,
  ssh_url_to_repo     TEXT NOT NULL,
  web_url             TEXT NOT NULL,
  description         TEXT,
  topics              TEXT,                           -- JSON array
  star_count          INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_projects_namespace ON projects(namespace_group_id);
CREATE INDEX idx_projects_activity  ON projects(last_activity_at DESC);
CREATE INDEX idx_projects_archived  ON projects(archived);

-- members of both groups and projects; entity_type discriminates
CREATE TABLE members (
  entity_type  TEXT NOT NULL,           -- 'group' | 'project'
  entity_id    INTEGER NOT NULL,
  user_id      INTEGER NOT NULL,
  username     TEXT NOT NULL,
  name         TEXT NOT NULL,
  access_level INTEGER NOT NULL,        -- 10/20/30/40/50 per GitLab
  expires_at   TEXT,                    -- nullable ISO 8601
  PRIMARY KEY (entity_type, entity_id, user_id)
);
CREATE INDEX idx_members_entity ON members(entity_type, entity_id, access_level DESC);
```

### Owner derivation (renderer concern, not a column)
For each project, the displayed "Owner" is computed by `model.py`:

1. If the project has a direct member with `access_level = 50` (Owner),
   pick the first by `user_id` ascending.
2. Else, take the namespace group's Owner (same rule, applied to the
   group's members).
3. Else, fall back to the namespace `full_path`.

The detail panel always shows the full member list, so the squish is a
display convenience, never a truth claim.

### Inherited members
`fetch.py` calls GitLab's `/members/all` endpoint (not `/members`) for
both groups and projects, so inherited membership is captured. When the
same user appears multiple times (direct + inherited), `fetch.py` keeps
only the row with the highest `access_level`.

## 5. CLI surface

```text
python -m gitlab_admin.browse                                # text tree from cache
python -m gitlab_admin.browse --refresh                      # re-fetch, then text tree
python -m gitlab_admin.browse --html out.html                # write HTML report
python -m gitlab_admin.browse --json                         # JSON to stdout
python -m gitlab_admin.browse --refresh --html out.html      # combine
python -m gitlab_admin.browse -i                             # interactive mode

# text-tree slicing (HTML filtering is client-side; these flags don't apply to it)
python -m gitlab_admin.browse --group platform/services
python -m gitlab_admin.browse --owner kun.lu
python -m gitlab_admin.browse --stale-days 365
python -m gitlab_admin.browse --no-archived

# overrides
python -m gitlab_admin.browse --cache-path ./snapshot.sqlite
python -m gitlab_admin.browse --gitlab-url ... --refresh     # one-off env override
```

### Behaviour rules
1. **`--refresh` is the only network operation.** A bare `browse`
   never touches GitLab.
2. **No silent auto-fetch.** If the cache is missing, exit 1 with
   *"No cache. Run with --refresh first."*
3. **Mode flag combinability.** `--html`, `--json`, and `-i` are
   mutually exclusive (you can't pipe an interactive session, and a
   single invocation has one output channel). `--refresh` is *not* a
   mode flag — it composes with all three: `--refresh -i`, `--refresh
   --html out.html`, `--refresh --json` are all valid (re-fetch, then
   render in the chosen mode). Combining two mode flags is an argparse
   error.
4. **No `--dry-run`.** Browse is read-only; the `--dry-run` convention
   in `concepts/gitlab/integration-model.md` is for write commands only.
5. **HTML report is one self-contained file.** Inline CSS + JS + a JSON
   data island. No external assets, no CDN.

### Exit codes
| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Cache missing or schema-mismatch (and not `--refresh`) |
| 2 | Network error during refresh |
| 3 | Auth error: `GITLAB_URL` / `GITLAB_TOKEN` missing or rejected |
| 4 | Unexpected error (I/O, argparse violation) |

## 6. Renderers

### 6.1 Text tree (default)
Indented tree to stdout. ANSI colors when `sys.stdout.isatty()`, plain
otherwise. Header line at the top, footer with snapshot metadata.

```text
📁 platform                                                       — Alice (owner)
├── 📁 services                                                   — Alice
│   ├── ▢ auth-svc                            Bob · 3 days · prv
│   ├── ▢ billing-svc                         Carol · 2 weeks · prv
│   └── ▢ legacy-auth         [archived]      Alice · 2 years · prv
├── 📁 web                                                        — Dan (4 projects)
└── 📁 data
    └── ▢ etl-jobs                            Eve · 1 month · prv

👤 Personal projects
└── ▢ kun.lu/scratch                          Kun · 6 hours · prv

Snapshot: 2026-05-19 18:45 UTC · gitlab.example.com · 1 247 projects across 142 groups
```

### 6.2 HTML report — Layout B
Single self-contained `.html` file. Two panes:
- **Left**: lean collapsible tree of group/project names. Search box at
  top; toggles for *show archived* (default off — hidden), *only stale
  (>1y)* (default off), and a tri-state visibility chip group
  (`private` / `internal` / `public`, all on by default; clicking a
  chip toggles that visibility class).
- **Right**: detail panel populated when a project row is clicked.

Detail panel field set:
- Project name + breadcrumb path
- Owner (derived per §4) and visibility pill
- Last-updated and default branch
- **HTTPS clone URL** with a "📋 Copy" button (writes to clipboard via `navigator.clipboard.writeText`)
- **SSH clone URL** with a "📋 Copy" button
- Maintainers list (de-duped by user_id, highest access_level wins)
- "↗ Open in GitLab" link to `web_url`

All filtering is client-side over the embedded JSON data island.

### 6.3 JSON
Tree-shaped JSON dumped to stdout:

```json
{
  "snapshot": { "completed_at": "2026-05-19T18:45:00Z", "gitlab_url": "https://...", "tool_version": "0.1.0" },
  "groups": [
    {
      "id": 12, "full_path": "platform", "name": "platform",
      "children_groups": [ /* recursive */ ],
      "projects": [
        {
          "id": 99, "path_with_namespace": "platform/services/billing-svc",
          "name": "billing-svc", "owner": "Carol", "last_activity_at": "...",
          "http_url_to_repo": "...", "ssh_url_to_repo": "...",
          "archived": false, "visibility": "private",
          "members": [ { "username": "...", "access_level": 50, "expires_at": null } ]
        }
      ]
    }
  ],
  "personal_namespace_projects": [ /* same project shape */ ]
}
```

### 6.4 Interactive (`-i`)
Driven by `questionary.select` at each tier:

1. Top level: list of top-level groups + a "👤 Personal projects" pseudo-entry.
2. Group level: list of subgroups + direct projects + `[← Back]`.
3. Project leaf: prints the detail-panel field set (clone URLs included), then offers a small action menu:
   - `[c] Copy HTTPS URL to clipboard`
   - `[s] Copy SSH URL to clipboard`
   - `[o] Open in GitLab` (shells out to `open` on macOS / `xdg-open` on Linux)
   - `[← Back]`

Type-to-filter on every list (provided natively by `questionary`).
Ctrl-C anywhere exits with code 0.

## 7. Error handling

| Path | Failure | Behaviour |
| --- | --- | --- |
| `--refresh` auth | `GITLAB_URL` / `GITLAB_TOKEN` missing or 401/403 | Exit 3, prints which var is missing (no traceback) |
| `--refresh` network | Timeout, DNS, connection refused | Exit 2. Cache unchanged (refresh is atomic via temp + replace) |
| `--refresh` rate limit | 429 with `Retry-After` | Respect header, up to 3 retries; then exit 2 |
| `--refresh` per-entity 403 | Specific group/project unreadable | Log + skip; footer notes `N entities skipped due to access errors` |
| `browse` no cache | Missing cache, not `--refresh` | Exit 1, *"No cache. Run with --refresh first."* |
| `browse` stale schema | Cache from older tool version | Exit 1, *"Cache schema older than tool. Re-run with --refresh."* |
| `--html PATH` | PATH is a directory; I/O error | Exit 4 with the underlying message |
| `-i` no TTY | Piped / non-interactive | Exit 1, *"Interactive mode requires a TTY."* |
| `-i` Ctrl-C | Anywhere in the loop | Exit 0, clean — no traceback |

## 8. Edge cases (decisions, not TODOs)

- **De-dupe members.** Same user appearing direct + inherited → keep
  highest `access_level` only. Enforced at fetch time.
- **Expired members.** Shown in the detail panel tagged
  `(expired YYYY-MM-DD)`. Not counted in owner derivation.
- **Empty groups.** Render `(empty)` suffix; still drillable.
- **Defensive cycle break.** If a `parent_id` chain exceeds depth 20,
  log and stop walking. GitLab disallows cycles; this is a smell-detector
  for a corrupt cache.
- **Personal-namespace projects.** Surfaced under a synthetic
  `👤 Personal projects` root in all renderers.
- **Long lists.** `questionary` scrolls; the HTML report renders all
  rows (volume of "thousands" is fine without virtualization).

## 9. Testing strategy

`pytest`. One rule: **only `fetch.py` is allowed to touch the network**,
and even there it's stubbed via `responses`.

| Module | Style | What's verified |
| --- | --- | --- |
| `cache.py` | Round-trip | Write a synthetic snapshot, read it back, assert equality |
| `model.py` | Pure unit | Seed fixture DB → build tree → assert hierarchy + owner-derivation rules + personal-namespace placement |
| `render_text.py` | Golden file | Fixture DB → tree → diff against checked-in expected output |
| `render_html.py` | Structural | Render to tmp, parse with stdlib `html.parser`, assert data island contains expected projects + copy buttons present + clone URLs in DOM |
| `render_json.py` | Schema | `json.loads` + shape assertions |
| `render_interactive.py` | Stubbed prompt | Drive `questionary` with a scripted input sequence; assert navigation traces correct path |
| `fetch.py` | HTTP stubs | `responses` to stub `/api/v4/groups`, `/projects`, `/members/all`; verify pagination, atomic-replace, dedup of inherited members |

A checked-in fixture `tests/fixtures/snapshot.sqlite` (~10 groups, ~30
projects) covers archived, personal namespace, multi-owner, no-owner,
deep nesting. Generated by `tests/build_fixture.py` so it's reproducible.

Manual smoke test (`tests/smoke_real.py`) runs against the real GitLab
instance once per release. Not in CI.

## 10. What we're *not* paying for today

- Performance work at 10K+ projects.
- Concurrent `--refresh` race protection (single-user audience).
- HTML fuzz/random-data testing.
- Incremental refresh (mentioned in `tech-stack.md` as future work).
- Snapshot history (kept to one row per the schema; add a `snapshot_id`
  FK later if we want diffing).

## 11. Living-doc impact

The first code-bearing PR for `browse` must, in the same commit:

1. Update `concepts/gitlab-admin/purpose-and-scope.md` — add **discovery
   / org navigation** as a fourth task family. The "out of scope" list
   stays as-is (bulk migrations, multi-instance, external distribution).
2. Update `concepts/gitlab-admin/tech-stack.md` — list `questionary` as
   a base dep; add `responses` as a dev dep; note SQLite-via-stdlib for
   the cache.
3. Add `concepts/gitlab-admin/browse-command.md` — load-bearing.
   Documents the cache schema (table layout + indexes), exit codes,
   output formats, owner-derivation rule, and the detail-panel field set.
4. Update `CLAUDE.md` article-mapping table — add a row tying
   `gitlab_admin/browse/**` to `browse-command.md`.
5. Append a `knowledge/log.md` entry describing the scope expansion and
   the new article.

## 12. Open questions (none blocking)

- *When* the first PR lands a working slice end-to-end vs. lands
  `--refresh` + text tree first and HTML/interactive in PR 2 — a
  sequencing call for `writing-plans` to make.
- Whether to add a `--top-only` flag for the text tree (collapse all
  subgroups, show only top-level groups). Not in v1.
- Whether the HTML report should include a "what changed since last
  snapshot" mode. Out of scope per §10.
