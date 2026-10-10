#!/usr/bin/env python3
"""Pin the boundary enforced by check-action-pins.py.

The checker is a supply-chain gate for tuna-os/.github#175: every external
`uses:` reference must be a 40-char commit SHA. This pins that line -- a real
SHA passes, every tag and branch ref fails, local path references are exempt,
and a missing ref is caught. Plain python3, no test framework, matches how
scripts/ is already run in CI.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

_SRC = pathlib.Path(__file__).with_name("check-action-pins.py")
_SPEC = importlib.util.spec_from_file_location("check_action_pins", _SRC)
policy = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(policy)

SHA = "3d3c42e5aac5ba805825da76410c181273ba90b1"
OTHER = "2ebcf16054461267868620b1414507f3ccc765c1"

# (name, workflow text, expect_violation)
CASES: list[tuple[str, str, bool]] = [
    (
        "full SHA passes",
        f"- uses: actions/checkout@{SHA}\n",
        False,
    ),
    (
        "full SHA with human comment passes",
        f"- uses: actions/setup-python@{OTHER} # v7.0.0\n",
        False,
    ),
    (
        "major version tag fails",
        "- uses: actions/checkout@v7\n",
        True,
    ),
    (
        "minor version tag fails",
        "- uses: flatpak/flatpak-github-actions/flatpak-builder@v6.8\n",
        True,
    ),
    (
        "branch ref on cross-repo action fails",
        "- uses: tuna-os/.github/.github/actions/ste-lint@main\n",
        True,
    ),
    (
        "stable/latest alias fails",
        "- uses: some/action@stable\n",
        True,
    ),
    (
        "missing ref falls back to default branch",
        "- uses: actions/checkout\n",
        True,
    ),
    (
        "local path reference is exempt",
        "- uses: ./.github/actions/ste-lint@main\n",
        False,
    ),
    (
        "relative local path is exempt",
        "uses: .github/actions/foo\n",
        False,
    ),
    (
        "mixed file: one pinned, one tagged",
        (
            "- uses: actions/checkout@{sha}\n"
            "- uses: actions/upload-artifact@v7\n"
            "- uses: actions/download-artifact@{sha2}\n"
        ).format(sha=SHA, sha2=OTHER),
        True,
    ),
    (
        "commented-out uses is ignored",
        f"# - uses: actions/checkout@v7\n- uses: actions/checkout@{SHA}\n",
        False,
    ),
    (
        "expression uses is skipped",
        "- uses: ${{ inputs.myAction }}\n",
        False,
    ),
]


def main() -> int:
    failures = []
    for name, text, expect_violation in CASES:
        got = policy.check_text(text, "<test>")
        if bool(got) != expect_violation:
            failures.append(
                f"  - {name}\n      expected {'a violation' if expect_violation else 'none'}, "
                f"got {got or 'none'}"
            )

    if failures:
        print("FAIL: action-pin checker regressed:", file=sys.stderr)
        print("\n".join(failures), file=sys.stderr)
        return 1

    print(f"OK: {len(CASES)} cases behave as pinned.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
