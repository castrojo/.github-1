#!/usr/bin/env python3
"""Pin the boundary enforced by check-renovate-automerge-policy.py.

The checker is a security gate, and its blocked set was narrowed from
{major, minor} to {major} when the fleet moved to automerged minor bumps.
That is exactly the kind of loosening that erodes further by accident, so the
line is pinned here: minor must pass, major must fail, and the scoping rules
that stop a narrow override from cancelling a broad bypass must still hold.

Plain python3, no test framework -- matches how scripts/ is already run in CI.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

_src = pathlib.Path(__file__).with_name("check-renovate-automerge-policy.py")
_spec = importlib.util.spec_from_file_location("policy", _src)
policy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(policy)

CASES: list[tuple[str, dict, bool]] = [
    # (name, config, expect_violation)
    (
        "minor+patch automerge is allowed (the whole point of the change)",
        {"packageRules": [{"matchUpdateTypes": ["minor", "patch", "pin", "pinDigest", "digest"], "automerge": True}]},
        False,
    ),
    (
        "explicit major automerge is still blocked",
        {"packageRules": [{"matchUpdateTypes": ["major"], "automerge": True}]},
        True,
    ),
    (
        "top-level automerge:true is still blocked (covers major)",
        {"automerge": True},
        True,
    ),
    (
        "a rule with no matchUpdateTypes applies to major, so it is blocked",
        {"packageRules": [{"automerge": True}]},
        True,
    ),
    (
        "explicit major:false alongside minor:true is compliant",
        {
            "packageRules": [
                {"matchUpdateTypes": ["minor", "patch"], "automerge": True},
                {"matchUpdateTypes": ["major"], "automerge": False},
            ]
        },
        False,
    ),
    (
        "a package-scoped major automerge is still caught",
        {"packageRules": [{"matchPackageNames": ["left-pad"], "matchUpdateTypes": ["major"], "automerge": True}]},
        True,
    ),
    (
        "a narrow major:false must NOT cancel an earlier broad bypass (protota regression)",
        {
            "packageRules": [
                {"automerge": True},
                {"matchDatasources": ["docker"], "matchUpdateTypes": ["major"], "automerge": False},
            ]
        },
        True,
    ),
    (
        "minor automerge scoped to one package is allowed",
        {"packageRules": [{"matchPackageNames": ["serde"], "matchUpdateTypes": ["minor"], "automerge": True}]},
        False,
    ),
]


def main() -> int:
    failures = []
    for name, config, expect_violation in CASES:
        got = policy.check(config)
        if bool(got) != expect_violation:
            failures.append(
                f"  - {name}\n      expected {'a violation' if expect_violation else 'no violation'}, got {got or 'none'}"
            )

    # The shipped preset every repo extends must itself be compliant.
    import json

    preset = json.loads((pathlib.Path(__file__).parents[1] / "default.json").read_text(encoding="utf-8"))
    if policy.check(preset):
        failures.append(f"  - default.json (the shared preset) violates the policy: {policy.check(preset)}")

    # project-starter/scripts/check-renovate-automerge-policy.py must stay
    # synchronized byte-for-byte with the canonical root copy (tuna-os/.github#34).
    root_checker = _src.read_bytes()
    starter_checker_path = pathlib.Path(__file__).parents[1] / "project-starter" / "scripts" / "check-renovate-automerge-policy.py"
    if not starter_checker_path.exists():
        failures.append(f"  - {starter_checker_path} is missing")
    elif starter_checker_path.read_bytes() != root_checker:
        failures.append(
            f"  - {starter_checker_path} has drifted from canonical {_src} (must match byte-for-byte)"
        )

    if failures:
        print("FAIL: renovate automerge policy checker regressed:", file=sys.stderr)
        print("\n".join(failures), file=sys.stderr)
        return 1
    print(f"OK: {len(CASES)} policy cases + default.json behave as pinned.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
