# Build Log

Append-only chronological log of significant changes to this project. Each entry records what changed, why, and which articles were touched. Read sequentially, this log tells the story of the project's decisions.

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
