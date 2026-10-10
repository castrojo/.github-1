#!/usr/bin/env python3
"""Tests for check-ci-contract.py.

The validator parses workflow YAML, so these tests import it by path and drive
it three ways: the pure ``check_contract`` function against fixture directories,
the ``load_criteria`` skip/return behaviour, and the ``main`` CLI exit codes.
Run with either:

    python3 check-ci-contract.test.py
    python3 -m unittest check-ci-contract.test
"""
import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location(
    "check_ci_contract", SCRIPT_DIR / "check-ci-contract.py"
)
check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check)


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


class ContractTestCase(unittest.TestCase):
    """Base class: a temp workflows dir, cleaned up after each test."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def workflow(self, name, body):
        path = self.dir / name
        write(path, body)
        return str(path)

    def check(self, criteria, workflows_dir=None):
        return check.check_contract(criteria, workflows_dir or self.dir)


# A minimal workflow with a push trigger and one named step.
REACHABLE = """
name: Build
on:
  push:
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - name: run tests
        run: echo hi
"""

# Same shape but triggered only by workflow_dispatch, which is not "active".
NOT_REACHABLE = """
name: Dispatched
on:
  workflow_dispatch:
jobs:
  job:
    runs-on: ubuntu-latest
    steps:
      - name: do things
        run: echo hi
"""

# A reusable workflow referenced by another via `uses: ./name`.
REUSABLE = """
name: Reusable
on:
  workflow_call:
jobs:
  gate:
    runs-on: ubuntu-latest
    steps:
      - name: verdict
        run: echo ok
"""

CALLER_OF_REUSABLE = """
name: Caller
on:
  push:
jobs:
  build:
    uses: ./reusable.yml
"""


class TestLoadCriteria(ContractTestCase):
    def test_missing_file_returns_none(self):
        # No criteria file at all -> caller skips verification.
        self.assertIsNone(check.load_criteria(str(self.dir / "green-criteria.yml")))

    def test_existing_file_returns_criteria_list(self):
        write(self.dir / "green-criteria.yml", "criteria:\n  - id: a\n    gates: []\n")
        loaded = check.load_criteria(str(self.dir / "green-criteria.yml"))
        self.assertEqual(loaded, [{"id": "a", "gates": []}])

    def test_file_without_criteria_key_is_empty_list(self):
        write(self.dir / "green-criteria.yml", "somethingelse: 1\n")
        self.assertEqual(check.load_criteria(str(self.dir / "green-criteria.yml")), [])


class TestCheckContract(ContractTestCase):
    def test_no_criteria_no_violations(self):
        self.workflow("a.yml", REACHABLE)
        self.assertEqual(self.check([]), [])

    def test_gate_workflow_does_not_exist(self):
        self.workflow("a.yml", REACHABLE)
        criteria = [
            {
                "id": "ci-green",
                "gates": [{"workflow": "nope.yml", "jobs": {}}],
                "freshness_sla_days": 30,
            }
        ]
        self.assertEqual(self.check(criteria), ["ci-green: gate workflow nope.yml does not exist"])

    def test_gate_workflow_not_named_in_asserted_by(self):
        self.workflow("lint.yml", REACHABLE)
        # asserted_by mentions a different workflow, so lint.yml is unnamed.
        criteria = [
            {
                "id": "lint-done",
                "asserted_by": "the unit-test job covers this",
                "gates": [{"workflow": "lint.yml", "jobs": {}}],
                "freshness_sla_days": 30,
            }
        ]
        self.assertEqual(
            self.check(criteria),
            ["lint-done: gate workflow lint.yml is not mentioned in asserted_by"],
        )

    def test_unreachable_workflow_reported(self):
        self.workflow("dispatched.yml", NOT_REACHABLE)
        criteria = [
            {
                "id": "gate",
                "asserted_by": "dispatched.yml runs the gate",
                "gates": [{"workflow": "dispatched.yml", "jobs": {}}],
                "freshness_sla_days": 30,
            }
        ]
        # workflow_dispatch is not an active trigger, so the gate is unreachable.
        self.assertEqual(
            self.check(criteria),
            ["gate: dispatched.yml is not reachable from any active trigger"],
        )

    def test_reachable_via_reusable_caller(self):
        # The reusable workflow itself has no active trigger, but a caller with a
        # push trigger makes it reachable through the callers() graph.
        self.workflow("reusable.yml", REUSABLE)
        self.workflow("caller.yml", CALLER_OF_REUSABLE)
        criteria = [
            {
                "id": "gate",
                "asserted_by": "reusable.yml runs the gate",
                "gates": [{"workflow": "reusable.yml", "jobs": {}}],
                "freshness_sla_days": 30,
            }
        ]
        self.assertEqual(self.check(criteria), [])

    def test_missing_freshness_sla(self):
        self.workflow("lint.yml", REACHABLE)
        criteria = [
            {
                "id": "lint-done",
                "asserted_by": "lint.yml runs the gate",
                "gates": [{"workflow": "lint.yml", "jobs": {}}],
            }
        ]
        self.assertEqual(self.check(criteria), ["lint-done: missing freshness_sla_days"])

    def test_gates_block_but_only_asserted_by(self):
        # gates present but empty, yet asserted_by names something -> malformed.
        self.workflow("lint.yml", REACHABLE)
        criteria = [
            {
                "id": "lint-done",
                "asserted_by": "lint.yml runs the gate",
                "gates": [],
                "freshness_sla_days": 30,
            }
        ]
        self.assertEqual(
            self.check(criteria),
            ["lint-done: asserted_by names something but there is no `gates` block"],
        )

    def test_missing_job(self):
        self.workflow("lint.yml", REACHABLE)
        criteria = [
            {
                "id": "gate",
                "asserted_by": "lint.yml runs the gate",
                "gates": [{"workflow": "lint.yml", "jobs": {"no-such-job": None}}],
                "freshness_sla_days": 30,
            }
        ]
        self.assertEqual(
            self.check(criteria),
            ["gate: lint.yml has no job 'no-such-job'"],
        )

    def test_hard_disabled_job(self):
        body = """
