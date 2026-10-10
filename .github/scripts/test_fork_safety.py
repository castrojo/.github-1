#!/usr/bin/env python3
"""Tests for fork_safety.py.

Extracted from the heredoc in reusable-fork-safety.yml (tuna-os/.github#275).
Loaded by path; the scripts directory is put on sys.path so the sibling
``workflow_introspector`` import resolves. Run with either:

    python3 test_fork_safety.py
    python3 -m unittest .test_fork_safety
"""
import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

_spec = importlib.util.spec_from_file_location("fork_safety", SCRIPT_DIR / "fork_safety.py")
fork_safety = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fork_safety)


class TestForkSafety(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.workflows = Path(self.dir.name) / "workflows"
        self.workflows.mkdir()

    def tearDown(self):
        self.dir.cleanup()

    def write(self, name, text):
        (self.workflows / name).write_text(text)

    def check(self, name, text):
        self.write(name, text)
        return fork_safety.validate_fork_safety(str(self.workflows))

    def test_no_workflows_directory_is_clean(self):
        self.assertEqual(
            fork_safety.validate_fork_safety(str(Path(self.dir.name) / "none")), [])

    def test_pull_request_target_is_violation(self):
        # validate_fork_safety only iterates workflows that carry an exact
        # `pull_request` trigger, so a workflow that is *only* pull_request_target
        # is never checked. The original heredoc guards `pull_request_target`
        # inside _check_workflow, which runs only when the workflow is also a
        # pull_request workflow -- hence the combined trigger list below.
        violations = self.check(
            "prt.yml",
            "on: [pull_request, pull_request_target]\n"
            "permissions:\n"
            "  contents: write\n"
            "jobs:\n"
            "  build:\n"
            "    permissions:\n"
            "      contents: read\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - run: echo hi\n",
        )
        self.assertTrue(any("pull_request_target" in v for v in violations))

    def test_write_action_without_guard_is_violation(self):
        violations = self.check(
            "bad-write.yml",
            "name: Bad\n"
            "on: pull_request\n"
            "permissions:\n"
            "  contents: read\n"
            "jobs:\n"
            "  build:\n"
            "    permissions:\n"
            "      contents: read\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - run: git push https://x@github.com/o/r.git\n",
        )
        self.assertTrue(any("write action" in v for v in violations))

    def test_secret_without_guard_is_violation(self):
        violations = self.check(
            "secret.yml",
            "name: Secret\n"
            "on: pull_request\n"
            "permissions:\n"
            "  contents: read\n"
            "jobs:\n"
            "  build:\n"
            "    permissions:\n"
            "      contents: read\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - run: echo done\n"
            "        env:\n"
            "          TOKEN: ${{ secrets.TOKEN }}\n",
        )
        self.assertTrue(any("secrets TOKEN" in v for v in violations))

    def test_missing_top_level_permissions_is_violation(self):
        violations = self.check(
            "noperms.yml",
            "name: NoPerms\n"
            "on: pull_request\n"
            "jobs:\n"
            "  build:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - run: echo hi\n",
        )
        self.assertTrue(any("lack explicit" in v for v in violations))

    def test_fork_guarded_write_is_allowed(self):
        violations = self.check(
            "good.yml",
            "name: Good\n"
            "on: pull_request\n"
            "permissions:\n"
            "  contents: read\n"
            "jobs:\n"
            "  build:\n"
            "    permissions:\n"
            "      contents: read\n"
            "    runs-on: ubuntu-latest\n"
            "    if: github.event_name != 'pull_request'\n"
            "    steps:\n"
            "      - run: git push https://x@github.com/o/r.git\n",
        )
        self.assertEqual(violations, [])

    def test_secrets_token_is_not_a_secret_reference(self):
        # GITHUB_TOKEN is the read-only fork token; referencing it is not a violation.
        violations = self.check(
            "gh.yml",
            "name: GH\n"
            "on: pull_request\n"
            "permissions:\n"
            "  contents: read\n"
            "jobs:\n"
            "  build:\n"
            "    permissions:\n"
            "      contents: read\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - run: echo done\n"
            "        env:\n"
            "          TOKEN: ${{ secrets.GITHUB_TOKEN }}\n",
        )
        self.assertEqual(violations, [])

    def test_continue_on_error_disarms_write_check(self):
        # The guard reads the STEP's continue-on-error (not the job's): a write
        # step that tolerates failure is treated as acceptable (faithful).
        violations = self.check(
            "coe.yml",
            "name: CoE\n"
            "on: pull_request\n"
            "permissions:\n"
            "  contents: read\n"
            "jobs:\n"
            "  build:\n"
            "    permissions:\n"
            "      contents: read\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - run: git push https://x@github.com/o/r.git\n"
            "        continue-on-error: true\n",
        )
        self.assertEqual(violations, [])

    def test_pull_request_caller_not_flagged(self):
        # A workflow with only workflow_call is not a pull_request workflow and
        # is skipped entirely by validate_fork_safety.
        violations = self.check(
            "called.yml",
            "name: Called\n"
            "on: workflow_call\n"
            "jobs:\n"
            "  build:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - run: git push https://x@github.com/o/r.git\n",
        )
        self.assertEqual(violations, [])

    def test_main_returns_exit_code(self):
        for name, text in {
            "ok.yml": "on: pull_request\npermissions:\n  contents: read\njobs:\n  b:\n    permissions:\n      contents: read\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo\n",
            "bad.yml": "on: pull_request\npermissions:\n  contents: read\njobs:\n  b:\n    permissions:\n      contents: read\n    runs-on: ubuntu-latest\n    steps:\n      - run: git push https://x@github.com/o/r.git\n",
        }.items():
            self.write(name, text)
        os.environ["WORKFLOWS_DIR"] = str(self.workflows)
        try:
            self.assertEqual(fork_safety.main([]), 1)
        finally:
            del os.environ["WORKFLOWS_DIR"]


if __name__ == "__main__":
    unittest.main(verbosity=2)
