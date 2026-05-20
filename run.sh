#!/usr/bin/env bash
# run.sh — canonical entry point for the gitlab-admin CLI.
#
# DESCRIPTION
#   The friendliest way to invoke gitlab-admin. Teammates who clone the
#   repo should be able to type `./run.sh --refresh` and have it work,
#   regardless of whether they already have uv, a venv, or anything
#   Python-specific set up. This script handles three things that
#   would otherwise be manual:
#
#     1. Install `uv` (Astral's Python package manager) if it isn't
#        already on PATH. Uses the official Astral installer.
#     2. Run `uv sync` so the project's virtualenv matches `uv.lock`
#        before each invocation. Idempotent and fast (~100 ms) when
#        nothing's stale.
#     3. Invoke `uv run python -m gitlab_admin.browse` with all
#        arguments forwarded through.
#
# USAGE
#   ./run.sh [browse options...]
#
#   Every argument after `./run.sh` is passed verbatim to the Python
#   CLI. There are no flags handled by this script itself — use
#   `./run.sh --help` for the underlying tool's full option list.
#
# EXAMPLES
#   ./run.sh                                    # text tree from cache
#   ./run.sh --refresh                          # full re-fetch + render
#   ./run.sh --json | jq '.groups[].full_path'  # script-friendly output
#   ./run.sh --group platform                   # subtree of the org
#   ./run.sh --owner kun.lu --no-archived       # filtered view
#   ./run.sh --refresh --env-file scripts/.env  # non-default .env location
#
# ENVIRONMENT
#   GITLAB_URL, GITLAB_TOKEN
#       Required for `--refresh`. Loaded from a `.env` file by default
#       (the Python CLI walks up from CWD via python-dotenv). Shell env
#       vars always win over file values. See
#       knowledge/concepts/gitlab/integration-model.md for the
#       precedence rules.
#
# EXIT CODES
#   0    success
#   1    cache missing / schema mismatch (no --refresh)
#   2    network error during refresh
#   3    auth error (GITLAB_URL / GITLAB_TOKEN missing or rejected)
#   4    unexpected error / argparse violation
#   126  this wrapper script failed (uv install, uv sync, etc.)
#
# REQUIREMENTS
#   - bash (not POSIX sh — relies on `set -o pipefail`)
#   - curl (only the first time, when uv is being installed)
#   - macOS or Linux (uv supports both natively)
#
# WHERE THIS LIVES
#   At the project root. Run it from anywhere — it `cd`s to its own
#   directory first so `uv sync` finds `pyproject.toml`.

set -euo pipefail

# ── Helpers ─────────────────────────────────────────────────────────
log() { printf "%s\n" "[run.sh] $*" >&2; }
fail() { log "ERROR: $*"; exit 126; }

# ── Locate ourselves and run from there ────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
cd "$SCRIPT_DIR"

# ── Ensure uv is installed ──────────────────────────────────────────
if ! command -v uv >/dev/null 2>&1; then
    log "uv not found on PATH; installing via the official Astral installer..."
    if ! command -v curl >/dev/null 2>&1; then
        fail "curl is required to install uv. Install curl, or install uv manually: https://docs.astral.sh/uv/getting-started/installation/"
    fi
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # The installer drops uv into ~/.local/bin/ by default. PATH may
    # not yet include it in this shell; ensure it does.
    if [[ -x "$HOME/.local/bin/uv" ]]; then
        export PATH="$HOME/.local/bin:$PATH"
    fi
    if ! command -v uv >/dev/null 2>&1; then
        fail "uv install completed but 'uv' is still not on PATH. Open a new terminal so PATH updates take effect, or add ~/.local/bin to PATH manually."
    fi
    log "uv installed: $(uv --version)"
fi

# ── Sync dependencies (idempotent; fast when in-sync) ──────────────
uv sync --quiet

# ── Run the CLI, forwarding all args ───────────────────────────────
# `exec` replaces this shell with the Python process so:
#   - Ctrl-C goes straight to Python
#   - Exit code is the CLI's, not the script's
#   - No extra layer in the process tree
exec uv run python -m gitlab_admin.browse "$@"
