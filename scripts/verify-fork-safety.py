#!/usr/bin/env python3
"""Verify that pull_request workflows survive execution from forks.

This is the engine that used to live inline in
.github/workflows/reusable-fork-safety.yml (embedded in a YAML `run:` heredoc).
Embedding it in YAML made it untestable: a change to the write-action regex, the
secret-reference regex, or the fork-guard set could only be exercised by running
the workflow in a consumer repository. Extracting it here gives it a stable
command boundary so it can be imported and unit-tested (see
test-verify-fork-safety.py) before it ships to every @main consumer.

The CLI reads the same input the workflow passed through an environment variable
(WORKFLOWS_DIR) and prints the same text, so consumer behaviour is unchanged --
only the location of the code moved.

Usage:
    verify-fork-safety.py            # uses WORKFLOWS_DIR env, or the default below

Exit codes:
    0  all pull_request workflows are fork-safe (or no workflows dir to check)
    1  a workflow is not fork-safe
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Iterable

import yaml

# A step that performs a write from inside a workflow. On a fork pull_request
# the token is read-only and secrets are empty, so any of these unguarded is a
# hole: either it silently no-ops (false negative -- the gate it stands for
# never fires) or, if the workflow is later re-run off-branch, it can write.
WRITE_ACTIONS = re.compile(
    r"git push|gh pr (comment|create|edit|review|merge)|gh issue (comment|create|edit)"
    r"|gh api [^\n]*(--method|-X) ?(POST|PATCH|PUT|DELETE)"
    r"|gh api [^\n]*-F |gh release |actions/github-script"
)

# A `${{ secrets.X }}` reference. The negative look-ahead keeps GITHUB_TOKEN
# itself out: that secret is always populated, even from a fork, so referencing
# it is never a leak.
SECRET_REF = re.compile(r"\$\{\{\s*secrets\.(?!GITHUB_TOKEN\b)([A-Za-z0-9_]+)")

# Text that marks a step/job as fork-aware: it only does its write when the run
# is NOT a fork pull_request (or otherwise proves trust). If a guarded step
# contains any of these it is allowed to touch writes/secrets.
FORK_GUARDS = (
    "github.event_name != 'pull_request'",
    'github.event_name != "pull_request"',
    "github.event_name == 'workflow_dispatch'",
    "head.repo.fork",
    "head.repo.full_name",
    "IS_FORK",
    "no_r2_credentials",
)


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_yaml_dir(directory: Path) -> dict[str, dict]:
    """Parse every workflow in *directory*, keyed by filename (basename)."""
    docs: dict[str, dict] = {}
    for f in sorted(list(directory.glob("*.yml")) + list(directory.glob("*.yaml"))):
        docs[f.name] = load_yaml(f)
    return docs


def get_triggers(doc: dict) -> dict:
    """Return the event names a workflow is wired to (string / list / mapping)."""
    on = doc.get("on", doc.get(True, {}))
    if isinstance(on, str):
        return {on: None}
    if isinstance(on, list):
        return {k: None for k in on}
    return on or {}


def pr_workflow_names(workflows: dict[str, dict]) -> list[str]:
    """Sorted basenames of workflows that fire on pull_request."""
    return sorted(
        name for name, doc in workflows.items() if "pull_request" in get_triggers(doc or {})
    )


def is_fork_aware(text: str) -> bool:
    return any(g in text for g in FORK_GUARDS)


def check(workflows: dict[str, dict]) -> list[str]:
    """Return the list of fork-safety violations, empty when every PR workflow is safe.

    Pure and side-effect free so tests can drive it with in-memory fixtures:
    *workflows* maps each workflow filename to its parsed document.
    """
    violations: list[str] = []

    for name in pr_workflow_names(workflows):
        doc = workflows[name] or {}
        # 1. Top-level `permissions:` must be declared, or every non-delegated
        #    job runs with the repo defaults -- which is exactly what a fork
        #    would exploit.
        has_top_permissions = "permissions" in doc
        jobs = doc.get("jobs") or {}
        if not has_top_permissions:
            missing = [
                j
                for j, body in jobs.items()
                if "permissions" not in (body or {}) and "uses" not in (body or {})
            ]
            if missing:
                violations.append(
                    f"{name}: jobs {missing} lack explicit `permissions:` declaration."
                )

        # 2. pull_request_target re-runs the workflow with the *base* repo's
        #    context, exposing secrets to untrusted fork code.
        if "pull_request_target" in get_triggers(doc):
            violations.append(
                f"{name}: uses `pull_request_target` which exposes secrets to untrusted code."
            )

        # 3. Every step that writes or references a secret must be guarded.
        for job_id, job in jobs.items():
            job = job or {}
            job_guard = is_fork_aware(str(job.get("if", "")))
            steps = job.get("steps") or []
            aware_ids = {
                s.get("id")
                for s in steps
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
                step_text = (
                    cond + "\n" + yaml.dump(step.get("env") or {}) + "\n" + str(step.get("run", ""))
                )
                guarded_by_preflight = any(
                    f"steps.{sid}.outputs" in cond for sid in aware_ids
                )
                if (
                    job_guard
                    or guarded_by_preflight
                    or is_fork_aware(step_text)
                    or step.get("continue-on-error")
                ):
                    continue
                what = (
                    "secrets " + ",".join(sorted(set(secrets)))
                    if secrets
                    else "a write action"
                )
                violations.append(
                    f"{name}: job {job_id!r} step {step.get('name', '?')!r} "
                    f"uses {what} without fork guard"
                )

    return violations


def main() -> int:
    workflows_dir = Path(os.environ.get("WORKFLOWS_DIR", ".github/workflows"))
    if not workflows_dir.is_dir():
        print(f"No workflows directory found at {workflows_dir}")
        return 0

    workflows = load_yaml_dir(workflows_dir)
    print(
        f"Checking {len(pr_workflow_names(workflows))} "
        f"pull_request workflow(s) in {workflows_dir}..."
    )

    violations = check(workflows)
    if violations:
        print(f"❌ Fork safety violations found ({len(violations)}):")
        for v in violations:
            print(f"  • {v}")
        return 1

    print("✅ All pull_request workflows are fork-safe.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
