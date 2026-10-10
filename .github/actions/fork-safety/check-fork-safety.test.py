#!/usr/bin/env python3
"""Tests for check-fork-safety.py.

The validator parses workflow YAML, so these tests import it by path and drive
it two ways: the pure ``check_safety`` function against fixture directories, and
the ``main`` CLI exit codes. Run with either:

    python3 check-fork-safety.test.py
    python3 -m unittest check-fork-safety.test
"""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location(
    "check_fork_safety", SCRIPT_DIR / "check-fork-safety.py"
)
check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check)


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


class ForkSafetyTestCase(unittest.TestCase):
    """Base class: a temp workflows dir, cleaned up after each test."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def workflow(self, name, body):
        path = self.dir / name
        write(path, body)
        return str(path)

    def check(self, workflows_dir=None):
        return check.check_safety(workflows_dir or self.dir)

    def run_main(self, workflows_dir=None):
        return check.main(["--workflows-dir", workflows_dir or str(self.dir)])


# A pull_request workflow that is fully fork-safe: top-level permissions, no
# pull_request_target, and the only write step is guarded by a fork condition.
SAFE = """
name: Safe
on:
  pull_request:
permissions:
  contents: read
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: push when not a fork
        if: github.event_name != 'pull_request'
        run: git push
"""

# Missing top-level permissions, and a job that declares neither permissions nor
# uses -> that job is reported.
MISSING_PERMISSIONS = """
name: NoPerms
on:
  pull_request:
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo hi
"""

# A reusable workflow job (uses:) is exempt from the missing-permissions check,
# because the called workflow owns its own permissions block.
REUSABLE_CALLER = """
name: Calls Reusable
on:
  pull_request:
jobs:
  build:
    uses: ./.github/workflows/reusable.yml
"""

# A workflow that fires on pull_request and pull_request_target is entered by
# find_pr_workflows (it has a pull_request trigger), so the pull_request_target
# check inside the loop fires against it.
PR_TARGET = """
name: Target
on:
  pull_request:
  pull_request_target:
permissions:
  contents: read
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo hi
"""

# A write step with no fork guard at all -> violation.
UNGUARDED_WRITE = """
name: Unguarded
on:
  pull_request:
permissions:
  contents: read
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: git push
"""

# A secret reference with no fork guard -> violation.
UNGUARDED_SECRET = """
name: Secret
on:
  pull_request:
permissions:
  contents: read
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo ${{ secrets.TOKEN }}
"""

# The read-only GITHUB_TOKEN is explicitly allowed by the secret regex, so a
# step that only uses it is NOT reported even without a guard.
GITHUB_TOKEN_ONLY = """
name: Token
on:
  pull_request:
permissions:
  contents: read
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo ${{ secrets.GITHUB_TOKEN }}
"""

# A write step guarded by a job-level fork condition -> NOT reported.
JOB_GUARDED = """
name: JobGuarded
on:
  pull_request:
permissions:
  contents: read
jobs:
  build:
    if: github.event_name != 'pull_request'
    runs-on: ubuntu-latest
    steps:
      - run: git push
"""

# A write step guarded by its own fork condition -> NOT reported.
STEP_GUARDED = """
name: StepGuarded
on:
  pull_request:
permissions:
  contents: read
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: push
        if: head.repo.fork
        run: git push
"""

# A write step that continue-on-error is set on -> NOT reported (the original
# runner swallows the failure, so a fork cannot actually write).
CONTINUE_ON_ERROR = """
name: Continue
on:
  pull_request:
permissions:
  contents: read
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: push
        continue-on-error: true
        run: git push
"""

# A write step guarded by an earlier step's outputs (preflight) -> NOT reported.
PREFLIGHT_GUARDED = """
name: Preflight
on:
  pull_request:
permissions:
  contents: read
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: check
        id: check
        if: head.repo.fork
        run: echo done
      - name: push
        if: steps.check.outputs.fork == 'false'
        run: git push
"""

# A workflow that does not fire on pull_request is ignored entirely.
NON_PR = """
name: Dispatched
on:
  workflow_dispatch:
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: git push
"""


class ForkSafetyRulesTests(ForkSafetyTestCase):
    def test_safe_workflow_has_no_violations(self):
        self.workflow("safe.yml", SAFE)
        self.assertEqual(self.check(), [])

    def test_missing_top_level_permissions_reports_job(self):
        self.workflow("noperms.yml", MISSING_PERMISSIONS)
        violations = self.check()
        self.assertEqual(len(violations), 1)
        self.assertIn("jobs ['build'] lack explicit", violations[0])

    def test_reusable_caller_exempt_from_permission_check(self):
        self.workflow("caller.yml", REUSABLE_CALLER)
        self.assertEqual(self.check(), [])

    def test_pull_request_target_always_reported(self):
        self.workflow("target.yml", PR_TARGET)
        violations = self.check()
        self.assertEqual(len(violations), 1)
        self.assertIn("pull_request_target", violations[0])

    def test_unguarded_write_reported(self):
        self.workflow("unguarded.yml", UNGUARDED_WRITE)
        violations = self.check()
        self.assertEqual(len(violations), 1)
        self.assertIn("a write action", violations[0])

    def test_unguarded_secret_reported(self):
        self.workflow("secret.yml", UNGUARDED_SECRET)
        violations = self.check()
        self.assertEqual(len(violations), 1)
        self.assertIn("secrets TOKEN", violations[0])

    def test_github_token_is_allowed(self):
        self.workflow("token.yml", GITHUB_TOKEN_ONLY)
        self.assertEqual(self.check(), [])

    def test_job_level_guard_suppresses_write(self):
        self.workflow("jobguard.yml", JOB_GUARDED)
        self.assertEqual(self.check(), [])

    def test_step_level_guard_suppresses_write(self):
        self.workflow("stepguard.yml", STEP_GUARDED)
        self.assertEqual(self.check(), [])

    def test_continue_on_error_suppresses_write(self):
        self.workflow("continue.yml", CONTINUE_ON_ERROR)
        self.assertEqual(self.check(), [])

    def test_preflight_guard_suppresses_write(self):
        self.workflow("preflight.yml", PREFLIGHT_GUARDED)
        self.assertEqual(self.check(), [])

    def test_non_pr_workflow_ignored(self):
        self.workflow("dispatched.yml", NON_PR)
        self.assertEqual(self.check(), [])

    def test_multiple_violations_reported_together(self):
        self.workflow("noperms.yml", MISSING_PERMISSIONS)
        self.workflow("unguarded.yml", UNGUARDED_WRITE)
        self.assertEqual(len(self.check()), 2)


class MainExitCodeTests(ForkSafetyTestCase):
    def test_clean_directory_exits_zero(self):
        self.workflow("safe.yml", SAFE)
        self.assertEqual(self.run_main(), 0)

    def test_violations_exit_one(self):
        self.workflow("unguarded.yml", UNGUARDED_WRITE)
        self.assertEqual(self.run_main(), 1)

    def test_missing_directory_exits_zero(self):
        self.assertEqual(self.run_main(str(self.dir / "does-not-exist")), 0)


if __name__ == "__main__":
    sys.exit(unittest.main(verbosity=2))
