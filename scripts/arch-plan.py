#!/usr/bin/env python3
"""Plan the architectures a publish-flatpak.yml run covers.

Single source of truth for the `archs` input of the reusable
`.github/workflows/publish-flatpak.yml`. Before this script existed, that
workflow parsed `inputs.archs` three independent times: once for the build
matrix, once for the registry-copy loop, and once more hard-coded in the
artifact-download and central-index steps, which only ever knew about
`x86_64` and `aarch64`. A syntactically valid but unsupported architecture --
a new arm64 variant, or a typo like `arm64` -- could therefore enter the
matrix and the registry loop with no matching download or index step, and the
run would publish architecture-qualified image tags with no index metadata: a
release whose registry and central catalog disagree.

`plan()` is the whole contract. It validates the list against the supported
enum, rejects duplicates and empty lists, selects an explicit primary, and
emits the normalized matrix the build, download, registry-copy and index-update
steps all consume. The workflow's preflight job runs it and fails before any
build starts; every downstream step reads the plan back from that job's
outputs, so there is now one place the architecture list is interpreted.

Usage:
    arch-plan.py                       # reads $ARCHS_INPUT (default: inputs.archs)
    ARCHS_INPUT='["x86_64"]' arch-plan.py
    arch-plan.py '["x86_64","aarch64"]'

Exit codes:
    0  plan produced (printed to stdout; also written to $GITHUB_OUTPUT when set)
    1  the architecture list is invalid (message on stderr)
"""

from __future__ import annotations

import json
import os
import sys

# The exact set of architectures the pipeline can publish for. This is the
# public contract of publish-flatpak.yml's `archs` input: anything outside it
# has no runner, no download step, and no index step, so it must be rejected
# rather than silently half-published.
SUPPORTED_ARCHS = ("x86_64", "aarch64")

# Runner for each supported arch. Kept next to the enum so a third architecture
# can only ever reach a build if someone also gives it a runner -- an arch
# without a runner entry now fails the plan loudly instead of silently landing
# on the x86_64 runner (the old `arch != 'aarch64' && ubuntu-24.04` default).
RUNNERS = {
    "x86_64": "ubuntu-24.04",
    "aarch64": "ubuntu-24.04-arm",
}

# Preferred primary for the unsuffixed `latest` tag. `latest` has no arch
# suffix and so can only track one architecture; defaulting to x86_64 makes
# that choice explicit and independent of list order. A caller that builds only
# aarch64 still gets aarch64 as primary (the fallthrough in plan()).
PREFERRED_PRIMARY = "x86_64"


def plan(archs):
    """Validate an architecture list and return the normalized plan.

    `archs` is the parsed JSON value of the input (a list of strings). Returns
    a dict with keys:

        matrix   the validated, de-duplicated list, in the caller's order
        primary  the explicit architecture the unsuffixed `latest` tag tracks
        runners  {arch: runner} for every arch in the matrix
        count    len(matrix)

    Raises ValueError with a human-readable message on the first problem found:
    a non-list input, an empty list, a value outside SUPPORTED_ARCHS (a
    misspelling or an unsupported/future arch), or a duplicate.
    """
    if not isinstance(archs, list):
        raise ValueError("archs must be a JSON array of architecture names")
    if not archs:
        raise ValueError("archs must contain at least one architecture")

    seen = set()
    matrix = []
    for arch in archs:
        if not isinstance(arch, str):
            raise ValueError(f"arch entries must be strings, got {arch!r}")
        if arch not in RUNNERS:
            raise ValueError(
                f"unsupported architecture {arch!r}: "
                f"supported values are {', '.join(SUPPORTED_ARCHS)}"
            )
        if arch in seen:
            raise ValueError(f"duplicate architecture {arch!r} in archs")
        seen.add(arch)
        matrix.append(arch)

    # Explicit primary, decoupled from list order: prefer x86_64, otherwise the
    # first supported arch present (which, with the enum above, is aarch64 when
    # x86_64 is absent). This is what stops `["aarch64","x86_64"]` from
    # reassigning the meaning of `latest`.
    primary = next((a for a in ("x86_64", *matrix) if a in seen), matrix[0])

    return {
        "matrix": matrix,
        "primary": primary,
        "runners": {a: RUNNERS[a] for a in matrix},
        "count": len(matrix),
    }


def _emit_outputs(plan_out):
    """Write the plan to $GITHUB_OUTPUT for the workflow's downstream jobs.

    Single-line `key=value` pairs so the values round-trip through
    `fromJSON()` in the build/publish jobs without a heredoc.
    """
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    matrix = json.dumps(plan_out["matrix"], separators=(",", ":"))
    runners = json.dumps(plan_out["runners"], separators=(",", ":"))
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(f"matrix={matrix}\n")
        fh.write(f"primary={plan_out['primary']}\n")
        fh.write(f"runners={runners}\n")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv:
        raw = argv[0]
    else:
        raw = os.environ.get("ARCHS_INPUT", os.environ.get("archs", "[]"))

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"ERROR: archs is not valid JSON: {exc}", file=sys.stderr)
        return 1

    try:
        plan_out = plan(parsed)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(plan_out, separators=(",", ":")))
    _emit_outputs(plan_out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
