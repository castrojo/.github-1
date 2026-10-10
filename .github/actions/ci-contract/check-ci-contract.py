"""Verify that reachable workflows assert every green criterion.

tuna-os/.github#206: the CI-contract check used to live as 90+ lines of Python
embedded in the `reusable-ci-contract.yml` workflow step. That made the contract
rules impossible to unit-test without standing up the whole workflow, and the
rules could drift from whatever a reviewer assumed made CI green. This is that
same extractor moved into a standalone, importable CLI packaged as the
`ci-contract` composite action, so the rules live in one tested place and travel
with the action to every caller.

A "green criterion" (``.github/green-criteria.yml`` when present) records what
must make CI green. Each criterion names the workflow / job / step that asserts
it and a freshness SLA. This verifies that every named gate:

  * refers to a workflow that actually exists in the directory,
  * is reachable from an active trigger (push / pull_request / schedule / ...),
  * is named in the criterion's ``asserted_by`` prose,
  * has the named job (not hard-disabled, not ``continue-on-error`` when the
    gate is blocking), and
  * has the named step.

Usage:
    check-ci-contract.py [--criteria PATH] [--workflows-dir DIR]

The ``--criteria`` / ``--workflows-dir`` values fall back to the
``CRITERIA_PATH`` / ``WORKFLOWS_DIR`` environment variables when set -- that is
how the composite action passes them, so an untrusted caller value is always
data and is never parsed as shell. The flags exist for standalone use and the
unit tests.

Exit code is 0 when there are no violations (or no criteria file to check), 1
otherwise.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - the action installs PyYAML first
    yaml = None  # type: ignore[assignment]

ACTIVE_TRIGGERS = {"schedule", "push", "pull_request", "merge_group", "workflow_run", "release"}
HARD_DISABLED = {"false", "${{ false }}"}
DEFAULT_CRITERIA = ".github/green-criteria.yml"
DEFAULT_WORKFLOWS_DIR = ".github/workflows"


def load_criteria(criteria_path: str | os.PathLike[str]) -> list | None:
    """Return the ``criteria`` list, or ``None`` when the file does not exist.

    ``None`` (not an empty list) is meaningful: the caller skips verification
    entirely rather than reporting that every criterion is missing.
    """
    path = Path(criteria_path)
    if not path.is_file():
        return None
    if yaml is None:
        raise SystemExit("PyYAML is required to read the criteria file (pip install pyyaml)")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return raw.get("criteria", [])


def load_workflows(workflows_dir: str | os.PathLike[str]) -> dict:
    """Load every ``*.yml`` / ``*.yaml`` workflow, keyed by path and basename."""
    directory = Path(workflows_dir)
    docs: dict = {}
    for f in sorted(list(directory.glob("*.yml")) + list(directory.glob("*.yaml"))):
        doc = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        # Key by both the full path and the basename so a gate may name a
        # workflow either way.
        docs[f"{directory}/{f.name}"] = doc
        docs[f.name] = doc
    return docs


def triggers(doc: dict) -> dict:
    """Normalise a workflow's ``on:`` block to a set-like mapping of triggers."""
    on = doc.get("on", doc.get(True, {}))
    if isinstance(on, str):
        return {on: None}
    if isinstance(on, list):
        return {k: None for k in on}
    return on or {}


def callers(workflows: dict) -> dict:
    """Map each reusable ``./`` workflow to the workflows that call it."""
    out: dict = {}
    for name, doc in workflows.items():
        for job in (doc.get("jobs") or {}).values():
            uses = (job or {}).get("uses", "")
            if isinstance(uses, str) and uses.startswith("./"):
                out.setdefault(uses[2:], set()).add(name)
    return out


def is_reachable(name: str, workflows: dict, _seen: set | None = None) -> bool:
    """True when ``name`` has an active trigger or is called by a reachable one."""
    _seen = _seen or set()
    if name in _seen:
        return False
    _seen.add(name)
    doc = workflows.get(name)
    if doc is None:
        return False
    if ACTIVE_TRIGGERS & set(triggers(doc)):
        return True
    return any(is_reachable(c, workflows, _seen) for c in callers(workflows).get(name, ()))


