"""Validate every knowledge/**/*.md file's frontmatter against the
shipped JSON Schema (schemas/article-frontmatter.schema.json).

Co-located with drift_check.py because they share a hand-parser for
YAML frontmatter and the same zero-deps philosophy. Both run from the
GH Action (drift-check is wired up; validate-articles can be wired
later) and from the local CLI shim under scripts/.

Validation is intentionally narrow — only the fields we ship in the
schema. Doesn't pretend to be a general JSON Schema validator. The
schema file is the contract; this validator enforces it.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


# -- Frontmatter parser (richer than drift_check's affects-only parser) --

def parse_frontmatter(article_path: Path) -> dict | None:
    """Return the frontmatter as a dict, or None if absent / malformed.

    Supports the subset our schema needs:
      - scalar fields: title, type, area, updated, status, load_bearing
      - block lists: affects: [...], references: [...]
      - inline lists: affects: [a, b]

    Strings can be unquoted, single-quoted, or double-quoted. Booleans
    are literal `true`/`false`. Dates are kept as strings (validated
    by pattern downstream).
    """
    try:
        text = article_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    if not text.startswith("---"):
        return None
    end_idx = text.find("\n---", 3)
    if end_idx == -1:
        return None
    fm_lines = text[3:end_idx].splitlines()

    data: dict = {}
    current_list_key: str | None = None
    for raw_line in fm_lines:
        line = raw_line.rstrip()
        if not line.strip():
            continue
        if current_list_key is not None:
            if line.lstrip().startswith("-"):
                val = _strip_quotes(line.lstrip()[1:].strip())
                if val:
                    data[current_list_key].append(val)
                continue
            current_list_key = None
        # Top-level key: value
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*)$", line)
        if not m:
            continue
        key, rest = m.group(1), m.group(2).strip()
        if rest == "":
            # Following lines should be a `- item` list
            data[key] = []
            current_list_key = key
        elif rest.startswith("[") and rest.endswith("]"):
            inner = rest[1:-1].strip()
            items = (
                [_strip_quotes(s.strip()) for s in inner.split(",") if s.strip()]
                if inner else []
            )
            data[key] = items
        elif rest in ("true", "false"):
            data[key] = rest == "true"
        else:
            data[key] = _strip_quotes(rest)
    return data


def _strip_quotes(s: str) -> str:
    if (s.startswith("'") and s.endswith("'")) or (
        s.startswith('"') and s.endswith('"')
    ):
        return s[1:-1]
    return s


# -- Validator --

# Mirrors the JSON Schema. If the schema file changes, this list must
# follow. The schema is the contract; this is the enforcer.
REQUIRED_FIELDS = ("title", "type", "area", "updated", "status")
ENUM_TYPE = ("concept", "connection", "meta")
ENUM_STATUS = ("thin", "mature", "deprecated")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MD_RE = re.compile(r".*\.md$")


def validate_frontmatter(
    data: dict, article_path: Path, knowledge_root: Path
) -> list[str]:
    """Return a list of error messages. Empty list means valid."""
    errors: list[str] = []

    for field in REQUIRED_FIELDS:
        if field not in data:
            errors.append(f"missing required field: '{field}'")
        elif not isinstance(data[field], str) or not data[field].strip():
            errors.append(f"field '{field}' must be a non-empty string")

    if "type" in data and isinstance(data["type"], str):
        if data["type"] not in ENUM_TYPE:
            errors.append(
                f"type '{data['type']}' not in {{{', '.join(ENUM_TYPE)}}}"
            )
    if "status" in data and isinstance(data["status"], str):
        if data["status"] not in ENUM_STATUS:
            errors.append(
                f"status '{data['status']}' not in "
                f"{{{', '.join(ENUM_STATUS)}}}"
            )
    if "updated" in data and isinstance(data["updated"], str):
        if not DATE_RE.match(data["updated"]):
            errors.append(
                f"updated '{data['updated']}' must match YYYY-MM-DD"
            )
    if "load_bearing" in data and not isinstance(data["load_bearing"], bool):
        errors.append("load_bearing must be a boolean")
    if "affects" in data:
        if not isinstance(data["affects"], list) or not all(
            isinstance(x, str) and x for x in data["affects"]
        ):
            errors.append("affects must be a list of non-empty strings")
    if "references" in data:
        if not isinstance(data["references"], list):
            errors.append("references must be a list of strings")
        else:
            for ref in data["references"]:
                if not isinstance(ref, str) or not MD_RE.match(ref):
                    errors.append(f"reference '{ref}' must end in .md")
                    continue
                # Check that the referenced article actually exists.
                ref_path = knowledge_root / ref
                if not ref_path.exists():
                    errors.append(
                        f"reference '{ref}' not found at {ref_path}"
                    )
    return errors


def validate_repo(knowledge_dir: str) -> dict:
    """Walk knowledge/**/*.md, validate each. Return aggregate result.

    Returns:
        files_checked: int
        files_with_errors: list of (path, [errors])
        total_errors: int
    """
    knowledge = Path(knowledge_dir)
    if not knowledge.exists() or not knowledge.is_dir():
        return {
            "files_checked": 0,
            "files_with_errors": [],
            "total_errors": 0,
            "skipped_reason": f"{knowledge_dir}/ not found",
        }
    files_with_errors: list[tuple[str, list[str]]] = []
    files_checked = 0
    for article in sorted(knowledge.rglob("*.md")):
        # Skip index.md and log.md by convention — they're not concept
        # articles and don't need frontmatter.
        if article.name in {"index.md", "log.md"}:
            continue
        files_checked += 1
        data = parse_frontmatter(article)
        if data is None:
            files_with_errors.append((str(article), ["no frontmatter found"]))
            continue
        errs = validate_frontmatter(data, article, knowledge)
        if errs:
            files_with_errors.append((str(article), errs))
    total_errors = sum(len(errs) for _, errs in files_with_errors)
    return {
        "files_checked": files_checked,
        "files_with_errors": files_with_errors,
        "total_errors": total_errors,
    }


def cli_main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="validate-articles",
        description=(
            "Validate every knowledge/**/*.md article's frontmatter "
            "against the shipped schema. Exit 1 if any file fails."
        ),
    )
    parser.add_argument(
        "--knowledge-dir", default="knowledge",
        help="path to knowledge/ directory (default: knowledge)",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="emit machine-readable JSON instead of human report",
    )
    args = parser.parse_args(argv)

    result = validate_repo(args.knowledge_dir)
    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        if "skipped_reason" in result:
            print(f"⚠️ Skipped: {result['skipped_reason']}")
            return 0
        if result["total_errors"] == 0:
            print(
                f"✅ All {result['files_checked']} article(s) have valid "
                f"frontmatter."
            )
            return 0
        print(
            f"⚠️ Frontmatter validation: {result['total_errors']} "
            f"error(s) across {len(result['files_with_errors'])} file(s) "
            f"(checked {result['files_checked']})."
        )
        for path, errs in result["files_with_errors"]:
            print(f"\n  {path}:")
            for e in errs:
                print(f"    - {e}")

    return 1 if result["total_errors"] > 0 else 0


if __name__ == "__main__":
    sys.exit(cli_main())
