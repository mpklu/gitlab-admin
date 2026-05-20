"""Indented tree → stdout. Renderer is pure: takes a Tree, returns a string."""

from __future__ import annotations

from datetime import date, datetime
from io import StringIO
from typing import Optional

from .model import Group, Project, Tree

_VIS_SHORT = {"private": "prv", "internal": "int", "public": "pub"}


def _short_date(iso: str) -> str:
    return iso.split("T")[0]


def _project_line(p: Project, indent: str) -> str:
    arch = "  [archived]" if p.archived else "            "
    return (
        f"{indent}▢ {p.name:<24}{arch}    "
        f"{p.owner} · {_short_date(p.last_activity_at)} · {_VIS_SHORT.get(p.visibility, p.visibility)}"
    )


def _walk_group(g: Group, prefix: str, is_last: bool, out: StringIO, *, depth: int) -> None:
    # Group header line.
    if depth == 0:
        head = f"📁 {g.name:<60}"
    else:
        connector = "└── " if is_last else "├── "
        head = f"{prefix}{connector}📁 {g.name:<55}"
    # Owner annotation: lowest-user_id Owner-access member, if any.
    owners = sorted((m for m in g.members if m.is_owner), key=lambda m: m.user_id)
    if owners:
        head += f"— {owners[0].username} (owner)"
    elif depth > 0:
        head += f"— {len(g.projects)} project(s)"
    out.write(head.rstrip() + "\n")

    # Children (subgroups + projects).
    child_prefix = prefix + ("    " if is_last else "│   ") if depth > 0 else ""
    entries = [("g", sg) for sg in g.subgroups] + [("p", p) for p in g.projects]
    for i, (kind, child) in enumerate(entries):
        last = i == len(entries) - 1
        if kind == "g":
            _walk_group(child, child_prefix, last, out, depth=depth + 1)
        else:
            connector = "└── " if last else "├── "
            out.write(_project_line(child, child_prefix + connector).rstrip() + "\n")


def _filter_tree(
    tree: Tree,
    *,
    include_archived: bool,
    owner: Optional[str],
    root_group: Optional[str],
    stale_days: Optional[int],
    today: Optional[str],
) -> Tree:
    """Return a shallow-copied Tree with non-matching projects removed."""
    if today is None:
        today_d = date.today()
    else:
        today_d = date.fromisoformat(today)

    def project_keeps(p: Project) -> bool:
        if not include_archived and p.archived:
            return False
        if owner and p.owner != owner:
            return False
        if stale_days is not None:
            activity = date.fromisoformat(_short_date(p.last_activity_at))
            if (today_d - activity).days < stale_days:
                return False
        return True

    def prune_group(g: Group) -> Optional[Group]:
        new_subs = [s for s in (prune_group(sg) for sg in g.subgroups) if s is not None]
        new_projects = [p for p in g.projects if project_keeps(p)]
        if not new_subs and not new_projects and (owner or stale_days is not None or not include_archived):
            return None
        # shallow copy with replaced children
        return Group(
            id=g.id, parent_id=g.parent_id, full_path=g.full_path, name=g.name,
            visibility=g.visibility, description=g.description, web_url=g.web_url,
            created_at=g.created_at, subgroups=new_subs, projects=new_projects,
            members=g.members,
        )

    top = [g for g in (prune_group(g) for g in tree.top_level_groups) if g is not None]
    if root_group is not None:
        top = [g for g in top if g.full_path == root_group or g.full_path.startswith(root_group + "/")]
        # Also filter subgroups recursively if root targets a deeper path.
    personal = [p for p in tree.personal_projects if project_keeps(p)]
    if root_group is not None:
        personal = []  # personal projects are outside the group tree
    return Tree(snapshot=tree.snapshot, top_level_groups=top, personal_projects=personal)


def render(
    tree: Tree,
    *,
    use_ansi: bool = True,
    include_archived: bool = True,
    owner: Optional[str] = None,
    root_group: Optional[str] = None,
    stale_days: Optional[int] = None,
    today: Optional[str] = None,
) -> str:
    """Render the tree to a plain string. ANSI not yet implemented; the
    flag is accepted so the CLI can pass it through unchanged once ANSI
    lands in a follow-up."""
    tree = _filter_tree(
        tree,
        include_archived=include_archived,
        owner=owner,
        root_group=root_group,
        stale_days=stale_days,
        today=today,
    )

    out = StringIO()
    for g in tree.top_level_groups:
        _walk_group(g, "", is_last=True, out=out, depth=0)

    if tree.personal_projects:
        out.write("\n👤 Personal projects\n")
        for i, p in enumerate(tree.personal_projects):
            last = i == len(tree.personal_projects) - 1
            connector = "└── " if last else "├── "
            line = (
                f"{connector}▢ {p.path_with_namespace:<30}              "
                f"{p.owner} · {_short_date(p.last_activity_at)} · "
                f"{_VIS_SHORT.get(p.visibility, p.visibility)}"
            )
            out.write(line.rstrip() + "\n")

    if tree.snapshot is not None:
        total_projects = sum(
            len(g.projects) + sum(len(sg.projects) for sg in g.subgroups)
            for g in tree.top_level_groups
        ) + len(tree.personal_projects)
        total_groups = sum(1 + len(g.subgroups) for g in tree.top_level_groups)
        out.write(
            f"\nSnapshot: {tree.snapshot.completed_at} · "
            f"{tree.snapshot.gitlab_url} · "
            f"{total_projects} projects across {total_groups} groups\n"
        )

    return out.getvalue()
