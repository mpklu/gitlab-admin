"""argparse CLI for `python -m gitlab_admin.browse`.

Exit codes (per spec §5):
  0 success
  1 cache missing / schema mismatch (not --refresh)
  2 network error during refresh
  3 auth error (env vars missing or rejected)
  4 unexpected error / arg violation
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from dotenv import load_dotenv

from gitlab_admin import __version__, client
from . import cache, fetch, model, render_text


EXIT_OK = 0
EXIT_NO_CACHE = 1
EXIT_NETWORK = 2
EXIT_AUTH = 3
EXIT_UNEXPECTED = 4


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m gitlab_admin.browse")
    p.add_argument("--refresh", action="store_true",
                   help="Re-fetch from GitLab before rendering.")
    p.add_argument("--cache-path", type=Path, default=cache.default_cache_path(),
                   help=f"SQLite cache path (default: {cache.default_cache_path()}).")
    p.add_argument("--gitlab-url", help="Override GITLAB_URL for this invocation.")
    p.add_argument("--gitlab-token", help="Override GITLAB_TOKEN for this invocation.")
    p.add_argument("--env-file", type=Path, metavar="PATH",
                   help="Load env vars from this .env file before reading the "
                        "environment. Default: walk up from CWD looking for `.env`. "
                        "Shell env vars always win over file values.")

    # Output modes (mutually exclusive)
    modes = p.add_mutually_exclusive_group()
    modes.add_argument("--json", action="store_true",
                       help="Emit JSON to stdout instead of a text tree.")
    modes.add_argument("--html", type=Path, metavar="PATH",
                       help="Write HTML report to PATH (not implemented in this plan).")
    modes.add_argument("-i", "--interactive", action="store_true",
                       help="Interactive menu mode (not implemented in this plan).")

    # Text-tree filters
    p.add_argument("--group", dest="root_group", metavar="PATH",
                   help="Root the tree at this group.")
    p.add_argument("--owner", help="Show only projects owned by this username.")
    p.add_argument("--stale-days", type=int, metavar="N",
                   help="Show only projects with no activity in the last N days.")
    p.add_argument("--no-archived", action="store_true",
                   help="Hide archived projects.")
    return p


def _print_progress(msg: str) -> None:
    print(f"[browse] {msg}", file=sys.stderr, flush=True)


def _refresh(args, cache_path: Path) -> int:
    try:
        gl = client.get_client(url=args.gitlab_url, token=args.gitlab_token)
    except client.MissingCredentials as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_AUTH
    try:
        fetch.sync_all(
            gl,
            cache_path=cache_path,
            tool_version=__version__,
            progress=_print_progress,
        )
    except fetch.SyncFailed as exc:
        print(f"refresh failed: {exc}", file=sys.stderr)
        print(
            f"existing cache (if any) unchanged at {cache_path}",
            file=sys.stderr,
        )
        return EXIT_NETWORK
    return EXIT_OK


def _ensure_cache(cache_path: Path) -> int:
    if not cache_path.exists():
        print(
            f"No cache at {cache_path}. Run with --refresh first.",
            file=sys.stderr,
        )
        return EXIT_NO_CACHE
    with cache.connect(cache_path) as conn:
        version = cache.read_schema_version(conn)
    if version != cache.SCHEMA_VERSION:
        print(
            f"Cache schema is v{version}; tool expects v{cache.SCHEMA_VERSION}. "
            "Re-run with --refresh.",
            file=sys.stderr,
        )
        return EXIT_NO_CACHE
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    # Load .env early so subsequent reads of GITLAB_URL/GITLAB_TOKEN see it.
    # override=False — actual shell env vars take precedence over file values.
    if args.env_file is not None:
        load_dotenv(args.env_file, override=False)
    else:
        load_dotenv(override=False)

    if args.html is not None or args.interactive:
        print(
            "--html and --interactive land in Plan 2 / Plan 3. Use the text "
            "renderer or --json for now.",
            file=sys.stderr,
        )
        return EXIT_UNEXPECTED

    cache_path: Path = args.cache_path

    if args.refresh:
        rc = _refresh(args, cache_path)
        if rc != EXIT_OK:
            return rc

    rc = _ensure_cache(cache_path)
    if rc != EXIT_OK:
        return rc

    with cache.connect(cache_path) as conn:
        tree = model.build_tree(conn)

    if args.json:
        from . import render_json
        sys.stdout.write(render_json.render(tree))
        return EXIT_OK

    output = render_text.render(
        tree,
        use_ansi=sys.stdout.isatty(),
        include_archived=not args.no_archived,
        owner=args.owner,
        root_group=args.root_group,
        stale_days=args.stale_days,
    )
    sys.stdout.write(output)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