name: Build
on:
  push:
jobs:
  test:
    if: false
    runs-on: ubuntu-latest
    steps:
      - name: run tests
        run: echo hi
"""
        self.workflow("build.yml", body)
        criteria = [
            {
                "id": "gate",
                "asserted_by": "build.yml runs the gate",
                "gates": [{"workflow": "build.yml", "jobs": {"test": None}}],
                "freshness_sla_days": 30,
            }
        ]
        self.assertEqual(
            self.check(criteria),
            ["gate: build.yml:test is hard-disabled"],
        )

    def test_blocking_gate_with_continue_on_error(self):
        body = """
name: Build
on:
  push:
jobs:
  test:
    continue-on-error: true
    runs-on: ubuntu-latest
    steps:
      - name: run tests
        run: echo hi
"""
        self.workflow("build.yml", body)
        criteria = [
            {
                "id": "gate",
                "asserted_by": "build.yml runs the gate",
                "enforcement": "blocking",
                "gates": [{"workflow": "build.yml", "jobs": {"test": None}}],
                "freshness_sla_days": 30,
            }
        ]
        self.assertEqual(
            self.check(criteria),
            ["gate: blocking gate build.yml:test has continue-on-error"],
        )

    def test_non_blocking_continue_on_error_is_allowed(self):
        body = """
name: Build
on:
  push:
jobs:
  test:
    continue-on-error: true
    runs-on: ubuntu-latest
    steps:
      - name: run tests
        run: echo hi
"""
        self.workflow("build.yml", body)
        criteria = [
            {
                "id": "gate",
                "asserted_by": "build.yml runs the gate",
                "enforcement": "advisory",
                "gates": [{"workflow": "build.yml", "jobs": {"test": None}}],
                "freshness_sla_days": 30,
            }
        ]
        self.assertEqual(self.check(criteria), [])

    def test_missing_named_step(self):
        self.workflow("lint.yml", REACHABLE)
        criteria = [
            {
                "id": "gate",
                "asserted_by": "lint.yml runs the gate",
                "gates": [{"workflow": "lint.yml", "jobs": {"test": "a different step"}}],
                "freshness_sla_days": 30,
            }
        ]
        self.assertEqual(
            self.check(criteria),
            ["gate: lint.yml:test has no step named 'a different step'"],
        )

    def test_full_match_no_violations(self):
        self.workflow("lint.yml", REACHABLE)
        criteria = [
            {
                "id": "gate",
                "asserted_by": "lint.yml runs the gate",
                "gates": [{"workflow": "lint.yml", "jobs": {"test": "run tests"}}],
                "freshness_sla_days": 30,
            }
        ]
        self.assertEqual(self.check(criteria), [])

    def test_gate_names_workflow_by_basename(self):
        # A gate may name the workflow by basename; load_workflows keys both.
        self.workflow("lint.yml", REACHABLE)
        criteria = [
            {
                "id": "gate",
                "asserted_by": "lint.yml runs the gate",
                "gates": [{"workflow": "sub/lint.yml", "jobs": {"test": "run tests"}}],
                "freshness_sla_days": 30,
            }
        ]
        self.assertEqual(self.check(criteria), [])


class TestMain(ContractTestCase):
    def test_missing_criteria_exits_zero(self):
        # Mirrors the original workflow: no criteria file -> skip, not fail.
        code = check.main(["--workflows-dir", str(self.dir)])
        self.assertEqual(code, 0)

    def test_missing_workflows_dir_exits_one(self):
        write(self.dir / "green-criteria.yml", "criteria:\n  - id: a\n    gates: []\n")
        code = check.main(
            [
                "--criteria",
                str(self.dir / "green-criteria.yml"),
                "--workflows-dir",
                str(self.dir / "does-not-exist"),
            ]
        )
        self.assertEqual(code, 1)

    def test_env_fallback_for_paths(self):
        # The action passes inputs through the environment; main must honour them.
        write(self.dir / "green-criteria.yml", "criteria: []\n")
        env = {
            "CRITERIA_PATH": str(self.dir / "green-criteria.yml"),
            "WORKFLOWS_DIR": str(self.dir),
        }
        saved = {k: os.environ.get(k) for k in env}
        try:
            os.environ.update(env)
            self.assertEqual(check.main([]), 0)
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


if __name__ == "__main__":
    sys.exit(unittest.main(verbosity=2))
