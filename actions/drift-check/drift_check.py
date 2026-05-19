#!/usr/bin/env python3
"""Drift check for the living-documentation methodology.

Two mapping sources, merged in priority order:

  1. Article frontmatter `affects:` globs (canonical; co-located with the
     content they document — see concepts/methodology/affects-globs.md).
  2. The legacy article-mapping table in CLAUDE.md (kept for backward
     compatibility while adopters migrate `affects:` into article
     frontmatter).

For each changed file, the check finds articles whose `affects:` globs
or whose CLAUDE.md table row patterns match. If the matched article
itself was not changed in this PR, that's a violation: the same-task
rule was skipped.

Inputs (env vars):
    CLAUDE_MD_PATH    — path to CLAUDE.md (default: CLAUDE.md)
    KNOWLEDGE_DIR     — path to knowledge directory (default: knowledge)
    BASE_REF          — base ref to diff against (default: $GITHUB_BASE_REF
                        or "main")
    FAIL_ON_VIOLATION — "true" or "false" (default: "true")
    GITHUB_OUTPUT     — path to the GitHub Actions output file (set by GitHub)

Outputs (via $GITHUB_OUTPUT, when set):
    violations — count of violations
    report     — markdown-formatted report

Exit codes:
    0  — no violations, or violations found and FAIL_ON_VIOLATION=false
    1  — violations found and FAIL_ON_VIOLATION=true
    2  — configuration / parse error
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class MappingRow:
    """One row of the article-mapping table."""

    code_pattern: str  # e.g., "src/workflows/*.py" or "the LLM agent"
    article_path: str  # e.g., "knowledge/concepts/x.md"


def parse_frontmatter_affects(article_path: Path) -> list[str]:
    """Extract the `affects:` glob list from an article's YAML frontmatter.

    Articles without frontmatter, or without an `affects:` field, return [].
    Hand-parses the simple shape we ship in the schema; doesn't pull in
    PyYAML to keep the Action's runtime dependency-free.
    """
    try:
        text = article_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []

    if not text.startswith("---"):
        return []
    end_idx = text.find("\n---", 3)
    if end_idx == -1:
        return []
    fm_lines = text[3:end_idx].splitlines()

    affects: list[str] = []
    in_affects = False
    for line in fm_lines:
        stripped = line.strip()
        if not in_affects and stripped.startswith("affects:"):
            # Inline form `affects: [a, b]` (rare; we ship the block form,
            # but accept either for robustness).
            inline = stripped[len("affects:"):].strip()
            if inline.startswith("[") and inline.endswith("]"):
                items = [
                    s.strip().strip("'\"")
                    for s in inline[1:-1].split(",")
                    if s.strip()
                ]
                affects.extend(items)
                continue
            in_affects = True
            continue
        if in_affects:
            if line.lstrip().startswith("-"):
                val = line.lstrip()[1:].strip()
                if (val.startswith("'") and val.endswith("'")) or (
                    val.startswith('"') and val.endswith('"')
                ):
                    val = val[1:-1]
                if val:
                    affects.append(val)
            else:
                # Next field or end of frontmatter — stop.
                in_affects = False
    return affects


def parse_articles_affects(knowledge_dir: str) -> list[MappingRow]:
    """Walk knowledge/**/*.md and emit MappingRows from each article's
    `affects:` frontmatter list.

    `article_path` on each row is recorded relative to the repo root so
    it can be compared against `git diff --name-only` output directly.
    """
    rows: list[MappingRow] = []
    knowledge = Path(knowledge_dir)
    if not knowledge.exists() or not knowledge.is_dir():
        return rows
    for article in sorted(knowledge.rglob("*.md")):
        affects = parse_frontmatter_affects(article)
        if not affects:
            continue
        article_str = str(article).replace("\\", "/")
        for glob in affects:
            rows.append(
                MappingRow(code_pattern=glob, article_path=article_str)
            )
    return rows


def parse_article_mapping(claude_md_text: str) -> list[MappingRow]:
    """Parse the article-mapping table from CLAUDE.md text.

    Looks for a Markdown table where:
    - The header row contains "When you change" and "Update this article"
      (case-insensitive).
    - Subsequent rows have two cells; the second cell contains a backticked
      path ending in .md.

    Returns an empty list if no mapping table is found, or if rows are
    malformed.
    """
    rows: list[MappingRow] = []
    lines = claude_md_text.splitlines()

    in_table = False
    for i, line in enumerate(lines):
        # Detect the header row of the mapping table.
        lower = line.lower()
        if "when you change" in lower and "update this article" in lower:
            in_table = True
            continue
        if in_table:
            # The line right after the header is the separator (| --- | --- |)
            if re.match(r"\s*\|[\s\-|]+\|\s*$", line):
                continue
            # End of table = blank line or non-table line
            if not line.strip().startswith("|"):
                in_table = False
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) < 2:
                continue
            code_pattern = cells[0]
            article_cell = cells[1]
            article_match = re.search(r"`([^`]+\.md)`", article_cell)
            if not article_match:
                continue
            rows.append(
                MappingRow(
                    code_pattern=code_pattern,
                    article_path=article_match.group(1),
                )
            )
    return rows


def get_changed_files(base_ref: str) -> list[str]:
    """Return the list of files changed between base_ref and HEAD.

    Two modes:
    - `base_ref == "HEAD"` — staged-vs-HEAD (i.e. `git diff --cached`).
      The pre-commit case: only files that are part of the about-to-be-
      created commit. Unstaged working-tree edits in unrelated files
      are intentionally excluded — they aren't being committed and
      including them produces false positives against articles whose
      `affects:` happens to match dirty-but-untouched paths.
    - Otherwise — `base_ref...HEAD` symmetric diff (PR-time / CI case).
    """
    if base_ref == "HEAD":
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", "--cached"],
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            print(f"::error::git diff failed: {e.stderr}", file=sys.stderr)
            sys.exit(2)
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]

    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", f"{base_ref}...HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        # Fallback: maybe base_ref was provided as a remote ref
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", base_ref, "HEAD"],
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError:
            print(f"::error::git diff failed: {e.stderr}", file=sys.stderr)
            sys.exit(2)
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _glob_to_regex(pattern: str) -> str:
    """Convert a glob (supporting `**` recursion) to a regex.

    Mapping:
      `**`  → `.*`         (matches across path separators)
      `*`   → `[^/]*`      (matches within a single path segment)
      `?`   → `[^/]`
      Other regex meta-chars are escaped.

    `a/**/b` matches both `a/b` and `a/x/y/b` (so the `/` immediately
    following `**` is treated as optional). This matches typical adopter
    expectations.
    """
    regex = ""
    i = 0
    while i < len(pattern):
        if pattern[i:i + 2] == "**":
            # If a `/` follows, treat `**/` as a single token meaning
            # "zero or more path segments" (so `a/**/b` matches `a/b`
            # and `a/x/y/b`). Otherwise emit a plain `.*`.
            #
            # We do NOT use `regex.rstrip(".*")` here: it would also
            # strip trailing `.` and `*` characters from preceding
            # tokens (e.g. the `*` in a just-emitted `[^/]*`, or an
            # escaped literal `\.`), corrupting the regex for patterns
            # like `foo*/**/bar` or `.**/x`.
            if i + 2 < len(pattern) and pattern[i + 2] == "/":
                regex += r"(?:.*/)?"
                i += 3
            else:
                regex += ".*"
                i += 2
        elif pattern[i] == "*":
            regex += "[^/]*"
            i += 1
        elif pattern[i] == "?":
            regex += "[^/]"
            i += 1
        elif pattern[i] in r".()[]{}+\|^$":
            regex += re.escape(pattern[i])
            i += 1
        else:
            regex += pattern[i]
            i += 1
    return f"^{regex}$"


def code_pattern_matches_files(
    code_pattern: str, changed_files: list[str]
) -> list[str]:
    """Determine which changed files match a mapping row's code pattern.

    The pattern can be:
    - A glob-like path (contains "/", "*", or ends in a code extension) —
      matched via a regex translation that supports `**` recursion. Cleaner
      than Python's fnmatch which collapses `**` to `*`.
    - A natural-language description (legacy CLAUDE.md table only) — matched
      by keyword: any changed file whose path contains any non-trivial word
      from the description. Best-effort fallback; new mappings should use
      glob form.

    Returns the subset of changed_files that match.
    """
    pattern = code_pattern.strip().strip("`")

    looks_like_path = "/" in pattern or "*" in pattern or pattern.endswith(
        (".py", ".ts", ".tsx", ".js", ".go", ".rs", ".rb", ".md", ".yml", ".yaml")
    )

    if looks_like_path:
        regex = _glob_to_regex(pattern)
        return [f for f in changed_files if re.match(regex, f)]

    # Natural-language description fallback: match by keyword.
    keywords = [
        w.lower()
        for w in re.findall(r"\b\w{4,}\b", pattern)
        if w.lower() not in {"this", "that", "with", "when", "from", "into", "code"}
    ]
    if not keywords:
        return []
    matches: list[str] = []
    for f in changed_files:
        f_lower = f.lower()
        if any(kw in f_lower for kw in keywords):
            matches.append(f)
    return matches


def check_drift(
    mapping: list[MappingRow],
    changed_files: list[str],
    knowledge_dir: str,
) -> list[dict]:
    """Identify violations: rows where code matched but article didn't change.

    Returns a list of violation dicts, each with:
        code_pattern   — the mapping row's code pattern
        article_path   — the expected article path
        matched_files  — which changed files matched the code pattern
    """
    violations: list[dict] = []
    changed_set = {f for f in changed_files}

    for row in mapping:
        matched = code_pattern_matches_files(row.code_pattern, changed_files)
        if not matched:
            continue
        # Normalize article path; allow it to be relative or knowledge-rooted.
        article = row.article_path
        if not article.startswith(knowledge_dir + "/") and not article.startswith(
            "/"
        ):
            article = f"{knowledge_dir}/{article}"
        if article in changed_set or article.lstrip("/") in changed_set:
            continue
        violations.append(
            {
                "code_pattern": row.code_pattern,
                "article_path": article,
                "matched_files": matched,
            }
        )
    return violations


def format_report(violations: list[dict], rows_total: int) -> str:
    """Format a markdown report of the check results."""
    if not violations:
        return (
            "✅ **Living Docs drift check passed.** "
            f"All {rows_total} mapped code paths that were touched in this PR "
            "have corresponding article updates."
        )

    lines = [
        "⚠️ **Living Docs drift check — same-task rule violations detected.**",
        "",
        f"This PR touches code paths listed in `CLAUDE.md`'s article-mapping "
        f"table, but does not update the corresponding articles. The "
        f"living-documentation methodology requires articles to be updated "
        f"in the **same task** as the code change.",
        "",
        "### Violations",
        "",
    ]
    for v in violations:
        lines.append(f"- **{v['code_pattern']}** → expected article: "
                     f"`{v['article_path']}`")
        for f in v["matched_files"][:5]:
            lines.append(f"    - changed file: `{f}`")
        if len(v["matched_files"]) > 5:
            lines.append(
                f"    - ... and {len(v['matched_files']) - 5} more changed file(s)"
            )
    lines.extend(
        [
            "",
            "### What to do",
            "",
            "1. **Capture first, refine second.** Add the missing article "
            "update(s) to this PR. An imperfect article is strictly better "
            "than a missed one — the reviewer can refine on review.",
            "2. If the article doesn't yet exist for one of the paths above, "
            "write the first thin article in the same PR (~200 words). See "
            "`CLAUDE.md` for placement guidance.",
            "3. Append an entry to `knowledge/log.md` listing what was touched.",
            "",
            "_If the matching is wrong (the code pattern is too broad or the "
            "article truly doesn't apply to this change), update the "
            "`CLAUDE.md` mapping table to fix the pattern — that's also a "
            "valid resolution._",
        ]
    )
    return "\n".join(lines)


def emit_output(name: str, value: str) -> None:
    """Write a value to GitHub Actions outputs, or stdout if not in Actions."""
    output_file = os.environ.get("GITHUB_OUTPUT")
    if output_file:
        with open(output_file, "a", encoding="utf-8") as f:
            # Multiline-safe output via heredoc syntax
            delim = "EOF_DRIFT_CHECK"
            f.write(f"{name}<<{delim}\n{value}\n{delim}\n")
    else:
        print(f"::{name}::{value}")


def run_check(
    claude_md_path: str,
    knowledge_dir: str,
    base_ref: str,
) -> dict:
    """Core drift check, I/O-free apart from reading the repo state.

    Returns a dict with:
        status   — 'no_claude_md' | 'no_mapping' | 'no_changes' | 'checked'
        report   — markdown-formatted human report
        violations    — list of violation dicts (only when status='checked')
        mapping_count — int
    Both env-var and CLI entry points consume this same shape.
    """
    claude_md = Path(claude_md_path)
    if not claude_md.exists():
        return {
            "status": "no_claude_md",
            "report": (
                f"⚠️ Living Docs drift check skipped — `{claude_md_path}` "
                "not found in this repository."
            ),
            "violations": [],
            "mapping_count": 0,
        }

    # Canonical: read each article's `affects:` frontmatter.
    frontmatter_mapping = parse_articles_affects(knowledge_dir)
    # Legacy fallback: hand-edited table in CLAUDE.md (kept for adopters
    # mid-migration; will eventually go away once frontmatter coverage is
    # complete in their repo).
    legacy_mapping = parse_article_mapping(claude_md.read_text(encoding="utf-8"))
    mapping = frontmatter_mapping + legacy_mapping

    if not mapping:
        return {
            "status": "no_mapping",
            "report": (
                "ℹ️ Living Docs drift check found no article-mapping (no "
                f"`affects:` frontmatter under `{knowledge_dir}/`, and no "
                f"mapping table in `{claude_md_path}`). Either the project "
                "hasn't started writing articles yet (brownfield retrofit, "
                "early days) or the formats aren't recognized. No "
                "violations reported."
            ),
            "violations": [],
            "mapping_count": 0,
        }

    changed_files = get_changed_files(base_ref)
    if not changed_files:
        return {
            "status": "no_changes",
            "report": "✅ No files changed; nothing to check.",
            "violations": [],
            "mapping_count": len(mapping),
        }

    violations = check_drift(mapping, changed_files, knowledge_dir)
    report = format_report(violations, len(mapping))
    return {
        "status": "checked",
        "report": report,
        "violations": violations,
        "mapping_count": len(mapping),
    }


def main() -> int:
    """GitHub Action entry — env-var driven, emits to GITHUB_OUTPUT."""
    claude_md_path = os.environ.get("CLAUDE_MD_PATH", "CLAUDE.md")
    knowledge_dir = os.environ.get("KNOWLEDGE_DIR", "knowledge")
    base_ref = (
        os.environ.get("BASE_REF")
        or os.environ.get("GITHUB_BASE_REF")
        or "main"
    )
    fail_on_violation = (
        os.environ.get("FAIL_ON_VIOLATION", "true").strip().lower() == "true"
    )

    if not Path(claude_md_path).exists():
        print(
            f"::error::CLAUDE.md not found at {claude_md_path}. "
            "Skipping drift check (no mapping to verify against).",
            file=sys.stderr,
        )

    result = run_check(claude_md_path, knowledge_dir, base_ref)
    emit_output("violations", str(len(result["violations"])))
    emit_output("report", result["report"])
    print(result["report"])

    if result["violations"] and fail_on_violation:
        return 1
    return 0


def cli_main(argv: list[str] | None = None) -> int:
    """Local CLI entry — argparse driven; print-only, no GITHUB_OUTPUT.

    Mirrors the GH Action's logic exactly so adopters can run the same
    check at commit time as runs at PR time. Local enforcement catches
    drift before push; the Action catches it if local was skipped or
    the contributor doesn't have the hook installed.
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="drift-check",
        description=(
            "Living-doc drift check — verify that code changes touch the "
            "matching knowledge article(s). Same logic as the GitHub Action; "
            "intended for local pre-commit hooks."
        ),
    )
    parser.add_argument("--claude-md", default="CLAUDE.md",
                        help="path to CLAUDE.md (default: CLAUDE.md)")
    parser.add_argument("--knowledge-dir", default="knowledge",
                        help="path to knowledge/ directory (default: knowledge)")
    parser.add_argument("--base-ref", default=None,
                        help="git ref to diff against (default: main, or "
                             "$BASE_REF / $GITHUB_BASE_REF if set)")
    parser.add_argument("--warn-only", action="store_true",
                        help="exit 0 even if violations are found "
                             "(default: exit 1 on violations)")
    args = parser.parse_args(argv)

    base_ref = (
        args.base_ref
        or os.environ.get("BASE_REF")
        or os.environ.get("GITHUB_BASE_REF")
        or "main"
    )

    result = run_check(args.claude_md, args.knowledge_dir, base_ref)
    print(result["report"])

    if result["violations"] and not args.warn_only:
        return 1
    return 0


if __name__ == "__main__":
    # Dispatch: only the GH runner sets GITHUB_ACTIONS=true. Anything
    # else (including a local shell that happens to have GITHUB_OUTPUT
    # exported from a prior CI debug session) routes to the CLI.
    if os.environ.get("GITHUB_ACTIONS") == "true":
        sys.exit(main())
    sys.exit(cli_main())
