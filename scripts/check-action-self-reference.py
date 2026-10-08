#!/usr/bin/env python3
"""Fail if a workflow or action in this repo resolves a nested action from a
mutable revision of this repo's own actions.

tuna-os/.github#84: the reusable workflows publish-flatpak.yml and ste-lint.yml
called tuna-os/.github/.github/actions/*@main -- a nested action from the same
repo pinned to a mutable branch. That splits one logical reusable interface
across two independently resolved revisions: a consumer pinned to a commit or
release still loads the nested action from the current default branch, and a
PR changing the composite action cannot exercise that change through the
reusable workflow before merge (the workflow keeps loading the old action from
main). publish-flatpak-index writes the central index with write access, so a
mixed-version run is not a theoretical reproducibility gap.

The rule is one line: any `uses:` of this repo's own actions
(tuna-os/.github/) must be pinned to a 40-character hex SHA. A SHA is the only
immutable reviewed revision this repo can offer -- it ships no tags or
releases, and a branch or tag can still move. Pinning to anything else
reproduces the exact coupling this check exists to forbid.

This is intentionally scoped to self-references only. Third-party actions
(actions/checkout@v7, flatpak/flatpak-github-actions/flatpak-builder@v6.8, ...)
are left to Renovate and their own version semantics; the mutability hazard
here is a repo calling its own actions from a branch it controls.

Usage:
    check-action-self-reference.py [path/to/file.yml ...]
    (no args) scans .github/workflows/*.yml and .github/actions/*/action.yml

Exit codes:
    0  compliant (no self-reference resolves from a mutable ref)
    1  a self-reference to a mutable ref was found (or a file could not parse)
"""

from __future__ import annotations

import pathlib
import re
import sys

import yaml

# The only repo whose actions this check must keep pinned. A `uses:` whose
# owner/repo matches this prefix is a self-reference, regardless of how deep
# the action path is (this repo nests actions under .github/actions/).
SELF_REPO = "tuna-os/.github/"

# The ref of a `uses:` must be a full 40-char hex SHA to count as immutable.
# A branch name (main, master, dev, ...) resolves to whatever HEAD is today;
# a tag can still be moved. Neither is a reviewed, fixed revision.
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def find_uses(node):
    """Yield every `uses:` string value nested anywhere in a parsed document.

    `uses:` lives in two shapes -- workflow steps
    (jobs.<job>.steps[].uses) and composite-action steps (runs.steps[].uses)
    -- so a structural walk finds both instead of assuming one location.
    """
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "uses" and isinstance(value, str):
                yield value
            yield from find_uses(value)
    elif isinstance(node, list):
        for item in node:
            yield from find_uses(item)


def split_ref(uses: str):
    """Split 'owner/repo/path@ref' into (path, ref).

    Returns (uses, None) when there is no '@': GitHub then falls back to the
    repo default branch, which is exactly the mutable-ref hazard we forbid.
    """
    if "@" not in uses:
        return uses, None
    path, _, ref = uses.rpartition("@")
    return path, ref


def check_doc(doc):
    """One violation string per offending self-reference in a parsed document.

    Pure over a parsed document -- no file I/O -- so the boundary this check
    holds can be pinned by a test without writing files to disk. The caller
    (check_files) supplies the file path for the message.
    """
    violations: list[str] = []
    if not isinstance(doc, dict):
        return violations
    for uses in find_uses(doc):
        repo_path, ref = split_ref(uses)
        if not repo_path.startswith(SELF_REPO):
            continue
        if ref is None:
            violations.append(
                f"{uses!r}: self-reference resolves from the default branch "
                "(no @ref)"
            )
        elif not SHA_RE.match(ref):
            violations.append(
                f"{uses!r}: self-reference pinned to mutable ref {ref!r}; pin "
                "to a 40-character hex SHA (tuna-os/.github#84)"
            )
    return violations


def check_files(paths):
    """Read each path and return the combined violations, each path-prefixed."""
    violations: list[str] = []
    for path in paths:
        try:
            doc = yaml.safe_load(pathlib.Path(path).read_text())
        except (OSError, yaml.YAMLError) as exc:
            # A file the gate cannot read is not compliant: hide a broken
            # workflow behind a parse error and you have not checked anything.
            violations.append(f"{path}: could not parse ({exc})")
            continue
        for violation in check_doc(doc):
            violations.append(f"{path}: {violation}")
    return violations


def default_paths():
    root = pathlib.Path(".")
    return sorted(
        {
            str(p)
            for p in {
                *root.glob(".github/workflows/*.yml"),
                *root.glob(".github/actions/*/action.yml"),
            }
        }
    )


def main() -> int:
    paths = sys.argv[1:] if len(sys.argv) > 1 else default_paths()
    violations = check_files(paths)
    if violations:
        print(
            "Self-references to tuna-os/.github must pin to an immutable SHA, "
            "not a mutable branch (tuna-os/.github#84):"
        )
        for message in violations:
            print(f"  {message}")
        return 1
    print(f"OK: {len(paths)} file(s) checked, no mutable self-references")
    return 0


if __name__ == "__main__":
    sys.exit(main())
