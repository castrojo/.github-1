#!/usr/bin/env python3
"""Pin the contract enforced by arch-plan.py.

The reusable publish-flatpak.yml publishes image tags for whatever its callers
put in `archs`, but the download and central-index steps used to only know
about x86_64 and aarch64 -- so an unsupported or misspelled architecture could
publish a registry tag with no index entry. arch-plan.py is the single place
that interprets the list; this file pins that interpretation so the contract
cannot silently widen again: empty, duplicate, misspelled, and future
architectures must all fail, list order must not move the primary, and the
normalized matrix the build and publish jobs consume must be exactly the
validated input.

Plain python3, no test framework -- matches how scripts/ is already run in CI.
"""

from __future__ import annotations

import importlib.util
import pathlib

_src = pathlib.Path(__file__).with_name("arch-plan.py")
_spec = importlib.util.spec_from_file_location("arch_plan", _src)
arch_plan = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(arch_plan)


class _Error:
    """Sentinel meaning 'plan() must raise ValueError with this substring'."""

    __slots__ = ("needle",)

    def __init__(self, needle: str):
        self.needle = needle


# (name, input, expected)  -- expected is either an _Error or a full plan dict.
CASES: list[tuple[str, object, object]] = [
    # (name, config, expected)
    (
        "the shipped default: both supported architectures",
        ["x86_64", "aarch64"],
        {
            "matrix": ["x86_64", "aarch64"],
            "primary": "x86_64",
            "runners": {"x86_64": "ubuntu-24.04", "aarch64": "ubuntu-24.04-arm"},
            "count": 2,
        },
    ),
    (
        "empty list is rejected (nothing to publish)",
        [],
        _Error("at least one architecture"),
    ),
    (
        "a duplicate architecture is rejected",
        ["x86_64", "x86_64"],
        _Error("duplicate architecture 'x86_64'"),
    ),
    (
        "a misspelled architecture is rejected (the bypass this fixes)",
        ["x86_64", "arm64"],
        _Error("unsupported architecture 'arm64'"),
    ),
    (
        "a future/unknown architecture is rejected until it gets a runner",
        ["x86_64", "loongarch64"],
        _Error("unsupported architecture 'loongarch64'"),
    ),
    (
        "a non-string entry is rejected",
        ["x86_64", 1],
        _Error("arch entries must be strings"),
    ),
    (
        "a non-list JSON value is rejected",
        "x86_64",
        _Error("must be a JSON array"),
    ),
    (
        "aarch64-only builds publish for aarch64",
        ["aarch64"],
        {
            "matrix": ["aarch64"],
            "primary": "aarch64",
            "runners": {"aarch64": "ubuntu-24.04-arm"},
            "count": 1,
        },
    ),
    (
        "x86_64-only builds publish for x86_64",
        ["x86_64"],
        {
            "matrix": ["x86_64"],
            "primary": "x86_64",
            "runners": {"x86_64": "ubuntu-24.04"},
            "count": 1,
        },
    ),
]


def _run_plan_case(name, value, expected):
    try:
        got = arch_plan.plan(value)
    except ValueError as exc:
        if isinstance(expected, _Error):
            return None if expected.needle in str(exc) else (
                f"{name}: expected error containing {expected.needle!r}, "
                f"got {str(exc)!r}"
            )
        return f"{name}: expected error, got plan {got}"
    if isinstance(expected, _Error):
        return f"{name}: expected error {expected.needle!r}, got plan {got}"
    if got != expected:
        return f"{name}: plan {got} != expected {expected}"
    return None


def main() -> int:
    failures = []
    for name, value, expected in CASES:
        problem = _run_plan_case(name, value, expected)
        if problem:
            failures.append(problem)

    # The order-independence invariant the old code broke: `primary` is the
    # unsuffixed `latest` tag's architecture, and it must not move when a
    # caller reorders the list. x86_64 is preferred either way.
    forward = arch_plan.plan(["x86_64", "aarch64"])
    reversed_ = arch_plan.plan(["aarch64", "x86_64"])
    if forward["primary"] != "x86_64" or reversed_["primary"] != "x86_64":
        failures.append(
            "primary is not deterministically x86_64 for both orderings: "
            f"forward={forward['primary']}, reversed={reversed_['primary']}"
        )
    # And the matrix preserves the caller's order even though primary does not.
    if reversed_["matrix"] != ["aarch64", "x86_64"]:
        failures.append(
            f"reordered matrix not preserved: {reversed_['matrix']}"
        )

    # Every architecture the plan emits must have a runner -- an arch in the
    # matrix with no runner entry is exactly the silent-wrong-runner class of
    # bug this script guards against.
    for name, value, _ in CASES:
        try:
            got = arch_plan.plan(value)
        except ValueError:
            continue
        for arch in got["matrix"]:
            if arch not in got["runners"]:
                failures.append(f"{name}: arch {arch!r} in matrix has no runner")

    if failures:
        print("FAIL: arch-plan contract regressed:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"OK: {len(CASES)} contract cases + order-independence and runner checks pass.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
