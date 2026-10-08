#!/usr/bin/env python3
"""Pin the document-rewriting logic in roadmap-index.py.

Plain python3, no test framework -- matches how scripts/ is already run in CI
(``python3 scripts/test-roadmap-index.py``). The ``gh``-backed network layer is
exercised only by a manual smoke run (``scripts/roadmap-index.py --diff``), not
here, so this suite is deterministic and offline.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
from datetime import date

_src = pathlib.Path(__file__).with_name("roadmap-index.py")
_spec = importlib.util.spec_from_file_location("roadmap_index", _src)
ri = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ri)

FAILURES: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        FAILURES.append(msg)


def eq(actual: object, expected: object, msg: str) -> None:
    check(actual == expected, f"{msg}\n  expected: {expected!r}\n  actual:   {actual!r}")


# --------------------------------------------------------------------------- #
# coverage_count
# --------------------------------------------------------------------------- #

def test_coverage_count():
    rows = [("a", "main", True), ("b", "main", False), ("c", "dev", True)]
    eq(ri.coverage_count(rows), (2, 3), "coverage_count counts yes/total")
    eq(ri.coverage_count([]), (0, 0), "coverage_count empty")


# --------------------------------------------------------------------------- #
# render_table
# --------------------------------------------------------------------------- #

def test_render_table():
    rows = [("Tavern", "main", True), ("hive", "v4", False)]
    expected = (
        ri.TABLE_HEADER
        + "\n"
        + ri.TABLE_SEP
        + "\n"
        + "| Tavern | main | ✅ |"
        + "\n"
        + "| hive | v4 | ❌ |"
    )
    eq(ri.render_table(rows), expected, "render_table header/sep/cells")

    ordered = ri.render_table([("zeta", "main", True), ("alpha", "main", True)])
    check(ordered.index("zeta") < ordered.index("alpha"),
          "render_table preserves given row order")


# --------------------------------------------------------------------------- #
# _replace_table_region
# --------------------------------------------------------------------------- #

_DOC = """# Title

Some preamble.

## Coverage: 1 / 2 active repos

The one repo without a roadmap:

- `hive` — active, default branch `v4`.

| Repo | Default branch | ROADMAP.md? |
|---|---|---|
| Tavern | main | ✅ |
| hive | v4 | ❌ |

## A note

body
"""


def test_replace_table_region():
    out = ri._replace_table_region(_DOC, [("Tavern", "main", True), ("hive", "v4", True)])
    check("Some preamble." in out, "preamble preserved")
    check("## Coverage: 1 / 2 active repos" in out, "count heading preserved")
    check("- `hive` — active, default branch `v4`." in out, "prose bullets preserved")
    check("## A note" in out, "following section preserved")
    check("| hive | v4 | ✅ |" in out, "hive row flipped to yes")
    check("| hive | v4 | ❌ |" not in out, "old hive row gone")
    eq(out.count(ri.TABLE_HEADER), 1, "exactly one table block remains")


def test_replace_table_region_adds_repo():
    out = ri._replace_table_region(
        _DOC, [("Tavern", "main", True), ("hive", "v4", False), ("spindle", "main", False)]
    )
    check("| spindle | main | ❌ |" in out, "new repo row added")
    eq(out.count(ri.TABLE_HEADER), 1, "still exactly one table block")


def test_replace_table_region_missing_appends():
    out = ri._replace_table_region("# Title\n\nno table here\n", [("a", "main", True)])
    check(ri.TABLE_HEADER in out, "table appended when none present")
    check("| a | main | ✅ |" in out, "appended row present")


# --------------------------------------------------------------------------- #
# apply_updates
# --------------------------------------------------------------------------- #

_APPLY_DOC = """# Org-wide ROADMAP inventory

**Last verified**: 2026-09-02 · **Source**: some source, currently **40** repositories.

## Coverage: 36 / 40 active repos

| Repo | Default branch | ROADMAP.md? |
|---|---|---|
| Tavern | main | ✅ |
| hive | v4 | ❌ |

## A note
"""


def test_apply_updates():
    out = ri.apply_updates(
        _APPLY_DOC,
        [("Tavern", "main", True), ("hive", "v4", True), ("spindle", "main", False)],
        date(2026, 10, 8),
    )
    check("**Last verified**: 2026-10-08" in out, "date updated")
    check("## Coverage: 2 / 3 active repos" in out, "count heading updated")
    check("| hive | v4 | ✅ |" in out, "table row flipped")
    check("| spindle | main | ❌ |" in out, "new row in table")
    check("currently **40** repositories" in out,
          "unrelated bold number in prose is not rewritten")
    check("2026-09-02" not in out, "old date fully replaced")


# --------------------------------------------------------------------------- #
# regenerate  (source + rows -> new_text, changed)
# --------------------------------------------------------------------------- #

_REGEN_DOC = """**Last verified**: 2026-09-02

## Coverage: 1 / 2 active repos

| Repo | Default branch | ROADMAP.md? |
|---|---|---|
| Tavern | main | ✅ |
| hive | v4 | ❌ |
"""


def test_regenerate_drift():
    new_text, changed = ri.regenerate(
        _REGEN_DOC, [("Tavern", "main", True), ("hive", "v4", True)], date(2026, 10, 8)
    )
    check(changed, "drift reported when rows change")
    check("2026-10-08" in new_text, "new date present")


def test_regenerate_no_drift():
    rows = [("Tavern", "main", True), ("hive", "v4", False)]
    new_text, changed = ri.regenerate(_REGEN_DOC, rows, date(2026, 9, 2))
    check(not changed, "no change when rows and date are unchanged")
    eq(new_text, _REGEN_DOC, "document byte-identical when nothing changed")


# --------------------------------------------------------------------------- #
# collect_rows with the network layer stubbed
# --------------------------------------------------------------------------- #

def test_collect_rows_skips_unreadable():
    def branch_of(repo, env=None):
        return None if repo == "gone" else "main"

    def roadmap_of(repo, branch, env=None):
        return repo != "b"

    rows = ri.collect_rows(
        active=lambda: ["a", "gone", "b"],
        branch_of=branch_of,
        roadmap_of=roadmap_of,
    )
    eq(rows, [("a", "main", True), ("b", "main", False)], "unreadable repo skipped")


def main() -> int:
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    if FAILURES:
        print(f"FAILED ({len(FAILURES)} check(s)):")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
