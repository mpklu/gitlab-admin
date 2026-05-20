---
title: browse command — org map of the GitLab instance
type: concept
area: gitlab-admin
updated: 2026-05-19
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

## Owner derivation

The displayed "Owner" for a project is derived, not stored:

1. First direct member with `access_level=50` (Owner) by `user_id` asc.
2. Else, owner of the namespace group (same rule, recursed).
3. Else, the namespace path.

The full member list ships with the model so the squish is a display
convenience, never a truth claim.

## CLI shape (this plan)

```text
python -m gitlab_admin.browse                        # text tree from cache
python -m gitlab_admin.browse --refresh              # re-fetch then text tree
python -m gitlab_admin.browse --json                 # JSON to stdout
python -m gitlab_admin.browse --group platform/services
python -m gitlab_admin.browse --owner kun.lu
python -m gitlab_admin.browse --stale-days 365
python -m gitlab_admin.browse --no-archived
python -m gitlab_admin.browse --cache-path ./snapshot.sqlite
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
