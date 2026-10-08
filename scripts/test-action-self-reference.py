#!/usr/bin/env python3
"""Pin the boundary enforced by check-action-self-reference.py.

The gate forbids a repo from resolving its own actions from a mutable ref.
That line -- self-references must pin to a 40-char hex SHA, everything else is
allowed -- is exactly the kind of rule that erodes by a quiet edit, so cases
are pinned here: a SHA passes, a branch/tag/no-ref fails, and a third-party
action at @main stays allowed (the hazard is self-references only).

Plain python3, no test framework -- matches how scripts/ is already run in CI
(renovate-policy-check.yml), and imports the checker the same way the check
workflow runs it.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import tempfile

_src = pathlib.Path(__file__).with_name("check-action-self-reference.py")
_spec = importlib.util.spec_from_file_location("policy", _src)
policy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(policy)

SHA = "da0153d94472c0e645f69820b3bae57487be3c43"
SELF = "tuna-os/.github/.github/actions/ste-lint"


def self_step(uses):
    """A workflow step that resolves one of this repo's own actions."""
    return {"jobs": {"j": {"steps": [{"uses": uses}]}}}


def action_step(uses):
    """A composite-action step (runs.steps) resolving one action."""
    return {"runs": {"using": "composite", "steps": [{"uses": uses}]}}


# (name, parsed YAML document, expects a violation)
CASES: list[tuple[str, object, bool]] = [
    # A self-reference pinned to a full SHA is the one thing that is allowed.
    ("self-reference pinned to SHA passes", self_step(f"{SELF}@{SHA}"), False),
    # The exact anti-pattern #84 reports: a self-reference at @main.
    ("self-reference at @main fails", self_step(f"{SELF}@main"), True),
    # Any other branch name is equally mutable; not just main.
    ("self-reference at @master fails", self_step(f"{SELF}@master"), True),
    # A tag is still movable, so it does not count as an immutable revision.
    ("self-reference at a tag fails", self_step(f"{SELF}@v1.2.3"), True),
    # No @ref at all resolves to the default branch -- still mutable.
    ("self-reference with no @ref fails", self_step(SELF), True),
    # A third-party action at @main is left to Renovate -- not a self-reference.
    ("third-party action at @main is allowed", self_step("actions/checkout@main"), False),
    # find_uses must reach a nested action step (runs.steps), not just a
    # workflow step -- a composite action calling a sibling action at @main.
    (
        "nested action-steps self-reference at @main fails",
        action_step(f"{SELF}@main"),
        True,
    ),
    # A 39-char hex ref is not a real SHA and must be rejected.
    ("short hex ref fails", self_step(f"{SELF}@{SHA[:39]}"), True),
    # Uppercase hex is not a valid lowercase commit SHA.
    ("uppercase hex ref fails", self_step(f"{SELF}@{SHA.upper()}"), True),
    # A document carrying only third-party actions is compliant.
    (
        "only third-party actions pass",
        {
            "jobs": {
                "j": {
                    "steps": [
                        {"uses": "actions/checkout@v7"},
                        {"uses": "flatpak/flatpak-github-actions/"
                                 "flatpak-builder@v6.8"},
                    ]
                }
            }
        },
        False,
    ),
]


def check_files_with(tmpdir, name, text, expects_violation):
    """Drive check_files over one real file to cover the read + parse path."""
    path = pathlib.Path(tmpdir) / name
    path.write_text(text)
    return bool(policy.check_files([str(path)])) == expects_violation


def main() -> int:
    failures: list[str] = []
    for name, doc, expects_violation in CASES:
        got = bool(policy.check_doc(doc))
        if got != expects_violation:
            failures.append(
                f"{name}: expected violation={expects_violation} "
                f"got violation={got}"
            )

    # check_files must surface a parse error as a violation, not swallow it,
    # and must treat a clean file as compliant.
    with tempfile.TemporaryDirectory() as tmpdir:
        if not check_files_with(tmpdir, "broken.yml", "jobs: [", True):
            failures.append("check_files: broken YAML should be a violation")
        if not check_files_with(
            tmpdir, "ok.yml", "jobs:\n  j:\n    steps:\n      - uses: actions/checkout@v7\n", False
        ):
            failures.append("check_files: a clean file must not violate")

    if failures:
        print("test-action-self-reference FAILED:")
        for message in failures:
            print(f"  {message}")
        return 1
    print(f"OK: {len(CASES)} check_doc cases + 2 check_files cases pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
