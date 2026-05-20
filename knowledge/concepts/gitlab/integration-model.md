---
title: GitLab integration model
type: concept
area: gitlab
updated: 2026-05-19
status: thin
load_bearing: true
---

## What this is

How `gitlab-admin` talks to GitLab: which instance, how it authenticates,
which library wraps the API, and the safety conventions every command
inherits.

- **Target:** a single self-hosted GitLab instance. URL provided at
  runtime via the `GITLAB_URL` environment variable.
- **Auth:** a personal access token (PAT) with admin scope, supplied via
  the `GITLAB_TOKEN` environment variable. No OAuth, no SSO flow, no
  application-specific credential store. Each operator uses their own
  token so audit logs attribute changes correctly.
- **`.env` loading:** CLI entry points call `dotenv.load_dotenv()` once
  at startup. By default it walks up from the current working directory
  looking for a `.env` file; `--env-file PATH` overrides that lookup.
  Real shell env vars always win over `.env` file values
  (`override=False`). `.env` is gitignored.
- **Client:** `python-gitlab`, constructed by `gitlab_admin.client.get_client()`.
  All commands go through this factory; no command builds its own client.

## Why this shape, not the alternatives

Env-var PAT auth keeps every command stateless and easy to wrap in
ad-hoc shell pipelines. A token file or keychain integration would add
state we do not need at our team size. Routing every call through a
single client factory gives us one place to add retries, rate-limit
backoff, and request logging when the need surfaces — none of which
are implemented yet, but are the obvious next additions.

## Safety conventions

- **Writes default to dry-run.** Any command that mutates state must
  accept `--dry-run` and default to it when destructive. The non-dry
  invocation requires an explicit flag.
- **Audit commands are read-only.** Audit/report commands never write.
- **No retries on writes without idempotency.** Until we audit each
  endpoint's idempotency, the client wrapper retries reads only.

## What would invalidate this article

Adding OAuth/SSO auth, supporting multiple GitLab instances in one
invocation, switching off `python-gitlab`, or removing the
default-dry-run convention. Each is a real change in posture.

## First commitments

- `GITLAB_URL` and `GITLAB_TOKEN` are the only required env vars.
- `gitlab_admin/client.py` raises a clear error if either is missing.
- Missing-token errors print the env-var name, not a stack trace.
- `dotenv.load_dotenv(override=False)` runs at CLI entry; shell env
  vars never get clobbered by `.env` values.
