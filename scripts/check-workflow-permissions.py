#!/usr/bin/env python3
"""Check that every GitHub Actions workflow declares a top-level permissions block.

tuna-os/.github#155: a workflow with no top-level `permissions:` block inherits
the repository's configured default token scope, which is almost always broader
than the jobs actually need. This script flags those workflows so the least
privilege baseline is enforced in CI.

It is intentionally dependency-free: it parses just enough YAML structure
(top-level mapping keys and their indentation) to answer one question -- does
this file declare a non-empty `permissions:` mapping at the top level? -- so it
runs on GitHub's ubuntu runners without a `pip install` step.

Usage:
    python3 check-workflow-permissions.py .github/workflows [--json] [--quiet]

Exit code is 0 when every workflow is compliant, 1 otherwise.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

TOP_LEVEL_KEY = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*):\s*(.*)$")
DOC_SEPARATOR = re.compile(r"^---\s*$")


def _iter_documents(text):
    """Split a YAML stream into document bodies on top-level --- / ... separators."""
    current = []
    for line in text.splitlines():
        if DOC_SEPARATOR.match(line):
            yield "\n".join(current)
            current = []
        else:
            current.append(line)
    yield "\n".join(current)


def _has_top_level_permissions(document):
    """Return True if `document` declares a non-empty top-level `permissions:` block.

    "Non-empty" means the key exists and has at least one child scope entry
    (an indented, non-comment line). A key present only as a comment, or with an
    empty mapping, does not count -- that still inherits the default scope.
    """
    in_permissions = False
    has_child = False
    for raw in document.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            # Blank or comment: neither a child scope nor a block terminator.
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        if indent == 0:
            match = TOP_LEVEL_KEY.match(raw)
            if match is None:
                continue
            if in_permissions:
                # A new top-level key ended the permissions block.
                return has_child
            if match.group(1) == "permissions":
                in_permissions = True
                inline = match.group(2).strip()
                # An inline scalar value (e.g. "permissions: read") declares
                # intent; an inline empty map (permissions: {}) does not.
                has_child = bool(inline) and inline != "{}"
            continue
        # indent > 0: a child line inside the permissions block.
        if in_permissions:
            has_child = True
    return has_child


def check_file(path):
    """Return a list of violation strings for one workflow file."""
    violations = []
    text = path.read_text(encoding="utf-8")
    for document in _iter_documents(text):
        if not _has_top_level_permissions(document):
            violations.append(f"{path}: missing top-level `permissions:` block")
    return violations


def find_workflow_files(directory):
    """Return the .yml and .yaml files directly inside `directory`, sorted."""
    if not directory.is_dir():
        return [f"{directory}: no such directory"]

    files = sorted(list(directory.glob("*.yml")) + list(directory.glob("*.yaml")))
    return files


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Flag workflows missing a top-level `permissions:` block."
    )
    parser.add_argument(
        "directory",
        type=Path,
        help="Directory to scan for workflow files (e.g. .github/workflows).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of human-readable text.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Emit no output; exit code alone reports the result.",
    )
    args = parser.parse_args(argv)

    violations = []
    for path in find_workflow_files(args.directory):
        violations.extend(check_file(path))

    if args.json:
        print(json.dumps({"violations": violations}))
        return 1 if violations else 0

    if not args.quiet:
        if violations:
            print(
                "❌ {} workflow(s) missing an explicit top-level permissions block:".format(
                    len(violations)
                )
            )
            for violation in violations:
                print(f"  • {violation}")
            print()
            print("Add a top-level `permissions:` block declaring the least privilege")
            print("each workflow needs, e.g.:")
            print("  permissions:")
            print("    contents: read")
        else:
            print("✅ All workflows declare an explicit top-level permissions block.")

    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
