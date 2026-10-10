#!/usr/bin/env python3
"""Tests for ci_contract.py.

Extracted from the heredoc in reusable-ci-contract.yml (tuna-os/.github#275).
Loaded by path; the scripts directory is put on sys.path so the sibling
``workflow_introspector`` import resolves. Run with either:

    python3 test_ci_contract.py
    python3 -m unittest .test_ci_contract
"""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

_spec = importlib.util.spec_from_file_location("ci_contract", SCRIPT_DIR / "ci_contract.py")
ci_contract = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ci_contract)


class TestCiContract(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.workflows = Path(self.dir.name) / "workflows"
        self.workflows.mkdir()
        self.criteria = Path(self.dir.name) / "green-criteria.yml"

    def tearDown(self):
        self.dir.cleanup()

    def write(self, name, text):
        (self.workflows / name).write_text(text)

    def run_contract(self, criteria):
        self.criteria.write_text(criteria)
        return ci_contract.validate_ci_contract(str(self.criteria), str(self.workflows))

    def test_no_criteria_file_skips_cleanly(self):
        self.write("build.yml", "on: push\n")
        violations, skipped = ci_contract.validate_ci_contract(
            str(Path(self.dir.name) / "missing.yml"), str(self.workflows))
        self.assertTrue(skipped)
        self.assertEqual(violations, [])

    def test_valid_contract_has_no_violations(self):
        self.write("build.yml",
                   "on: push\n"
                   "jobs:\n"
                   "  build:\n"
                   "    runs-on: ubuntu-latest\n"
                   "    steps:\n"
                   "      - name: Run unit tests\n"
                   "        run: echo\n")
        criteria = (
            "criteria:\n"
            "  - id: unit-tests\n"
            "    freshness_sla_days: 7\n"
            "    enforcement: blocking\n"
            "    asserted_by: \"build.yml keeps unit tests current\"\n"
            "    gates:\n"
            "      - workflow: build.yml\n"
            "        jobs:\n"
            "          build: Run unit tests\n"
        )
        violations, _skipped = self.run_contract(criteria)
        self.assertEqual(violations, [])

    def test_missing_workflow(self):
        self.write("build.yml", "on: push\n")
        criteria = (
            "criteria:\n"
            "  - id: missing-wf\n"
            "    freshness_sla_days: 7\n"
            "    enforcement: advisory\n"
            "    asserted_by: \"nope.yml is here\"\n"
            "    gates:\n"
            "      - workflow: nope.yml\n"
        )
        violations, _ = self.run_contract(criteria)
        self.assertIn("missing-wf: gate workflow nope.yml does not exist", violations)

    def test_missing_freshness_sla(self):
        self.write("build.yml", "on: push\n")
        criteria = (
            "criteria:\n"
            "  - id: no-sla\n"
            "    enforcement: advisory\n"
            "    asserted_by: \"build.yml again\"\n"
            "    gates:\n"
            "      - workflow: build.yml\n"
        )
        violations, _ = self.run_contract(criteria)
        self.assertIn("no-sla: missing freshness_sla_days", violations)

    def test_not_mentioned_in_asserted_by(self):
        self.write("build.yml", "on: push\n")
        criteria = (
            "criteria:\n"
            "  - id: not-mentioned\n"
            "    freshness_sla_days: 7\n"
            "    enforcement: advisory\n"
            "    asserted_by: \"something else entirely\"\n"
            "    gates:\n"
            "      - workflow: build.yml\n"
        )
        violations, _ = self.run_contract(criteria)
        self.assertIn(
            "not-mentioned: gate workflow build.yml is not mentioned in asserted_by", violations)

    def test_unreachable_workflow(self):
        # workflow_call only -> not reachable from any active trigger.
        self.write("scheduled.yml", "on: workflow_call\n")
        criteria = (
            "criteria:\n"
            "  - id: unreachable\n"
            "    freshness_sla_days: 7\n"
            "    enforcement: advisory\n"
            "    asserted_by: \"scheduled.yml gate\"\n"
            "    gates:\n"
            "      - workflow: scheduled.yml\n"
        )
        violations, _ = self.run_contract(criteria)
        self.assertIn(
            "unreachable: scheduled.yml is not reachable from any active trigger", violations)

    def test_missing_step(self):
        self.write("build.yml",
                   "on: push\n"
                   "jobs:\n"
                   "  build:\n"
                   "    runs-on: ubuntu-latest\n"
                   "    steps:\n"
                   "      - name: Real step\n"
                   "        run: echo\n")
        criteria = (
            "criteria:\n"
            "  - id: no-step\n"
            "    freshness_sla_days: 7\n"
            "    enforcement: advisory\n"
            "    asserted_by: \"build.yml step\"\n"
            "    gates:\n"
            "      - workflow: build.yml\n"
            "        jobs:\n"
            "          build: Nonexistent Step\n"
        )
        violations, _ = self.run_contract(criteria)
        self.assertIn("no-step: build.yml:build has no step named 'Nonexistent Step'", violations)

    def test_hard_disabled_job(self):
        # if: "false" is a quoted string so the string-comparison hard-disabled
        # check fires (bare `if: false` parses to the boolean False, which the
        # `or ""` coercion turns into "" -- faithful to the extracted validator).
        self.write("build.yml",
                   "on: push\n"
                   "jobs:\n"
                   "  disabled:\n"
                   "    if: \"false\"\n"
                   "    runs-on: ubuntu-latest\n"
                   "    steps:\n"
                   "      - name: anything\n"
                   "        run: echo\n")
        criteria = (
            "criteria:\n"
            "  - id: hard-disabled\n"
            "    freshness_sla_days: 7\n"
            "    enforcement: advisory\n"
            "    asserted_by: \"build.yml off\"\n"
            "    gates:\n"
            "      - workflow: build.yml\n"
            "        jobs:\n"
            "          disabled: anything\n"
        )
        violations, _ = self.run_contract(criteria)
        self.assertIn("hard-disabled: build.yml:disabled is hard-disabled", violations)

    def test_asserted_by_without_gates(self):
        self.write("build.yml", "on: push\n")
        criteria = (
            "criteria:\n"
            "  - id: asserted-only\n"
            "    asserted_by: \"named but no gates\"\n"
        )
        violations, _ = self.run_contract(criteria)
        self.assertIn(
            "asserted-only: asserted_by names something but there is no `gates` block", violations)

    def test_blocking_with_continue_on_error(self):
        self.write("build.yml",
                   "on: push\n"
                   "jobs:\n"
                   "  build:\n"
                   "    continue-on-error: true\n"
                   "    runs-on: ubuntu-latest\n"
                   "    steps:\n"
                   "      - name: Run unit tests\n"
                   "        run: echo\n")
        criteria = (
            "criteria:\n"
            "  - id: coe\n"
            "    freshness_sla_days: 7\n"
            "    enforcement: blocking\n"
            "    asserted_by: \"build.yml coe\"\n"
            "    gates:\n"
            "      - workflow: build.yml\n"
            "        jobs:\n"
            "          build: Run unit tests\n"
        )
        violations, _ = self.run_contract(criteria)
        self.assertIn("coe: blocking gate build.yml:build has continue-on-error", violations)

    def test_advisory_continue_on_error_allowed(self):
        self.write("build.yml",
                   "on: push\n"
                   "jobs:\n"
                   "  build:\n"
                   "    continue-on-error: true\n"
                   "    runs-on: ubuntu-latest\n"
                   "    steps:\n"
                   "      - name: Run unit tests\n"
                   "        run: echo\n")
        criteria = (
            "criteria:\n"
            "  - id: coe\n"
            "    freshness_sla_days: 7\n"
            "    enforcement: advisory\n"
            "    asserted_by: \"build.yml coe\"\n"
            "    gates:\n"
            "      - workflow: build.yml\n"
            "        jobs:\n"
            "          build: Run unit tests\n"
        )
        violations, _ = self.run_contract(criteria)
        self.assertNotIn("coe: blocking gate build.yml:build has continue-on-error", violations)

    def test_reachable_via_active_caller(self):
        # called.yml is workflow_call only, but called by a push workflow -> reachable.
        self.write("called.yml", "on: workflow_call\n")
        self.write("caller.yml",
                   "on: push\n"
                   "jobs:\n"
                   "  build:\n"
                   "    uses: ./called.yml\n")
        criteria = (
            "criteria:\n"
            "  - id: via-caller\n"
            "    freshness_sla_days: 7\n"
            "    enforcement: advisory\n"
            "    asserted_by: \"called.yml gate\"\n"
            "    gates:\n"
            "      - workflow: called.yml\n"
        )
        violations, _ = self.run_contract(criteria)
        self.assertNotIn(
            "via-caller: called.yml is not reachable from any active trigger", violations)


if __name__ == "__main__":
    unittest.main(verbosity=2)
