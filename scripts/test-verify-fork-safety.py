#!/usr/bin/env python3
"""Unit tests for the extracted fork-safety verifier.

These lock the behaviour that used to be untestable inside the reusable
workflow's YAML heredoc: trigger parsing, which workflows fire on pull_request,
and the fork-guard logic (write-action detection, secret-reference detection,
and the set of text that marks a step/job as fork-aware). Each case is a
workflows fixture run through :func:`verify_fork_safety.check`; several also
assert the individual helpers directly.

Run directly:
    python3 test-verify-fork-safety.py

Exit codes:
    0  all cases passed
    1  one or more cases failed
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "verify_fork_safety", HERE / "verify-fork-safety.py"
)
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)

# Fork-safety check() keys workflows by basename, so fixtures map name -> doc.
def wfmap(*pairs: tuple[str, dict]) -> dict[str, dict]:
    return dict(pairs)


def wf(name: str, on, jobs: dict) -> dict:
    return {"name": name, "on": on, "jobs": jobs}


def step(name: str, run: str = "", if_: str | None = None, continue_on_error: bool | None = None, **kw) -> dict:
    s = {"name": name, "run": run}
    if if_ is not None:
        s["if"] = if_
    if continue_on_error is not None:
        s["continue-on-error"] = continue_on_error
    s.update(kw)
    return s


CASES: list[tuple[str, dict[str, dict], bool]] = [
    # (name, workflows, expect_violation)

    (
        "a PR workflow with top permissions and a read-only step is compliant",
        wfmap(
            (
                "safe.yml",
                wf(
                    "safe.yml",
                    {"pull_request": None},
                    {"ci": {"permissions": "read-all", "steps": [step("hi", run="echo hi")]}},
                ),
            )
        ),
        False,
    ),

    (
        "a PR workflow missing top-level permissions, with an unscoped job, is a violation",
        wfmap(
            (
                "noperm.yml",
                wf(
                    "noperm.yml",
                    {"pull_request": None},
                    {"build": {"runs-on": "ubuntu-latest", "steps": [step("hi")]}},
                ),
            )
        ),
        True,
    ),

    (
        "a PR workflow that uses pull_request_target is a violation",
        wfmap(
            (
                "prty.yml",
                wf("prty.yml", {"pull_request": None, "pull_request_target": None}, {"b": {"permissions": "read-all"}}),
            )
        ),
        True,
    ),

    (
        "a PR workflow with an unguarded write action is a violation",
        wfmap(
            (
                "ug.yml",
                wf(
                    "ug.yml",
                    {"pull_request": None},
                    {"build": {"permissions": "read-all", "steps": [step("c", run="gh pr comment 1 --body x")]}},
                ),
            )
        ),
        True,
    ),

    (
        "a write action guarded by a job-level fork guard is allowed",
        wfmap(
            (
                "gw.yml",
                wf(
                    "gw.yml",
                    {"pull_request": None},
                    {
                        "build": {
                            "permissions": "read-all",
                            "if": "github.event_name != 'pull_request'",
                            "steps": [step("c", run="gh pr comment 1 --body x")],
                        }
                    },
                ),
            )
        ),
        False,
    ),

    (
        "a PR workflow with an unguarded secret reference is a violation",
        wfmap(
            (
                "sec.yml",
                wf(
                    "sec.yml",
                    {"pull_request": None},
                    {"build": {"permissions": "read-all", "steps": [step("use", run="echo ${{ secrets.MY_TOKEN }}")]}},
                ),
            )
        ),
        True,
    ),

    (
        "a secret reference guarded by a step-level fork guard is allowed",
        wfmap(
            (
                "secg.yml",
                wf(
                    "secg.yml",
                    {"pull_request": None},
                    {
                        "build": {
                            "permissions": "read-all",
                            "steps": [
                                step(
                                    "use",
                                    run="echo ${{ secrets.MY_TOKEN }}",
                                    if_="github.event_name != 'pull_request'",
                                )
                            ],
                        }
                    },
                ),
            )
        ),
        False,
    ),

    (
        "referencing GITHUB_TOKEN is not a leak (it is populated even from a fork)",
        wfmap(
            (
                "gt.yml",
                wf(
                    "gt.yml",
                    {"pull_request": None},
                    {"build": {"permissions": "read-all", "steps": [step("use", run="echo ${{ secrets.GITHUB_TOKEN }}")]}},
                ),
            )
        ),
        False,
    ),

    (
        "a non-PR workflow with an unguarded write is not scanned (no violation)",
        wfmap(
            (
                "push.yml",
                wf(
                    "push.yml",
                    {"push": None},
                    {"build": {"steps": [step("c", run="gh pr comment 1 --body x")]}},
                ),
            )
        ),
        False,
    ),

    (
        "a continue-on-error step that writes is allowed (the gate never fails anyway)",
        wfmap(
            (
                "coe.yml",
                wf(
                    "coe.yml",
                    {"pull_request": None},
                    {
                        "build": {
                            "permissions": "read-all",
                            "steps": [step("c", run="gh pr comment 1 --body x", continue_on_error=True)],
                        }
                    },
                ),
            )
        ),
        False,
    ),

    (
        "a write guarded by a preflight step output reference is allowed",
        wfmap(
            (
                "pref.yml",
                wf(
                    "pref.yml",
                    {"pull_request": None},
                    {
                        "build": {
                            "permissions": "read-all",
                            "steps": [
                                step("probe", run="echo id=ok", id="probe", if_="github.event_name != 'pull_request'"),
                                step(
                                    "c",
                                    run="gh pr comment ${{ steps.probe.outputs.id }}",
                                    if_="steps.probe.outputs.id == 'ok'",
                                ),
                            ],
                        }
                    },
                ),
            )
        ),
        False,
    ),
]


def test_get_triggers_parsing() -> None:
    assert verifier.get_triggers({"on": "pull_request"}) == {"pull_request": None}
    assert verifier.get_triggers({"on": ["push", "pull_request"]}) == {
        "push": None,
        "pull_request": None,
    }
    assert verifier.get_triggers({True: "pull_request"}) == {"pull_request": None}


def test_pr_workflow_names_only_pr() -> None:
    flows = wfmap(
        ("a.yml", wf("a.yml", {"push": None}, {})),
        ("b.yml", wf("b.yml", {"pull_request": None}, {})),
        ("c.yml", wf("c.yml", {"pull_request_target": None}, {})),
    )
    # pull_request_target is a different trigger and must not be counted here.
    assert verifier.pr_workflow_names(flows) == ["b.yml"]


def test_is_fork_aware_matches_every_guard() -> None:
    for guard in verifier.FORK_GUARDS:
        assert verifier.is_fork_aware(f"if: {guard}"), f"guard not recognised: {guard}"
    assert verifier.is_fork_aware("if: always()") is False


def test_write_actions_regex() -> None:
    for text in [
        "git push",
        "gh pr comment 1",
        "gh pr create",
        "gh pr review",
        "gh pr merge",
        "gh issue comment 1",
        "gh api /repos/x/y --method POST",
        "gh api /repos/x/y -X PUT",
        "gh release create v1",
        "actions/github-script",
    ]:
        assert verifier.WRITE_ACTIONS.search(text), f"missed: {text}"
    for text in [
        "gh pr view 1",
        "gh api /repos/x/y",
        "reading a file",
    ]:
        assert not verifier.WRITE_ACTIONS.search(text), f"false positive: {text}"


def test_secret_ref_regex() -> None:
    assert verifier.SECRET_REF.search("echo ${{ secrets.MY_TOKEN }}").group(1) == "MY_TOKEN"
    assert verifier.SECRET_REF.search("echo ${{ secrets.GITHUB_TOKEN }}") is None
    assert not verifier.SECRET_REF.search("echo ${{ github.token }}")


def main() -> int:
    failures: list[str] = []

    for name, flows, expect_violation in CASES:
        got = bool(verifier.check(flows))
        if got != expect_violation:
            failures.append(
                f"  - {name}\n"
                f"      expected {'a violation' if expect_violation else 'no violation'}, "
                f"got {verifier.check(flows) or 'none'}"
            )

    try:
        test_get_triggers_parsing()
        test_pr_workflow_names_only_pr()
        test_is_fork_aware_matches_every_guard()
        test_write_actions_regex()
        test_secret_ref_regex()
    except AssertionError as e:
        failures.append(f"  - direct unit test failed: {e}")

    if failures:
        print("FAIL: fork-safety verifier regressed:", file=sys.stderr)
        print("\n".join(failures), file=sys.stderr)
        return 1

    print(
        f"OK: {len(CASES)} policy cases + 5 unit tests pass; "
        "write-action detection and fork guards behave as pinned."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
