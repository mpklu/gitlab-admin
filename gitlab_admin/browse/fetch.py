"""Network-touching layer: walks the GitLab API and populates a fresh
SQLite cache via temp-file + atomic os.replace().

This is the ONLY module in browse/ that talks to GitLab. Everything
downstream reads the cache.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import gitlab

from . import cache


class SyncFailed(RuntimeError):
    """A sync failed before the atomic replace; existing cache is untouched."""


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _group_row(g) -> dict:
    return {
        "id": g.id,
        "parent_id": getattr(g, "parent_id", None),
        "full_path": g.full_path,
        "name": g.name,
        "visibility": g.visibility,
        "description": getattr(g, "description", None),
        "web_url": g.web_url,
        "created_at": g.created_at,
    }


def _project_row(p) -> dict:
    namespace = getattr(p, "namespace", {}) or {}
    is_group_ns = namespace.get("kind") == "group"
    return {
        "id": p.id,
        "namespace_group_id": namespace.get("id") if is_group_ns else None,
        "namespace_user_id": namespace.get("id") if not is_group_ns else None,
        "path_with_namespace": p.path_with_namespace,
        "name": p.name,
        "default_branch": getattr(p, "default_branch", None),
        "visibility": p.visibility,
        "archived": 1 if p.archived else 0,
        "last_activity_at": p.last_activity_at,
        "http_url_to_repo": p.http_url_to_repo,
        "ssh_url_to_repo": p.ssh_url_to_repo,
        "web_url": p.web_url,
        "description": getattr(p, "description", None),
        "topics": json.dumps(getattr(p, "topics", []) or []),
        "star_count": getattr(p, "star_count", 0),
    }


def _member_row(entity_type: str, entity_id: int, m) -> dict:
    return {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "user_id": m.id,
        "username": m.username,
        "name": getattr(m, "name", m.username),
        "access_level": m.access_level,
        "expires_at": getattr(m, "expires_at", None),
    }


def _write_members_deduped(conn, entity_type: str, entity_id: int, member_objs) -> None:
    """For each user, keep only the row with highest access_level."""
    best: dict[int, dict] = {}
    for m in member_objs:
        row = _member_row(entity_type, entity_id, m)
        existing = best.get(m.id)
        if existing is None or row["access_level"] > existing["access_level"]:
            best[m.id] = row
    for row in best.values():
        cache.write_member(conn, row)


ProgressFn = "Callable[[str], None]"


def _noop_progress(_msg: str) -> None:
    pass


def _is_forbidden(exc: Exception) -> bool:
    """True if a GitLab API exception represents an HTTP 403.

    Per-entity 403s are recoverable — the admin can't see one specific
    group or project; the rest of the sync should still complete.
    Distinct from auth errors (401), which kill the whole sync.
    """
    code = getattr(exc, "response_code", None)
    return code == 403


def sync_all(
    gl: gitlab.Gitlab,
    *,
    cache_path: Path,
    tool_version: str,
    progress: "ProgressFn" = _noop_progress,
) -> None:
    """Fetch everything visible to the token and replace `cache_path`
    atomically. Raises SyncFailed on any API error; existing cache is
    not touched on failure.

    `progress` is called with human-readable status strings as the sync
    advances (group N of M, project counts, etc.). Defaults to a no-op
    so library callers don't see anything; the CLI passes a stderr
    printer.
    """
    started = _utcnow_iso()
    cache_path = Path(cache_path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_str = tempfile.mkstemp(
        prefix="browse-", suffix=".sqlite.tmp", dir=cache_path.parent
    )
    os.close(fd)
    tmp_path = Path(tmp_str)
    try:
        with cache.connect(tmp_path) as conn:
            cache.init_schema(conn)
            # Disable FK enforcement during bulk load. Two reasons:
            # (a) the API doesn't guarantee parents arrive before
            # subgroups, so insertion order would otherwise trip
            # `groups.parent_id REFERENCES groups(id)`; and (b) admins
            # can occasionally see a subgroup whose parent isn't in
            # the result set at all (e.g., parent archived or deleted).
            # We clean up case (b) below by nullifying orphan parent_ids,
            # then re-enable FK enforcement before committing.
            conn.execute("PRAGMA foreign_keys = OFF")
            progress(f"Listing groups from {gl.url}...")
            try:
                groups = gl.groups.list(all=True, all_available=True)
            except gitlab.exceptions.GitlabError as exc:
                raise SyncFailed(f"failed to list groups: {exc}") from exc
            total_groups = len(groups)
            progress(f"Found {total_groups} groups; walking projects + members")
            # Track ids we've already persisted in this sync. A project can
            # appear in multiple groups' listings when it's *shared* with
            # those groups (common GitLab pattern for code-review groups
            # like "approvers/engineers"). Skipping dupes avoids both the
            # UNIQUE constraint violation and a redundant members fetch.
            seen_group_ids: set[int] = set()
            seen_project_ids: set[int] = set()
            skipped: list[str] = []
            project_total = 0
            for i, g in enumerate(groups, start=1):
                if g.id in seen_group_ids:
                    progress(
                        f"  [{i}/{total_groups}] {g.full_path:<40} (already seen — skipped)"
                    )
                    continue
                seen_group_ids.add(g.id)
                cache.write_group(conn, _group_row(g))
                try:
                    group_obj = gl.groups.get(g.id)
                    g_members = group_obj.members_all.list(all=True)
                except gitlab.exceptions.GitlabError as exc:
                    if _is_forbidden(exc):
                        skipped.append(f"group {g.full_path} (members: 403)")
                        progress(
                            f"  [{i}/{total_groups}] {g.full_path:<40} (skipped: 403 on members)"
                        )
                        continue
                    raise SyncFailed(f"failed to list members for group {g.full_path}: {exc}") from exc
                _write_members_deduped(conn, "group", g.id, g_members)

                try:
                    projects = group_obj.projects.list(all=True, include_subgroups=False)
                except gitlab.exceptions.GitlabError as exc:
                    if _is_forbidden(exc):
                        skipped.append(f"group {g.full_path} (projects: 403)")
                        progress(
                            f"  [{i}/{total_groups}] {g.full_path:<40} (skipped: 403 on projects)"
                        )
                        continue
                    raise SyncFailed(f"failed to list projects for group {g.full_path}: {exc}") from exc
                new_projects = [p for p in projects if p.id not in seen_project_ids]
                dup_count = len(projects) - len(new_projects)
                project_total += len(new_projects)
                shared_note = f", {dup_count} shared/already-seen" if dup_count else ""
                progress(
                    f"  [{i}/{total_groups}] {g.full_path:<40} "
                    f"({len(new_projects)} new project(s){shared_note}, {len(g_members)} member(s))"
                )
                for p in new_projects:
                    seen_project_ids.add(p.id)
                    cache.write_project(conn, _project_row(p))
                    try:
                        p_obj = gl.projects.get(p.id)
                        p_members = p_obj.members_all.list(all=True)
                    except gitlab.exceptions.GitlabError as exc:
                        if _is_forbidden(exc):
                            skipped.append(
                                f"project {p.path_with_namespace} (members: 403)"
                            )
                            continue
                        raise SyncFailed(f"failed to list members for project {p.path_with_namespace}: {exc}") from exc
                    _write_members_deduped(conn, "project", p.id, p_members)

            # Personal-namespace projects: projects under a *user*
            # namespace (e.g. /kal/scratch) aren't reachable via the
            # /groups endpoint because user namespaces aren't groups.
            # List all visible projects and pick up the ones whose
            # namespace.kind == "user" that we haven't seen yet.
            progress("Listing personal-namespace projects...")
            try:
                all_projects = gl.projects.list(all=True)
            except gitlab.exceptions.GitlabError as exc:
                raise SyncFailed(
                    f"failed to list projects for personal-namespace scan: {exc}"
                ) from exc

            personal_new = 0
            personal_skipped = 0
            for p in all_projects:
                ns = getattr(p, "namespace", {}) or {}
                if ns.get("kind") != "user":
                    continue
                if p.id in seen_project_ids:
                    continue
                seen_project_ids.add(p.id)
                cache.write_project(conn, _project_row(p))
                try:
                    p_obj = gl.projects.get(p.id)
                    p_members = p_obj.members_all.list(all=True)
                except gitlab.exceptions.GitlabError as exc:
                    if _is_forbidden(exc):
                        skipped.append(
                            f"project {p.path_with_namespace} (members: 403)"
                        )
                        personal_skipped += 1
                        personal_new += 1
                        continue
                    raise SyncFailed(
                        f"failed to list members for project {p.path_with_namespace}: {exc}"
                    ) from exc
                _write_members_deduped(conn, "project", p.id, p_members)
                personal_new += 1
            project_total += personal_new
            if personal_new:
                note = ""
                if personal_skipped:
                    note = f" ({personal_skipped} with 403 on members)"
                progress(f"  Added {personal_new} personal-namespace project(s){note}")
            else:
                progress("  No personal-namespace projects to add.")

            # Nullify any orphan parent_ids (parent group not in result set).
            # Model layer treats parent_id=NULL as top-level, so orphans get
            # promoted rather than disappearing or breaking referential checks.
            conn.execute(
                "UPDATE groups SET parent_id = NULL "
                "WHERE parent_id IS NOT NULL "
                "AND parent_id NOT IN (SELECT id FROM groups)"
            )

            cache.write_snapshot(conn, cache.SnapshotRow(
                started_at=started,
                completed_at=_utcnow_iso(),
                gitlab_url=gl.url,
                tool_version=tool_version,
            ))
            if skipped:
                progress(f"Skipped {len(skipped)} entit{'y' if len(skipped) == 1 else 'ies'} due to access errors:")
                for s in skipped[:10]:
                    progress(f"  - {s}")
                if len(skipped) > 10:
                    progress(f"  ... and {len(skipped) - 10} more")
            progress(f"Committing: {total_groups} groups, {project_total} projects.")
            conn.commit()
            # Re-enable FK enforcement for any subsequent reads
            # (cache.connect() also sets this; this is belt-and-braces).
            conn.execute("PRAGMA foreign_keys = ON")
            progress("Done.")

        os.replace(tmp_path, cache_path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise
