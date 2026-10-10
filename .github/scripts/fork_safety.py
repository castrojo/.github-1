#!/usr/bin/env python3
"""Verify that pull_request workflows survive execution from forks.

tuna-os/.github#275: extracted from the 140-line heredoc in
``reusable-fork-safety.yml``. On a ``pull_request`` raised from a fork GitHub
issues a read-only token and empties every secret, so this checks that:

  1. every ``pull_request`` workflow declares an explicit ``permissions:`` block
     (or a job that only ``uses:`` another workflow),
  2. no workflow uses ``pull_request_target`` (it runs with secrets against
     untrusted code), and
  3. every step that writes or references a secret is guarded by a fork-aware
     ``if:`` condition.

The YAML loading and trigger normalisation live in ``workflow_introspector``;
this module is the fork-safety rules and the CLI. Run through
``.github/actions/fork-safety-check`` so it executes against the calling
repository's checkout.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

import yaml

from workflow_introspector import get_triggers, load_workflow

DEFAULT_WORKFLOWS_DIR = ".github/workflows"

# Commands that perform a write against the GitHub API or the filesystem. A
# pull_request-from-fork step running any of these with the (read-only, secretless)
# fork token is the failure mode the check guards against.
WRITE_ACTIONS = re.compile(
    r"git push|gh pr (comment|create|edit|review|merge)|gh issue (comment|create|edit)"
    r"|gh api [^\n]*(--method|-X) ?(POST|PATCH|PUT|DELETE)"
    r"|gh api [^\n]*-F |gh release |actions/github-script"
)
# A ${{ secrets.NAME }} reference, but not the read-only GITHUB_TOKEN.
SECRET_REF = re.compile(r"\$\{\{\s*secrets\.(?!GITHUB_TOKEN\b)([A-Za-z0-9_]+)")
# ``if:`` conditions that prove the step did not run on an untrusted fork push.
FORK_GUARDS = (
    "github.event_name != 'pull_request'",
    'github.event_name != "pull_request"',
    "github.event_name == 'workflow_dispatch'",
    "head.repo.fork",
    "head.repo.full_name",
    "IS_FORK",
    "no_r2_credentials",
)


def is_fork_aware(text: str) -> bool:
    """True if ``text`` contains any fork-aware ``if:`` guard."""
    return any(g in text for g in FORK_GUARDS)


def validate_fork_safety(workflows_dir: str = DEFAULT_WORKFLOWS_DIR):
    """Return the list of fork-safety violations for ``workflows_dir``."""
    directory = Path(workflows_dir)
    if not directory.is_dir():
        print(f"No workflows directory found at {directory}")
        return []

    files = sorted(directory.glob("*.yml")) + sorted(directory.glob("*.yaml"))
    pr_workflows = [f for f in files if "pull_request" in get_triggers(load_workflow(f))]

    print(f"Checking {len(pr_workflows)} pull_request workflow(s) in {directory}...")
    violations = []
    for wf in pr_workflows:
        violations.extend(_check_workflow(wf))
    return violations


def _check_workflow(wf: Path):
    doc = load_workflow(wf)
    jobs = doc.get("jobs") or {}

    # 1. Top-level permissions declared, or every job is a thin wrapper around
    #    another workflow (which carries its own permissions).
    violations = []
    if "permissions" not in doc:
        missing = [
            j for j, body in jobs.items()
            if "permissions" not in (body or {}) and "uses" not in (body or {})
        ]
        if missing:
            violations.append(f"{wf.name}: jobs {missing} lack explicit `permissions:` declaration.")

    # 2. pull_request_target runs untrusted code with the secret store attached.
    if "pull_request_target" in get_triggers(doc):
        violations.append(f"{wf.name}: uses `pull_request_target` which exposes secrets to untrusted code.")

    # 3. Each write/secret step must be guarded against forks.
    for job_id, job in jobs.items():
        job = job or {}
        job_guard = is_fork_aware(str(job.get("if", "")))
        steps = job.get("steps") or []
        aware_ids = {
            s.get("id") for s in steps
            if s.get("id") and is_fork_aware(
                str(s.get("if", "")) + yaml.dump(s.get("env") or {}) + str(s.get("run", ""))
            )
        }
        for step in steps:
            blob = yaml.dump(step)
            needs_write = bool(WRITE_ACTIONS.search(blob))
            secrets = [m.group(1) for m in SECRET_REF.finditer(blob)]
            if not needs_write and not secrets:
                continue
            cond = str(step.get("if", ""))
            step_text = cond + "\n" + yaml.dump(step.get("env") or {}) + "\n" + str(step.get("run", ""))
            guarded_by_preflight = any(f"steps.{sid}.outputs" in cond for sid in aware_ids)
            if job_guard or guarded_by_preflight or is_fork_aware(step_text) or step.get("continue-on-error"):
                continue
            what = "secrets " + ",".join(sorted(set(secrets))) if secrets else "a write action"
            violations.append(
                f"{wf.name}: job {job_id!r} step {step.get('name', '?')!r} uses {what} without fork guard"
            )
    return violations


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Check pull_request workflows for fork safety.")
    parser.add_argument("--workflows-dir", default=os.environ.get("WORKFLOWS_DIR", DEFAULT_WORKFLOWS_DIR))
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    violations = validate_fork_safety(args.workflows_dir)
    if violations:
        print(f"❌ Fork safety violations found ({len(violations)}):")
        for v in violations:
            print(f"  • {v}")
        return 1
    print("✅ All pull_request workflows are fork-safe.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
