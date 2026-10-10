#!/usr/bin/env python3
"""Verify that green-criteria.yml is asserted by reachable workflow jobs.

tuna-os/.github#275: extracted from the 160-line heredoc in
``reusable-ci-contract.yml``. It loads ``green-criteria.yml``, and for every
criterion's ``gates`` block checks that the named workflow exists, is reachable
from an active trigger, is mentioned in ``asserted_by``, and declares the named
job/step -- with the job not hard-disabled and, when the criterion is blocking,
not running with ``continue-on-error``.

The YAML loading, trigger normalisation, caller walk and reachability all live in
``workflow_introspector``; this module is only the criteria rules and the CLI.
Run through ``.github/actions/ci-contract-check`` so it executes against the
calling repository's checkout.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import yaml

from workflow_introspector import is_reachable, load_workflows

DEFAULT_CRITERIA_PATH = ".github/green-criteria.yml"
DEFAULT_WORKFLOWS_DIR = ".github/workflows"

# A criterion is only meaningful if it carries a freshness SLA; a gate with no
# SLA means nothing is being kept current, which is the whole point of the check.
FRESHNESS_KEY = "freshness_sla_days"


def validate_ci_contract(criteria_path: str = DEFAULT_CRITERIA_PATH,
                         workflows_dir: str = DEFAULT_WORKFLOWS_DIR):
    """Return ``(violations, skipped)`` for the CI contract.

    ``skipped`` is True when there is no criteria file at all -- the check is
    opt-in, so an absent ``green-criteria.yml`` is a clean no-op, not a failure.
    """
    criteria_file = Path(criteria_path)
    workflow_directory = Path(workflows_dir)

    if not criteria_file.is_file():
        print(f"No criteria file at {criteria_path}; skipping CI contract verification.")
        return [], True

    if not workflow_directory.is_dir():
        print(f"No workflows directory at {workflows_dir}.")
        return ["workflows directory missing"], False

    workflows = load_workflows(workflow_directory)
    criteria = _load_criteria(criteria_file).get("criteria", [])
    violations = _check_criteria(criteria, workflows)

    if violations:
        print(f"❌ CI contract violations found ({len(violations)}):")
        for v in violations:
            print(f"  • {v}")
    else:
        print(f"✅ CI contract valid: {len(criteria)} criteria verified.")
    return violations, False


def _load_criteria(criteria_file: Path) -> dict:
    """Load the criteria document, coalescing an empty file to ``{}``."""
    return yaml.safe_load(criteria_file.read_text(encoding="utf-8")) or {}


def _check_criteria(criteria, workflows):
    violations = []
    for criterion in criteria:
        cid = criterion.get("id", "unknown")
        gates = criterion.get("gates")
        if not gates:
            if criterion.get("asserted_by"):
                violations.append(f"{cid}: asserted_by names something but there is no `gates` block")
            continue
        if FRESHNESS_KEY not in criterion:
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
                cond = str(job.get("if") or "")
                if cond.strip() in {"false", "${{ false }}"}:
                    violations.append(f"{cid}: {wf}:{job_id} is hard-disabled")
                if blocking and job.get("continue-on-error"):
                    violations.append(f"{cid}: blocking gate {wf}:{job_id} has continue-on-error")
                if verdict_step:
                    step_names = [s.get("name") for s in (job.get("steps") or []) if s.get("name")]
                    if verdict_step not in step_names:
                        violations.append(f"{cid}: {wf}:{job_id} has no step named {verdict_step!r}")
    return violations


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Verify the CI contract in green-criteria.yml.")
    parser.add_argument("--criteria-path", default=os.environ.get("CRITERIA_PATH", DEFAULT_CRITERIA_PATH))
    parser.add_argument("--workflows-dir", default=os.environ.get("WORKFLOWS_DIR", DEFAULT_WORKFLOWS_DIR))
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    violations, _skipped = validate_ci_contract(args.criteria_path, args.workflows_dir)
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
