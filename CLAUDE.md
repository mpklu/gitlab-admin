# gitlab-admin

A Python toolkit our team uses to administer a self-hosted GitLab instance.
It covers user and group lifecycle, project/repo housekeeping (settings,
protections, CI config), and access/permissions audits. Auth is via a
personal access token supplied through environment variables. The repo is
shared with teammates and run locally — it is not packaged or published.

## Methodology

This project follows the living-documentation methodology described at
https://github.com/mpklu/living-doc.
The first principle ("capture first, refine second") and the same-task
rule from that repository's `LIVING_DOCS_OVERVIEW.md` apply here.

## Source of Truth

The knowledge base in `knowledge/` is the source of truth for this project.
It must always mirror the code. Entry point: `knowledge/index.md`.
Compile log: `knowledge/log.md`.

### The rule

Every code change that alters behaviour, config, models, or architecture
must update the relevant `knowledge/concepts/*.md` article(s) in the same
task and append an entry to `knowledge/log.md`. Don't batch knowledge
updates for later.

**Failure mode this prevents.** Skipping the article update means it
goes stale before the next read. The next session will trust the stale
article and produce wrong work. The drift compounds. This is not
stylistic — it's load-bearing.

**Capture first, refine second:** when in doubt about whether a change is
documentation-relevant, write the update anyway. When in doubt about where
a new article belongs, pick the closest fit and write it. The user reviews
and refines. Missing context is unrecoverable; an imperfect article costs
minutes.

### Before any commit

The same-task rule is a *principle*; this checklist is the *procedure*.
Run through it before every commit:

1. List the files in this commit's diff.
2. For each: any article's `affects:` frontmatter glob match it? (Until
   the `affects:`-based mapping is in place, fall back to the
   article-mapping table below.) Open those articles.
3. Did this change alter behaviour, configuration, models, structure,
   or a documented decision?
4. If yes: stage the article update + a `log.md` entry **in this same
   commit**.
5. If no article exists for the touched code path: write a thin one
   now (~200 words). Don't open a follow-up issue; don't defer.
6. If the change is genuinely doc-irrelevant (typo, formatting,
   refactor with identical observable behaviour): the commit body
   must say so explicitly: `no knowledge impact: <reason>`.

### Red flags

These thoughts mean STOP and audit:

- "I'll update docs after this commit lands."
- "The article is roughly correct."
- "This is too small to document."
- "Let me ship and circle back."
- "The reviewer can flag it if it matters."

Each phrase rationalizes a skip that compounds. The cost of pausing
to update the article is minutes; the cost of stale documentation is
unbounded.

### What lives where

| Location | Contains | Authority |
| --- | --- | --- |
| `knowledge/concepts/` | Standalone reference articles, grouped by area | How each thing works and why |
| `knowledge/connections/` | Cross-concept articles | How the pieces fit together |
| `gitlab_admin/` | Python package: client, commands, shared modules | What the system does |
| `tests/` | pytest tests with sanitized fixtures | Testable behaviour |
| `scripts/` | Living-doc validators (`drift-check`, `validate-articles`) — **not** app code | Doc tooling |
| `.env` | Real credentials (gitignored): `GITLAB_URL`, `GITLAB_TOKEN` | Local config |

### Article mapping — update these when the matching code changes

This table is populated from day one of greenfield. As you add new modules
or external integrations, add new rows here.

| When you change... | Update this article |
| --- | --- |
| Project scope (what gitlab-admin does or refuses to do) | `concepts/gitlab-admin/purpose-and-scope.md` |
| Folder layout, package boundaries, or runtime conventions | `concepts/gitlab-admin/tech-stack.md` |
| GitLab API client wrapper, auth handling, or rate-limit behaviour | `concepts/gitlab/integration-model.md` |
| Env vars or how credentials are sourced | `concepts/gitlab/integration-model.md` |
| A new command in `gitlab_admin/commands/` | Add `concepts/gitlab-admin/{command-name}.md` and a row to this table |
| Anything in `gitlab_admin/browse/**` (cache schema, owner derivation, exit codes, renderers) | `concepts/gitlab-admin/browse-command.md` |
| CLI surface — any flag added / removed / renamed in `gitlab_admin/browse/__main__.py`, or change in flag semantics | `concepts/gitlab-admin/browse-command.md` **and** the `CLI OPTIONS` + `EXAMPLES` sections of `run.sh`'s header docstring |
| Test conventions, fakes, fixtures | _(add `concepts/gitlab-admin/testing-strategy.md` once tests land)_ |

### When the agent encounters code without a matching article

Write the first thin article in the same task. Place as:

- `concepts/{{project}}/{topic-kebab-case}.md` for an internal concept.
- `concepts/{external-system}/{topic}.md` for an external integration. Create
  a new area subdirectory if the system isn't already covered.
- `connections/{topic}.md` for a cross-cutting article describing how
  multiple existing concepts interact.

Capture the **why** — context, constraints, alternatives ruled out — not
just the post-change state of the code. Add a row to the article-mapping
table above. Note the addition in `log.md`.

### How to catch drift

After finishing implementation, ask: "does anything in `knowledge/` now
contradict what I just built?" Check signatures, field lists, config
tables, folder structure, and env var names. **Real data beats the article**
— if a field the article says is required turns out to be absent in real
payloads, update the article to match reality, not the other way around.
Add a compile entry to `knowledge/log.md` listing the articles touched.

## Conventions

### Dependency Management

- For python, must use uv
- For Typescript/Javascript, must use pnpm


## Key Commands

```bash
./run.sh                            # canonical CLI entry — bootstraps uv, syncs, runs browse
./run.sh --refresh                  # re-fetch from GitLab then render
./run.sh --json                     # JSON to stdout
uv sync                             # install/update deps explicitly
uv run pytest                       # run tests
scripts/validate-articles           # validate knowledge/ frontmatter
scripts/drift-check                 # check articles vs touched code
```

See `run.sh`'s header comment block for the full entry-point contract.

### Keeping `run.sh` in sync

`run.sh`'s header docstring is a duplicate surface for the CLI options
documented in `concepts/gitlab-admin/browse-command.md`. When you change
the CLI in `gitlab_admin/browse/__main__.py`, update **both** in the same
commit:

1. The article (the canonical reference, used by drift-check).
2. The `CLI OPTIONS` and (where useful) `EXAMPLES` sections of `run.sh`.

Don't let `run.sh` drift. A teammate's first encounter with the tool is
typically `less run.sh` — if the docstring lies, the tool gets a bad
first impression. The article-mapping table above lists this as a
same-task-rule entry.
