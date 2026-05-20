---
title: browse command — org map of the GitLab instance
type: concept
area: gitlab-admin
updated: 2026-05-20
status: thin
load_bearing: true
---

## What this is

`browse` produces a navigable map of every group, subgroup, and project
visible to the admin token on the self-hosted GitLab instance. Three
output renderers — text tree, JSON, HTML report — and an interactive
mode share one fetch/cache/model pipeline. This plan implements text +
JSON; HTML and interactive land in follow-up plans.

## How it's wired

```text
GitLab API
    ↓ (network — only here)
fetch.py
    ↓ (writes via temp + os.replace)
cache.py  →  ~/.cache/gitlab-admin/browse.sqlite
    ↓ (reads)
model.py  →  in-memory Group/Project tree
    ↓
render_text.py  /  render_json.py
```

## Cache

Stored at `~/.cache/gitlab-admin/browse.sqlite` (overridable with
`--cache-path`). Four tables: `snapshot`, `groups`, `projects`, `members`.
Refresh is atomic: write to a temp file in the same directory, then
`os.replace()` over the live file. See the spec at
`docs/superpowers/specs/2026-05-19-gitlab-org-browser-design.md` §4 for
the full schema.

### Progress output

`fetch.sync_all` accepts a `progress: Callable[[str], None]` callback,
called as the sync advances (group N of M, per-group project/member
counts, final commit notice). The CLI passes a stderr printer prefixed
`[browse]`. Library callers default to a no-op so tests stay quiet.
This exists because a real-instance refresh can take minutes against a
hundreds-of-projects setup; without progress, the command looks hung.

### Per-entity 403 handling

The GitLab API can return 403 on a specific group or project even when
the admin token works generally (some self-hosted instances have
quirky ACLs, archived-but-visible groups, or recently-permission-changed
resources). `fetch.sync_all` treats per-entity 403s as recoverable:

- The offending entity's members/projects fetch is skipped.
- The rest of the sync continues.
- A progress line announces the skip immediately
  (`(skipped: 403 on members)`).
- Before commit, a summary lists all skipped entities (first 10 names
  plus an "and N more" count if the list is longer).

Other HTTP errors (auth 401, server 5xx, network timeouts) still abort
the whole sync via `SyncFailed` — they indicate problems where partial
data isn't safe.

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
- **Project Owners** — direct members with `access_level == 50`,
  expired excluded. Empty list shows `(none direct on this project)`
  so the user can tell access is inherited from the namespace group.
- **Project Maintainers** — direct members with `access_level == 40`,
  expired excluded. Shown as a separate list from Owners so the two
  roles are visually distinct.
- "↗ Open in GitLab" link to the project's `web_url`

Client-side filters in the top toolbar:

- **Search** matches against project path-with-namespace (case-insensitive).
- **Archived** checkbox — hidden by default; tick to include archived projects.
- **Stale >1y** checkbox — show only projects with no activity in the last year.
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

### Personal-namespace projects

GitLab projects can live under a *user* namespace (e.g.
`/kal/scratch`) rather than a group. The `/api/v4/groups` endpoint
only returns groups, so a groups-only walk misses every project under
a user namespace. After the groups loop, `fetch.sync_all` issues a
single `/api/v4/projects` call (admin token sees everything), filters
to `namespace.kind == 'user'`, and writes any project it hasn't
already persisted via the groups path. The `seen_project_ids`
skip-set deduplicates against group-owned projects already in the
cache. Per-project member fetches still get the recoverable-403
treatment from the section above.

The progress line reports `Added N personal-namespace project(s)` or
`No personal-namespace projects to add.` depending on what surfaces.

These projects land in the cache with `namespace_user_id` populated
and `namespace_group_id` NULL — the model layer routes them to the
synthetic `👤 Personal projects` root, separate from the group tree.

### Shared-project deduplication

GitLab projects can be *shared* with multiple groups (common pattern:
a code-review group like `approvers/engineers` that has ~200 projects
shared with it). When the same project appears in two groups' project
listings, `fetch.sync_all` would otherwise crash on
`UNIQUE constraint failed: projects.id`. The sync tracks seen project
IDs and skips duplicates — both the INSERT and the redundant
`/members/all` fetch. The same skip-set is also applied to groups
defensively. The progress line reports `N new project(s), K shared/already-seen`
so it's obvious when this is happening.

### Orphan parent_id handling

The GitLab API doesn't guarantee that parent groups are returned before
their subgroups, and admins can occasionally see a subgroup whose parent
isn't in the result set at all. `fetch.sync_all` handles both by:

1. Disabling `PRAGMA foreign_keys` during the bulk insert.
2. After all rows are written, running
   `UPDATE groups SET parent_id = NULL WHERE parent_id NOT IN (SELECT id FROM groups)` —
   orphans get promoted to top-level rather than disappearing.
3. Committing, then re-enabling FK enforcement on the connection.

This trades referential strictness during the write window for
robustness against API ordering and visibility quirks. The model layer
already treats `parent_id = NULL` as top-level, so promoted orphans
render naturally.

## Owner derivation

The displayed "Owner" for a project is derived, not stored:

1. First direct member with `access_level=50` (Owner) by `user_id` asc.
2. Else, owner of the namespace group (same rule, recursed).
3. Else, the namespace path.

The full member list ships with the model so the squish is a display
convenience, never a truth claim.

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

Exit codes: 0 success, 1 missing/stale cache, 2 network error during
refresh, 3 auth error, 4 unexpected.

## What would invalidate this article

- A schema change in `cache.py` not reflected in the spec §4 schema.
- A change to owner-derivation rules.
- A new exit code or a change to existing exit-code semantics.
- A new mode flag combination rule.

## First commitments

- All network I/O is in `fetch.py`.
- `model.py` is pure: cache rows in, tree out, no I/O.
- Refresh is atomic-replace; partial state is unreachable.
- `~/.cache/gitlab-admin/browse.sqlite` is the canonical cache path.
