"""Verify that ``pull_request`` workflows survive execution from forks.

tuna-os/.github#275: the fork-safety check used to live as ~140 lines of Python
embedded in the ``reusable-fork-safety.yml`` workflow step. That made the rules
impossible to unit-test without standing up the whole workflow, and each
workflow in the repo implemented its own YAML loader, trigger detection and
fork-guard checks, so a schema change had to be coordinated across every one.
This is that extractor moved into a standalone, importable CLI packaged as the
``fork-safety`` composite action, so the rules live in one tested place and
travel with the action to every caller (tuna-os/.github#275).

On a ``pull_request`` event raised from a fork, GitHub issues a read-only
``GITHUB_TOKEN`` and all repository secrets are empty. The check verifies that:

  1. every ``pull_request`` workflow declares explicit top-level ``permissions:``,
  2. no workflow uses ``pull_request_target`` without an explicit exception, and
  3. every step that runs a write action or references a secret is guarded by a
     fork-aware condition.

Usage:
    check-fork-safety.py [--workflows-dir DIR]

The ``--workflows-dir`` value falls back to the ``WORKFLOWS_DIR`` environment
variable when set -- that is how the composite action passes it, so an
untrusted caller value is always data and is never parsed as shell. The flag
exists for standalone use and the unit tests.

Exit code is 0 when there are no violations (or no workflows directory to check),
1 otherwise.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - the action installs PyYAML first
    yaml = None  # type: ignore[assignment]

DEFAULT_WORKFLOWS_DIR = ".github/workflows"

# A step that can write to the repository or the outside world from inside a
# fork-run job.
WRITE_ACTIONS = re.compile(
    r"git push|gh pr (comment|create|edit|review|merge)|gh issue (comment|create|edit)"
    r"|gh api [^\n]*(--method|-X) ?(POST|PATCH|PUT|DELETE)"
    r"|gh api [^\n]*-F |gh release |actions/github-script"
)
# A secrets.* reference that is not the read-only GITHUB_TOKEN.
SECRET_REF = re.compile(r"\$\{\{\s*secrets\.(?!GITHUB_TOKEN\b)([A-Za-z0-9_]+)")
# Conditions that prove a step or job only runs when it is not a fork.
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
    """Return the parsed document, or an empty dict for an empty file."""
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def get_triggers(doc: dict) -> dict:
    """Normalise a workflow's ``on:`` block to a mapping of triggers."""
    on = doc.get("on", doc.get(True, {}))
    if isinstance(on, str):
        return {on: None}
    if isinstance(on, list):
        return {k: None for k in on}
    return on or {}


def is_fork_aware(text: str) -> bool:
    """True when ``text`` contains any fork-guard condition."""
    return any(guard in text for guard in FORK_GUARDS)


def find_pr_workflows(workflows_dir: str | os.PathLike[str]) -> list[Path]:
    """Return the ``*.yml`` / ``*.yaml`` files that fire on ``pull_request``."""
    directory = Path(workflows_dir)
    files = sorted(list(directory.glob("*.yml")) + list(directory.glob("*.yaml")))
    return [f for f in files if "pull_request" in get_triggers(load_yaml(f))]


def check_safety(workflows_dir: str | os.PathLike[str]) -> list:
    """Return the list of fork-safety violation strings for the directory."""
    directory = Path(workflows_dir)
    if not directory.is_dir():
        return []

    pr_workflows = find_pr_workflows(directory)
    violations: list = []

    for wf in pr_workflows:
        doc = load_yaml(wf)
        # 1. Top-level permissions declared.
        has_top_permissions = "permissions" in doc
        jobs = doc.get("jobs") or {}
        if not has_top_permissions:
            missing = [
                job_id
                for job_id, body in jobs.items()
                if "permissions" not in (body or {}) and "uses" not in (body or {})
            ]
            if missing:
                violations.append(
                    f"{wf.name}: jobs {missing} lack explicit `permissions:` declaration."
                )

        # 2. pull_request_target without an explicit exception.
        if "pull_request_target" in get_triggers(doc):
            violations.append(
                f"{wf.name}: uses `pull_request_target` which exposes secrets to untrusted code."
            )

        # 3. Write actions and secrets in steps must be fork-guarded.
        for job_id, job in jobs.items():
            job = job or {}
            job_guard = is_fork_aware(str(job.get("if", "")))
            steps = job.get("steps") or []
            aware_ids = {
                step.get("id")
                for step in steps
                if step.get("id") and is_fork_aware(
                    str(step.get("if", ""))
                    + (yaml.dump(step.get("env") or {}) if yaml is not None else "")
                    + str(step.get("run", ""))
                )
            }
            for step in steps:
                blob = yaml.dump(step) if yaml is not None else ""
                needs_write = bool(WRITE_ACTIONS.search(blob))
                secrets = [m.group(1) for m in SECRET_REF.finditer(blob)]
                if not needs_write and not secrets:
                    continue
                cond = str(step.get("if", ""))
                step_env = yaml.dump(step.get("env") or {}) if yaml is not None else ""
                step_text = cond + "\n" + step_env + "\n" + str(step.get("run", ""))
                guarded_by_preflight = any(
                    f"steps.{sid}.outputs" in cond for sid in aware_ids if sid
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
                step_name = step.get("name", "?")
                violations.append(
                    f"{wf.name}: job {job_id!r} step {step_name!r} uses {what} without fork guard"
                )

    return violations


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify that pull_request workflows are fork-safe."
    )
    parser.add_argument(
        "--workflows-dir",
        default=os.environ.get("WORKFLOWS_DIR", DEFAULT_WORKFLOWS_DIR),
        help="Directory of workflow YAML files (default: $WORKFLOWS_DIR or %(default)s)",
    )
    args = parser.parse_args(argv)

    workflows_dir = Path(args.workflows_dir)
    if not workflows_dir.is_dir():
        print(f"No workflows directory found at {workflows_dir}")
        return 0

    if yaml is None:
        print(
            "PyYAML is required to verify fork safety; install it (pip install pyyaml).",
            file=sys.stderr,
        )
        return 1

    violations = check_safety(workflows_dir)
    if violations:
        print(f"❌ Fork safety violations found ({len(violations)}):")
        for violation in violations:
            print(f"  • {violation}")
        return 1

    print("✅ All pull_request workflows are fork-safe.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
