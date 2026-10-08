#!/usr/bin/env python3
"""Regenerate the org-wide ROADMAP-INDEX.md table from live GitHub data.

The inventory in ``ROADMAP-INDEX.md`` is a point-in-time snapshot of which
``tuna-os`` repositories carry a ``ROADMAP.md`` on their default branch. It was
tracked by hand, and it drifted: the real active repo count grew from 37 to 40
between two verification passes and nobody noticed because the table only ever
re-checked the repos it already listed (tuna-os/.github#110, tunaos#1295,
tunaos#1361).

This script re-derives the table from the GitHub API and rewrites the table
region of the document in place, so a scheduled workflow can open a PR whenever
the committed table has gone stale instead of letting it rot.

It deliberately mirrors the regeneration block documented inside
ROADMAP-INDEX.md, including its one load-bearing detail: a repository is judged
to "have a roadmap" by the *exit status* of the ``gh api`` contents request,
not by whether a ``--jq`` filter captured a non-empty string. On a 404 ``gh
api`` prints the raw JSON error body to stdout *past* a ``--jq`` filter, so a
string-emptiness test produces a false "has a roadmap" positive.

The script touches only the data-derived parts of the document:

* the ``**Last verified:**`` date,
* the ``## Coverage: X / Y active repos`` count, and
* the ``| Repo | Default branch | ROADMAP.md? |`` table itself.

Everything else in the file (scope note, scope correction, the prose explaining
each repo that lacks a roadmap, the notes, the "Related" links) is human
maintained and is left untouched.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import date, datetime, timezone
from typing import Callable, Iterable, Optional, Sequence, Tuple

ORG = "tuna-os"
INDEX_FILE = "ROADMAP-INDEX.md"

TABLE_HEADER = "| Repo | Default branch | ROADMAP.md? |"
TABLE_SEP = "|---|---|---|"
YES = "✅"
NO = "❌"

# A row is (repo, default_branch, has_roadmap).
Row = Tuple[str, str, bool]

LAST_VERIFIED_RE = re.compile(r"\*\*Last verified\*\*: \d{4}-\d{2}-\d{2}")
COVERAGE_HEADING_RE = re.compile(r"^## Coverage: \d+ / \d+ active repos$", re.MULTILINE)


# --------------------------------------------------------------------------- #
# Network layer — thin wrappers around `gh`. All of it is injectable so the
# pure document logic can be unit-tested without touching the network.
# --------------------------------------------------------------------------- #

def _gh(args: Sequence[str], env: Optional[dict] = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["gh", *args],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def active_repos(org: str = ORG, env: Optional[dict] = None) -> list[str]:
    """Names of every active (non-archived) repo in the org, sorted.

    Mirrors ``gh repo list <org> --limit 200 --json name,isArchived --jq
    '.[] | select(.isArchived==false) | .name' | sort``.
    """
    proc = _gh(
        ["repo", "list", org, "--limit", "200", "--json", "name,isArchived"],
        env=env,
    )
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        raise SystemExit(f"gh repo list failed (exit {proc.returncode})")
    data = json.loads(proc.stdout)
    return sorted(item["name"] for item in data if not item.get("isArchived", False))


def default_branch(repo: str, env: Optional[dict] = None) -> Optional[str]:
    """Default branch for a repo, or None if the repo cannot be read."""
    proc = _gh(["api", f"repos/{ORG}/{repo}", "--jq", ".default_branch"], env=env)
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def has_roadmap(repo: str, branch: str, env: Optional[dict] = None) -> bool:
    """True iff ``repo`` has ROADMAP.md on ``branch``.

    Decided by the exit status of the contents request, never by parsing its
    stdout — see the module docstring for why a string test is wrong.
    """
    proc = _gh(
        ["api", f"repos/{ORG}/{repo}/contents/ROADMAP.md?ref={branch}"],
        env=env,
    )
    return proc.returncode == 0


def collect_rows(
    org: str = ORG,
    env: Optional[dict] = None,
    active: Optional[Callable[[], list[str]]] = None,
    branch_of: Optional[Callable[[str], Optional[str]]] = None,
    roadmap_of: Optional[Callable[[str, str], bool]] = None,
) -> list[Row]:
    """Build the ``(repo, branch, has_roadmap)`` rows for every active repo.

    The three callables let the network layer be swapped for a stub in tests;
    when omitted the real ``gh``-backed functions are used.
    """
    env = env if env is not None else dict(os.environ)
    names = active() if active is not None else active_repos(org, env)
    branch_of = branch_of if branch_of is not None else default_branch
    roadmap_of = roadmap_of if roadmap_of is not None else has_roadmap

    rows: list[Row] = []
    for name in names:
        branch = branch_of(name, env)
        if branch is None:
            # Repo vanished or is unreadable between the list call and this
            # lookup; skip it rather than emitting a bogus row.
            continue
        rows.append((name, branch, roadmap_of(name, branch, env)))
    return rows


# --------------------------------------------------------------------------- #
# Pure document logic — the part that is unit-tested.
# --------------------------------------------------------------------------- #

def coverage_count(rows: Iterable[Row]) -> Tuple[int, int]:
    """Return ``(repos_with_roadmap, total_active_repos)``."""
    rows = list(rows)
    total = len(rows)
    with_roadmap = sum(1 for _, _, has in rows if has)
    return with_roadmap, total


def render_table(rows: Iterable[Row]) -> str:
    """Render the markdown table (header, separator, one row per repo)."""
    rows = list(rows)
    out = [TABLE_HEADER, TABLE_SEP]
    for name, branch, has in rows:
        cell = YES if has else NO
        out.append(f"| {name} | {branch} | {cell} |")
    return "\n".join(out)


def _replace_table_region(text: str, rows: Sequence[Row]) -> str:
    """Replace the ``| Repo | ... |`` table block with freshly rendered rows.

    The block starts at the header row and runs through the last consecutive
    ``|``-prefixed data row. Everything before and after (including the blank
    line and the following ``##`` section) is preserved verbatim.
    """
    lines = text.split("\n")
    start = next(
        (i for i, line in enumerate(lines) if line == TABLE_HEADER),
        None,
    )
    if start is None:
        # No existing table to replace; append a fresh one at the end.
        rendered = render_table(rows).split("\n")
        if lines and lines[-1] != "":
            lines.append("")
        lines.extend(rendered)
        return "\n".join(lines)

    # Header, separator, then every consecutive data row.
    end = start + 1
    while end < len(lines) and lines[end].startswith("|"):
        end += 1
    # ``end`` now points at the first non-table line (usually a blank line).
    new_lines = lines[:start] + render_table(rows).split("\n") + lines[end:]
    return "\n".join(new_lines)


def apply_updates(text: str, rows: Sequence[Row], today: date) -> str:
    """Return ``text`` with the date, count and table refreshed for ``rows``."""
    with_roadmap, total = coverage_count(rows)
    date_str = today.isoformat()

    text = LAST_VERIFIED_RE.sub(f"**Last verified**: {date_str}", text)
    text = COVERAGE_HEADING_RE.sub(
        f"## Coverage: {with_roadmap} / {total} active repos",
        text,
    )
    text = _replace_table_region(text, rows)
    return text


def regenerate(source: str, rows: Sequence[Row], today: Optional[date] = None) -> Tuple[str, bool]:
    """Return ``(new_text, changed)`` for the current document ``source``."""
    today = today if today is not None else datetime.now(timezone.utc).date()
    new_text = apply_updates(source, rows, today)
    return new_text, new_text != source


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def _read_index(path: str) -> str:
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _write_index(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Regenerate the tuna-os ROADMAP-INDEX.md table from live data.",
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=INDEX_FILE,
        help=f"Path to the inventory document (default: {INDEX_FILE})",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--write",
        action="store_true",
        help="Rewrite the document in place when it has drifted.",
    )
    mode.add_argument(
        "--diff",
        action="store_true",
        help="Print the proposed table and exit without writing.",
    )
    mode.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 on drift, 0 in sync. This is the default.",
    )
    args = parser.parse_args(argv)

    rows = collect_rows()
    if not rows:
        sys.stderr.write("no active repositories returned; refusing to rewrite\n")
        return 2

    source = _read_index(args.path)
    new_text, changed = regenerate(source, rows)

    with_roadmap, total = coverage_count(rows)
    print(f"{with_roadmap} / {total} active repos have ROADMAP.md")

    if args.diff:
        print()
        print(render_table(rows))
        return 0

    if not changed:
        print("in sync — no changes needed")
        return 0

    if args.write:
        _write_index(args.path, new_text)
        print("drift detected — wrote new table")
        return 0

    # Default mode: report drift without writing.
    print("drift detected — table is stale", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
