---
title: Purpose and scope of gitlab-admin
type: concept
area: gitlab-admin
updated: 2026-05-19
status: thin
load_bearing: true
---

## What this is

`gitlab-admin` is a Python toolkit our team uses to administer a single
self-hosted GitLab instance. It is a *shared internal repo*, not a
distributed product: teammates clone it and run commands locally against
the same instance using their own admin token.

The toolkit targets four task families:

1. **User & group lifecycle** — onboarding, offboarding, role changes,
   periodic membership audits.
2. **Project/repo housekeeping** — applying consistent settings across
   projects (visibility, protected branches, MR rules, CI/CD config).
3. **Access & permissions audit** — reporting who has what access,
   flagging deviation from policy, surfacing stale tokens and deploy keys.
4. **Discovery / org navigation** — browsing the full org map (groups,
   projects, owners, clone URLs, last activity) when GitLab's own web
   UI can't keep up. See `browse-command.md`.

## Why this shape

These four families are the recurring manual toil today. A Python repo
optimised for ad-hoc commands beats a packaged CLI because (a) the
audience is small and trusted, (b) iteration speed matters more than
polish, and (c) admin operations frequently need a quick custom variant.

## Explicitly out of scope

- **Bulk project migrations** (group moves, import/export). Risky,
  rare, and better done with `glab` or the GitLab UI.
- **Distribution outside the team.** No PyPI, no Homebrew, no binary.
- **Multi-instance support.** One GitLab instance per checkout, configured
  via `GITLAB_URL`. If we ever need a second, that's a real redesign.

## What would invalidate this article

A decision to add bulk migrations to scope, to distribute the toolkit
outside the team, or to support multiple GitLab instances from a single
invocation. Any of these changes the design centre of gravity.

## First commitments

- Top-level package is `gitlab_admin/`.
- Commands live under `gitlab_admin/commands/`, one module per command.
- Each command is runnable as `python -m gitlab_admin.<command>`.
