#!/usr/bin/env python3
"""Unit tests for the extracted CI-contract verifier.

These lock the behaviour that used to be untestable inside the reusable
workflow's YAML heredoc: trigger parsing, reusable-workflow reachability, and
the blocking-gate checks (hard-disabled job, continue-on-error). Each case is a
fixture pair (criteria + workflows) run through :func:`verify_ci_contract.check`;
a few also assert the individual helpers directly.

Run directly:
    python3 test-verify-ci-contract.py

Exit codes:
    0  all cases passed
    1  one or more cases failed
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "verify_ci_contract", HERE / "verify-ci-contract.py"
)
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)

# A workflow doc keyed both ways, exactly like load_workflows() would build it.
def wfmap(*pairs: tuple[str, dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for path, doc in pairs:
        name = path.split("/")[-1]
        out[path] = doc
        out[name] = doc
    return out


def wf(name: str, on, jobs: dict) -> tuple[str, dict]:
    return name, {"name": name, "on": on, "jobs": jobs}


def criteria(*items) -> list[dict]:
    return list(items)


def gate(workflow: str, jobs: dict | None = None, **criterion) -> dict:
    """Build a criterion; defaults to a minimal valid one."""
    c = {
        "id": criterion.get("id", "c"),
        "freshness_sla_days": criterion.get("freshness_sla_days", 7),
        "enforcement": criterion.get("enforcement", "blocking"),
        "asserted_by": criterion.get("asserted_by", "asserted by " + workflow),
        "gates": [{"workflow": workflow, "jobs": jobs or {}}],
    }
    return c


CASES: list[tuple[str, list[dict], dict[str, dict], bool]] = [
    # (name, criteria, workflows, expect_violation)

    (
        "a reachable gate whose job and verdict step exist is compliant",
        criteria(
            gate(
                "gate.yml",
                jobs={"ci": "verify"},
                enforcement="blocking",
            )
        ),
        wfmap(
            wf(
                "gate.yml",
                {"push": {"branches": ["main"]}},
                {"ci": {"steps": [{"name": "verify", "run": "echo hi"}]}},
            )
        ),
        False,
    ),

    (
        "a gate workflow that does not exist is a violation",
        criteria(gate("ghost.yml", jobs={})),
        wfmap(wf("other.yml", {"push": None}, {})),
        True,
    ),

    (
        "a gate workflow not named in asserted_by is a violation",
        criteria(gate("gate.yml", jobs={}, asserted_by="some other file")),
        wfmap(
            wf("gate.yml", {"push": None}, {"ci": {"steps": []}})
        ),
        True,
    ),

    (
        "a gate reachable only via workflow_dispatch (not an active trigger) is unreachable",
        criteria(gate("gate.yml", jobs={})),
        wfmap(
            wf("gate.yml", {"workflow_dispatch": None}, {"ci": {"steps": []}})
        ),
        True,
    ),

    (
        "a reusable workflow reachable through a caller chain counts as reachable",
        criteria(gate("gate.yml", jobs={})),
        wfmap(
            wf("gate.yml", {"workflow_call": None}, {"ci": {"steps": []}}),
            wf(
                "runner.yml",
                {"push": None},
                {
                    "build": {
                        "uses": "./gate.yml",
                        "steps": [{"name": "call", "run": "echo hi"}],
                    }
                },
            ),
        ),
        False,
    ),

    (
        "a blocking gate whose job has continue-on-error is a violation",
        criteria(gate("gate.yml", jobs={"ci": "verify"})),
        wfmap(
            wf(
                "gate.yml",
                {"push": None},
                {
                    "ci": {
                        "continue-on-error": True,
                        "steps": [{"name": "verify", "run": "echo hi"}],
                    }
                },
            )
        ),
        True,
    ),

    (
        "a non-blocking gate with continue-on-error is allowed (continue-on-error only bites blocking)",
        criteria(gate("gate.yml", jobs={"ci": "verify"}, enforcement="nonblocking")),
        wfmap(
            wf(
                "gate.yml",
                {"push": None},
                {
                    "ci": {
                        "continue-on-error": True,
                        "steps": [{"name": "verify", "run": "echo hi"}],
                    }
                },
            )
        ),
        False,
    ),

    (
        "a blocking gate with a hard-disabled job is a violation",
        criteria(gate("gate.yml", jobs={"ci": "verify"})),
        wfmap(
            wf(
                "gate.yml",
                {"push": None},
                {"ci": {"if": "false", "steps": [{"name": "verify", "run": "echo hi"}]}},
            )
        ),
        True,
    ),

    (
        "a gate whose job is missing is a violation",
        criteria(gate("gate.yml", jobs={"ci": "verify"})),
        wfmap(
            wf("gate.yml", {"push": None}, {"other": {"steps": [{"name": "verify", "run": "echo hi"}]}})
        ),
        True,
    ),

    (
        "a gate whose verdict step name is missing is a violation",
        criteria(gate("gate.yml", jobs={"ci": "verify"})),
        wfmap(
            wf(
                "gate.yml",
                {"push": None},
                {"ci": {"steps": [{"name": "not-verify", "run": "echo hi"}]}},
            )
        ),
        True,
    ),

    (
        "a criterion with asserted_by but no gates block is a violation",
        criteria({"id": "c", "enforcement": "blocking", "asserted_by": "something"}),
        wfmap(),
        True,
    ),

    (
        "a criterion with gates but no freshness_sla_days is a violation",
        criteria({"id": "c", "enforcement": "blocking", "asserted_by": "x", "gates": []}),
        wfmap(),
        True,
    ),

    (
        "a gate named by bare basename (no path) is still found",
        criteria(gate("gate.yml", jobs={})),
        wfmap(wf("gate.yml", {"push": None}, {"ci": {"steps": []}})),
        False,
    ),
]


def test_triggers_parsing() -> None:
    """triggers() must handle the three shapes YAML allows for `on`."""
    assert verifier.triggers({"on": "push"}) == {"push": None}
    assert verifier.triggers({"on": ["push", "pull_request"]}) == {
        "push": None,
        "pull_request": None,
    }
    assert set(verifier.triggers({"on": {"push": {"branches": ["main"]}}})) == {"push"}
    # unquoted `on:` is parsed by PyYAML as the boolean True key
    assert "pull_request" in verifier.triggers({True: "pull_request"})
    assert verifier.triggers({}) == {}


def test_is_reachable() -> None:
    """is_reachable() follows uses: edges and never loops on cycles."""
    reachable = wfmap(
        wf("gate.yml", {"workflow_call": None}, {}),
        wf("runner.yml", {"push": None}, {"b": {"uses": "./gate.yml"}}),
    )
    assert verifier.is_reachable("gate.yml", reachable) is True

    dispatched = wfmap(wf("gate.yml", {"workflow_dispatch": None}, {}))
    assert verifier.is_reachable("gate.yml", dispatched) is False

    missing = wfmap(wf("other.yml", {"push": None}, {}))
    assert verifier.is_reachable("ghost.yml", missing) is False

    cycle = wfmap(
        wf("a.yml", {"workflow_call": None}, {"b": {"uses": "./b.yml"}}),
        wf("b.yml", {"workflow_call": None}, {"a": {"uses": "./a.yml"}}),
    )
    # Neither is active, but the visited-set must stop the recursion, not hang.
    assert verifier.is_reachable("a.yml", cycle) is False


def test_callers_and_load_workflows() -> None:
    """callers() maps reusable workflows to their callers; load_workflows keys two ways."""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        wd = Path(td) / ".github" / "workflows"
        wd.mkdir(parents=True)
        (wd / "gate.yml").write_text(
            "name: gate\non: workflow_call\njobs:\n  ci:\n    runs-on: ubuntu-latest\n",
            encoding="utf-8",
        )
        (wd / "runner.yml").write_text(
            "name: runner\non: push\njobs:\n  b:\n    uses: ./gate.yml\n",
            encoding="utf-8",
        )
        docs = verifier.load_workflows(wd)
        # keyed by both the full path and the bare basename
        assert docs["gate.yml"] == docs[f"{wd}/gate.yml"]
        callers = verifier.callers(docs)
        assert "runner.yml" in callers["gate.yml"]


def test_main_exit_codes() -> None:
    """main() exit codes match the original workflow's sys.exit() values."""
    import contextlib
    import io
    import os
    import tempfile

    saved = dict(os.environ)
    try:
        # no criteria file -> skip, exit 0
        os.environ["CRITERIA_PATH"] = ".github/does-not-exist.yml"
        os.environ["WORKFLOWS_DIR"] = ".github/workflows"
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            assert verifier.main() == 0

        with tempfile.TemporaryDirectory() as td:
            criteria = Path(td) / "green-criteria.yml"
            criteria.write_text("criteria: []\n", encoding="utf-8")

            # criteria present but workflows dir missing -> exit 1 (was sys.exit(1)
            # in the original heredoc; must not have drifted to a different code)
            os.environ["CRITERIA_PATH"] = str(criteria)
            os.environ["WORKFLOWS_DIR"] = str(Path(td) / "no-such-dir")
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                assert verifier.main() == 1

            # criteria + workflows dir both present, empty criteria -> valid, exit 0
            wd = Path(td) / "workflows"
            wd.mkdir()
            os.environ["WORKFLOWS_DIR"] = str(wd)
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                assert verifier.main() == 0
    finally:
        os.environ.clear()
        os.environ.update(saved)


def main() -> int:
    failures: list[str] = []

    for name, crit, flows, expect_violation in CASES:
        got = bool(verifier.check(crit, flows))
        if got != expect_violation:
            failures.append(
                f"  - {name}\n"
                f"      expected {'a violation' if expect_violation else 'no violation'}, "
                f"got {verifier.check(crit, flows) or 'none'}"
            )

    try:
        test_triggers_parsing()
        test_is_reachable()
        test_callers_and_load_workflows()
        test_main_exit_codes()
    except AssertionError as e:
        failures.append(f"  - direct unit test failed: {e}")

    if failures:
        print("FAIL: CI-contract verifier regressed:", file=sys.stderr)
        print("\n".join(failures), file=sys.stderr)
        return 1

    print(
        f"OK: {len(CASES)} policy cases + 4 unit tests pass; "
        "trigger parsing, reachability and blocking-gate checks behave as pinned."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
