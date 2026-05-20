# Build Log

Append-only chronological log of significant changes to this project. Each entry records what changed, why, and which articles were touched. Read sequentially, this log tells the story of the project's decisions.

## [2026-05-20] bugfix | fetch personal-namespace projects

- Symptom: projects under a user namespace (e.g.
  `https://gitlab.example.com/kal/scratch`) never made it into the
  cache. The model layer had a `👤 Personal projects` synthetic root,
  but it was always empty because `fetch.sync_all` only walked
  `/api/v4/groups` (which doesn't return user namespaces).
- Fix: after the groups loop, `fetch.sync_all` lists
  `/api/v4/projects` (which an admin token can see in full), filters
  to `namespace.kind == "user"`, and writes any project not already
  in `seen_project_ids`. Per-project member fetches still honor the
  recoverable-403 path.
- Progress line: `Added N personal-namespace project(s)` (or `No
  personal-namespace projects to add.`).
- Tests added: `test_sync_picks_up_personal_namespace_projects` (mixed
  group + personal), `test_sync_handles_only_personal_namespace_projects`
  (no groups at all).
- All seven existing sync tests grew a `_stub_projects_list_all(...,
  [])` line to satisfy the new endpoint.
- Updated: `concepts/gitlab-admin/browse-command.md` adds a
  Personal-namespace projects section.

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


## [2026-05-20] enhancement | run.sh canonical entry + standardize on uv

- Added `run.sh` at the project root as the canonical CLI invocation.
  It checks for `uv` (installs via Astral's official one-liner if
  missing), runs `uv sync --quiet`, and `exec`s
  `uv run python -m gitlab_admin.browse` with all forwarded args.
  Strict mode (`set -euo pipefail`); helper script log lines go to
  stderr so they don't pollute `--json` stdout output. Header
  comment block documents usage, examples, env vars, exit codes.
- Committed `uv.lock`. `CLAUDE.md` Conventions section already
  declares uv as the required Python package manager; run.sh and
  the lockfile make that real.
- Updated `concepts/gitlab-admin/tech-stack.md` to name uv + run.sh
  as the canonical install + entry.
- Updated `CLAUDE.md` Key Commands to use `./run.sh` and `uv` instead
  of pip / direct `python -m`.

## [2026-05-20] bugfix | per-entity 403 is recoverable

- Symptom: real-instance refresh died at group 62/63 with
  `403: 403 Forbidden` on listing members of a single group (`ops`).
  The whole sync aborted; no cache was written.
- Spec §7 already specified the right behavior ("per-entity 403 → log
  + skip"). Plan 1's final review flagged it as a deferred item.
  Implemented now.
- Fix: `fetch.sync_all` catches `gitlab.exceptions.GitlabError` with
  `response_code == 403` on per-entity fetches (group members, group
  projects, project members), records the skip, and continues. A
  summary listing the first 10 skipped entities prints before commit.
- Other HTTP errors (401 auth, 5xx server, network) still raise
  `SyncFailed` — they're not safely-recoverable.
- Test added: `test_sync_skips_group_on_403_and_continues`.
- Updated: `concepts/gitlab-admin/browse-command.md` adds a
  Per-entity 403 handling section.

## [2026-05-20] bugfix | dedupe shared projects in fetch

- Symptom: real-instance refresh crashed mid-walk with
  `sqlite3.IntegrityError: UNIQUE constraint failed: projects.id`
  on a group named `approvers/engineers` with ~200 projects.
- Root cause: GitLab projects can be *shared* with multiple groups
  (common for code-review groups). The same project then appears in
  two groups' `/projects` listings, and the second INSERT trips the
  PK constraint.
- Fix: `fetch.sync_all` tracks `seen_project_ids` (and
  `seen_group_ids` defensively) and skips already-persisted entities.
  This also avoids a redundant `/members/all` fetch for each shared
  project.
- Progress line now distinguishes `N new project(s)` from
  `K shared/already-seen` so the user can see why a count is small.
- Test added: `test_sync_skips_project_already_seen_in_another_group`.
- Updated: `concepts/gitlab-admin/browse-command.md` adds a
  Shared-project deduplication section.

## [2026-05-20] enhancement | progress output during `--refresh`

- Symptom: real-instance refresh on a hundreds-of-projects setup
  produced no terminal output for minutes, looking hung even though
  it was just slow (~1000+ API round-trips).
- Added: optional `progress: Callable[[str], None]` parameter on
  `fetch.sync_all`. CLI passes a stderr printer prefixed `[browse]`;
  library callers get a no-op default.
- Messages cover: initial "Listing groups…", per-group `[N/M]` line
  with project + member counts, final "Committing" / "Done".
- Updated `browse-command.md` with a Progress output section.

## [2026-05-19] bugfix | fetch handles unordered + orphan groups

- Symptom: first real `--refresh` against a self-hosted instance
  crashed with `sqlite3.IntegrityError: FOREIGN KEY constraint failed`
  inside `cache.write_group` because the API returned a subgroup
  before its parent.
- Fix: `fetch.sync_all` now disables `PRAGMA foreign_keys` during the
  bulk insert; after all rows are written, runs an UPDATE to nullify
  orphan `parent_id`s (parent group not in the result set);
  re-enables FK enforcement before committing.
- Side-effect: orphan subgroups (parent not visible to the token) are
  now promoted to top-level instead of vanishing or crashing.
- Tests added: `test_sync_handles_subgroup_before_parent_in_api_response`,
  `test_sync_orphan_parent_id_becomes_top_level`.
- Also: `test_refresh_without_credentials_exits_3` now passes
  `--env-file <nonexistent>` so the project's real `.env` isn't picked
  up during a credential-absent test path.
- Updated: `concepts/gitlab-admin/browse-command.md` adds an "Orphan
  parent_id handling" section.

## [2026-05-19] enhancement | dotenv loading at CLI entry

- Added `python-dotenv` as a base dep; `gitlab_admin/browse/__main__.py`
  now calls `load_dotenv(override=False)` at startup. `.env` files are
  picked up by walking up from CWD by default; `--env-file PATH`
  overrides the lookup. Shell env vars always win.
- Updated `concepts/gitlab/integration-model.md` and
  `concepts/gitlab-admin/tech-stack.md` to document the loader and
  precedence rule.
- Tests added: `test_env_file_populates_credentials_when_shell_lacks_them`,
  `test_env_file_does_not_override_shell_env`.

## [2026-05-19] feature | gitlab-admin browse — foundation

- Implemented the `browse` foundation per Plan 1 of the design at
  `docs/superpowers/specs/2026-05-19-gitlab-org-browser-design.md`.
- Landed: `gitlab_admin/client.py`, `gitlab_admin/browse/` (cache, model,
  fetch, text and JSON renderers, CLI entry).
- Scope: expanded `purpose-and-scope.md` to a fourth task family
  (discovery / org navigation).
- Added: `concepts/gitlab-admin/browse-command.md` (load-bearing).
- HTML and interactive renderers tracked for Plans 2 and 3.
- Test surface: `pytest -v` runs across cache, model, fetch, both
  renderers, and CLI; fetch tests stub HTTP via `responses`.

## [2026-05-19] bootstrap | adopt living-docs methodology + seed first articles

- Installed living-docs methodology via `install/install.sh` from mpklu/living-doc (greenfield mode, recommended setup: core + cli + pre-commit hook + GitHub Action + bootstrap prompt).
- Filled `CLAUDE.md` placeholders with gitlab-admin specifics: project name/description, project structure, package manager (pip), test runner (pytest), article-mapping table tied to the three seeded articles.
- Seeded three thin "north star" concept articles before any code lands:
  - `concepts/gitlab-admin/purpose-and-scope.md` — task families in scope (user/group lifecycle, project housekeeping, access audits) and what is deliberately out (bulk migrations, multi-instance, external distribution).
  - `concepts/gitlab-admin/tech-stack.md` — Python 3.11+, `python-gitlab`, `pytest`, `gitlab_admin/` package layout, `python -m gitlab_admin.<command>` convention, mandatory `--dry-run` on writes.
  - `concepts/gitlab/integration-model.md` — single self-hosted GitLab instance, PAT auth via `GITLAB_URL`/`GITLAB_TOKEN`, single client factory in `gitlab_admin/client.py`, safety conventions (default dry-run on writes, no retries on non-idempotent writes).
- Anchor questions asked: primary task families; tech stack; GitLab target + auth model; audience/distribution.
- Decisions pending: exact first command to implement; whether to add `pyproject.toml` in the next PR or with the first command; rate-limit/retry policy (deferred until first 429 surfaces in practice).
