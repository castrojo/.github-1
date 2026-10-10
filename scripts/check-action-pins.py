#!/usr/bin/env python3
"""Fail if a repo's GitHub Actions are pinned to version tags instead of SHAs.

Org policy (tuna-os/.github#175): every external `uses:` reference in a workflow
must be pinned to a full 40-character commit SHA, never to a version tag
(`@v7`, `@v6.8`) or a branch ref (`@main`, `@stable`). A tag or branch is a
moving target an attacker can repoint -- by compromising the action maintainer,
by force-pushing a poisoned release, or by deleting and recreating the tag -- so
it gives no cryptographic guarantee about which code a pipeline is running. A
commit SHA is: once. It cannot be moved without a new SHA, which GitHub publishes.

This scans workflow YAML line by line (no PyYAML dependency, so it runs in any
caller's lint job the way the rest of reusable-lint.yml does). It looks at the
`uses:` key of every step and job-level `uses:` and checks the ref after `@`.

What counts as compliant:
  * `actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1` -- 40 hex chars.
  * the same ref with a trailing `# v7.0.1` human-readable comment.
  * a local path reference (`./.github/actions/foo`, `.github/actions/foo`) --
    these live in the repo being built and cannot be poisoned from outside, so
    the SHA rule does not apply to them.

What is flagged:
  * `actions/checkout@v7` -- version tag.
  * `flatpak/flatpak-github-actions/flatpak-builder@v6.8` -- version tag.
  * `tuna-os/.github/.github/actions/ste-lint@main` -- branch ref on a
    cross-repo action (branch drift risk, the same class of finding).
  * `actions/checkout` with no `@ref` at all -- GitHub falls back to the
    action's default branch, which is exactly the unpinned case.

Deliberately conservative, like check-renovate-automerge-policy.py: it never
silently misses a real unpinned reference by being too narrow. A value that is
not a 40-hex SHA is a violation, full stop -- even if the tag happens to point
at a SHA the author considers "safe" today. Pinning is not optional for a tag,
and a human reviewing the PR is the place to decide whether to keep it.

Usage:
    check-action-pins.py [path/to/workflows-dir | path/to/file.yml ...]
    (defaults to .github/workflows)

Exit codes:
    0  compliant (every external reference is a 40-char SHA)
    1  a reference was unpinned, or a file could not be read
"""

from __future__ import annotations

import pathlib
import re
import sys

SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
USES_RE = re.compile(r"^\s*(?:-\s+)?uses:\s*(?P<value>.+?)\s*$")
TEXT_FILES = (".yml", ".yaml")


def _clean_value(raw: str) -> str:
    """Reduce the text after `uses:` to the reference token, or "" if none.

    Strips a trailing inline YAML comment, surrounding quotes, and whitespace.
    Returns "" for blank values or `${{ ... }}` expressions, which cannot be
    judged statically.
    """
    value = raw.split("#", 1)[0].strip()
    value = value.strip('"').strip("'").strip()
    if not value or value.startswith("${{"):
        return ""
    return value


def check_text(text: str, path: str = "<input>") -> list[str]:
    """Return a list of human-readable violation strings, empty if compliant."""
    violations: list[str] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("#"):
            continue
        match = USES_RE.match(line)
        if not match:
            continue
        value = _clean_value(match.group("value"))
        if not value:
            continue
        # Local path references live in the repo being built; they are not an
        # external supply-chain ref and have no commit SHA to pin to.
        if value.startswith("."):
            continue
        if "@" not in value:
            violations.append(
                f"{path}:{lineno}: {value!r} has no @ref and falls back to the "
                "action's default branch"
            )
            continue
        ref = value.rpartition("@")[2]
        if not SHA_RE.match(ref):
            violations.append(
                f"{path}:{lineno}: {value!r} is pinned to {ref!r}, not a "
                "40-char commit SHA"
            )
    return violations


def check_file(path: pathlib.Path | str) -> list[str]:
    text = pathlib.Path(path).read_text(encoding="utf-8")
    return check_text(text, str(path))


def _iter_workflow_files(paths: list[str]) -> list[pathlib.Path]:
    files: list[pathlib.Path] = []
    for p in paths:
        pp = pathlib.Path(p)
        if pp.is_dir():
            files.extend(sorted(f for f in pp.rglob("*") if f.suffix in TEXT_FILES))
        else:
            files.append(pp)
    return files


def main() -> int:
    paths = sys.argv[1:] or [".github/workflows"]
    violations: list[str] = []
    for f in _iter_workflow_files(paths):
        try:
            violations.extend(check_file(f))
        except OSError as e:
            print(f"ERROR: could not read {f}: {e}", file=sys.stderr)
            return 1

    if violations:
        print(f"FAIL: {len(violations)} unpinned action reference(s):", file=sys.stderr)
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
        return 1

    print("OK: all external action references are pinned to 40-char commit SHAs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
