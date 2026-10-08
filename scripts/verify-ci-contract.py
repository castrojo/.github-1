#!/usr/bin/env python3
"""Verify that every green-criteria gate is asserted by a reachable workflow.

This is the engine that used to live inline in
.github/workflows/reusable-ci-contract.yml (embedded in a YAML `run:` heredoc).
Embedding it in YAML made it untestable: a change to graph reachability, trigger
parsing, or the blocking-gate checks could only be exercised by running the
workflow in a consumer repository. Extracting it here gives it a stable command
boundary so it can be imported and unit-tested (see
test-verify-ci-contract.py) before it ships to every @main consumer.

The CLI reads the same two inputs the workflow passed through environment
variables (CRITERIA_PATH, WORKFLOWS_DIR) and prints the same text, so consumer
behaviour is unchanged -- only the location of the code moved.

Usage:
    verify-ci-contract.py                # uses CRITERIA_PATH/WORKFLOWS_DIR env,
                                         # or the defaults below
    CRITERIA_PATH=... WORKFLOWS_DIR=... verify-ci-contract.py

Exit codes:
    0  contract valid (or no criteria file to check -- skipped)
    1  the workflows directory is missing, or a gate workflow fails its checks
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Iterable

import yaml

# Triggers that make a workflow "active" for reachability: something that can
# actually start it without a human reaching for the Run button.
ACTIVE_TRIGGERS = {"schedule", "push", "pull_request", "merge_group", "workflow_run", "release"}


def load_workflows(directory: Path) -> dict[str, dict]:
    """Parse every workflow in *directory*, keyed by both its path and basename.

    Keyed two ways on purpose: a criterion's `gate.workflow` may name the file
    with a leading path (`.github/workflows/foo.yml`) or bare (`foo.yml`), and
    the verifier must find it either way.
    """
    docs: dict[str, dict] = {}
    for f in sorted(list(directory.glob("*.yml")) + list(directory.glob("*.yaml"))):
        doc = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        docs[f"{directory}/{f.name}"] = doc
        docs[f.name] = doc
    return docs


def triggers(doc: dict) -> dict:
    """Return the set of event names a workflow is wired to.

    Handles the three shapes YAML allows for `on`: a single string, a list of
    strings, or a mapping. Also accepts the boolean key `True`, which is how
    PyYAML renders an unquoted `on:` (it is a truthy scalar).
    """
    on = doc.get("on", doc.get(True, {}))
    if isinstance(on, str):
        return {on: None}
    if isinstance(on, list):
        return {k: None for k in on}
    return on or {}


def callers(workflows: dict[str, dict]) -> dict[str, set[str]]:
    """Map each reusable workflow (by relative `./path`) to the callers that use it."""
    out: dict[str, set[str]] = {}
    for name, doc in workflows.items():
        for job in (doc.get("jobs") or {}).values():
            uses = (job or {}).get("uses", "")
            if isinstance(uses, str) and uses.startswith("./"):
                out.setdefault(uses[2:], set()).add(name)
    return out


def is_reachable(name: str, workflows: dict[str, dict], _seen: set[str] | None = None) -> bool:
    """True if *name* is reachable from an active trigger, following `uses:` edges.

    Depth-first with a visited set: a cycle in the reuse graph must not loop
    forever, and a node already explored cannot become reachable just because a
    second path reaches it.
    """
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


def check(criteria: Iterable[dict], workflows: dict[str, dict]) -> list[str]:
    """Return the list of contract violations, empty when the contract holds.

    Pure and side-effect free so tests can drive it with in-memory fixtures:
    *criteria* is the list of criterion dicts from green-criteria.yml,
    *workflows* is the mapping produced by :func:`load_workflows`.
    """
    violations: list[str] = []

    for criterion in criteria:
        cid = criterion.get("id", "unknown")
        gates = criterion.get("gates")
        if not gates:
            if criterion.get("asserted_by"):
                violations.append(
                    f"{cid}: asserted_by names something but there is no `gates` block"
                )
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
                cond = str(job.get("if") or "")
                if cond.strip() in {"false", "${{ false }}"}:
                    violations.append(f"{cid}: {wf}:{job_id} is hard-disabled")
                if blocking and job.get("continue-on-error"):
                    violations.append(f"{cid}: blocking gate {wf}:{job_id} has continue-on-error")
                if verdict_step:
                    step_names = [
                        s.get("name") for s in (job.get("steps") or []) if s.get("name")
                    ]
                    if verdict_step not in step_names:
                        violations.append(
                            f"{cid}: {wf}:{job_id} has no step named {verdict_step!r}"
                        )

    return violations


def main() -> int:
    criteria_path = Path(os.environ.get("CRITERIA_PATH", ".github/green-criteria.yml"))
    workflows_dir = Path(os.environ.get("WORKFLOWS_DIR", ".github/workflows"))

    if not criteria_path.is_file():
        print(f"No criteria file at {criteria_path}; skipping CI contract verification.")
        return 0

    if not workflows_dir.is_dir():
        print(f"No workflows directory at {workflows_dir}.")
        return 1

    raw = yaml.safe_load(criteria_path.read_text(encoding="utf-8")) or {}
    criteria = raw.get("criteria", [])
    workflows = load_workflows(workflows_dir)

    violations = check(criteria, workflows)
    if violations:
        print(f"❌ CI contract violations found ({len(violations)}):")
        for v in violations:
            print(f"  • {v}")
        return 1

    print(f"✅ CI contract valid: {len(criteria)} criteria verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