def check_contract(criteria: list, workflows_dir: str | os.PathLike[str]) -> list:
    """Return the list of violation strings for ``criteria`` against the workflows."""
    workflows = load_workflows(workflows_dir)
    violations: list = []

    for criterion in criteria:
        cid = criterion.get("id", "unknown")
        gates = criterion.get("gates")
        if not gates:
            if criterion.get("asserted_by"):
                violations.append(f"{cid}: asserted_by names something but there is no `gates` block")
            continue
        if "freshness_sla_days" not in criterion:
            violations.append(f"{cid}: missing freshness_sla_days")
        blocking = criterion.get("enforcement") == "blocking"
        prose = criterion.get("asserted_by") or ""

        for gate in gates:
            wf = gate.get("workflow", "")
            wf_basename = wf.split("/")[-1]
            doc = workflows.get(wf) or workflows.get(wf_basename)
            if doc is None:
                violations.append(f"{cid}: gate workflow {wf} does not exist")
                continue
            if wf_basename not in prose:
                violations.append(f"{cid}: gate workflow {wf} is not mentioned in asserted_by")
            if not is_reachable(wf, workflows) and not is_reachable(wf_basename, workflows):
                violations.append(f"{cid}: {wf} is not reachable from any active trigger")

            jobs = doc.get("jobs") or {}
            for job_id, verdict_step in (gate.get("jobs") or {}).items():
                job = jobs.get(job_id)
                if job is None:
                    violations.append(f"{cid}: {wf} has no job {job_id!r}")
                    continue
                # A job is hard-disabled when its `if` evaluates to false. YAML
                # parses `if: false` to the boolean False (str() "False"), so the
                # boolean is checked directly and the string forms `false` and
                # `${{ false }}` separately; an absent `if` runs normally.
                if_value = job.get("if")
                if if_value is False or str(if_value).strip() in HARD_DISABLED:
                    violations.append(f"{cid}: {wf}:{job_id} is hard-disabled")
                if blocking and job.get("continue-on-error"):
                    violations.append(f"{cid}: blocking gate {wf}:{job_id} has continue-on-error")
                if verdict_step:
                    step_names = [s.get("name") for s in (job.get("steps") or []) if s.get("name")]
                    if verdict_step not in step_names:
                        violations.append(f"{cid}: {wf}:{job_id} has no step named {verdict_step!r}")

    return violations


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify .github/green-criteria.yml against reachable workflows."
    )
    parser.add_argument(
        "--criteria",
        default=os.environ.get("CRITERIA_PATH", DEFAULT_CRITERIA),
        help="Path to the green-criteria file (default: $CRITERIA_PATH or %(default)s)",
    )
    parser.add_argument(
        "--workflows-dir",
        default=os.environ.get("WORKFLOWS_DIR", DEFAULT_WORKFLOWS_DIR),
        help="Directory of workflow YAML files (default: $WORKFLOWS_DIR or %(default)s)",
    )
    args = parser.parse_args(argv)

    criteria = load_criteria(args.criteria)
    if criteria is None:
        print(f"No criteria file at {args.criteria}; skipping CI contract verification.")
        return 0

    workflows_dir = Path(args.workflows_dir)
    if not workflows_dir.is_dir():
        print(f"No workflows directory at {workflows_dir}.")
        return 1

    if yaml is None:
        print(
            "PyYAML is required to verify the CI contract; install it (pip install pyyaml).",
            file=sys.stderr,
        )
        return 1

    violations = check_contract(criteria, workflows_dir)
    if violations:
        print(f"❌ CI contract violations found ({len(violations)}):")
        for violation in violations:
            print(f"  • {violation}")
        return 1

    print(f"✅ CI contract valid: {len(criteria)} criteria verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
