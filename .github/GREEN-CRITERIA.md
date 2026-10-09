# Green Criteria / CI Contract

This document describes the **CI Contract** pattern used across tuna-os
repositories and how to adopt it. The pattern is Hive practice #1 (epic #2250,
issue #2260) and is enforced by the org-level reusable workflow
[`.github/workflows/reusable-ci-contract.yml`](.github/workflows/reusable-ci-contract.yml).

## What it is

Every repository has a handful of **green criteria** — the things that must be
true for CI to count as green. Examples:

- the linter passes,
- the STE (Simplified Technical English) prose check passes,
- the flatpak tooling drift check reports no drift,
- the renovate automerge policy is intact.

A green criterion is only meaningful if something actually *verifies* it, and
that something is still running and fresh. The CI Contract turns "we have a
lint gate" into a testable claim:

> For every green criterion, there is a reachable workflow with a real job and
> step that asserts it, and that workflow has run within its freshness SLA.

`.github/green-criteria.yml` is the list of claims.
`reusable-ci-contract.yml` checks that the claims are backed by real, reachable,
fresh workflows. If the two drift out of sync, the contract check fails — so the
documentation can never quietly lie about what CI actually enforces.

### Why it matters

- **No unverifiable claims.** A criterion with no backing workflow is a promise
  nobody keeps. The contract fails loudly instead of letting a criterion rot.
- **No dead workflows.** A workflow that no criterion references is orphaned
  tooling that still burns CI minutes. The contract fails it the same way.
- **No stale checks.** A gate that has not run since the code it guards changed
  is a false "green". The `freshness_sla_days` field turns "did this run
  recently?" into a hard requirement.
- **Onboarding.** A new maintainer learns exactly what green means and how each
  piece is enforced, from one file.

## Authoring `green-criteria.yml`

The file is a single top-level `criteria:` list. Each entry names one green
criterion and the workflow(s) that assert it.

```yaml
# .github/green-criteria.yml
criteria:
  - id: renovate-automerge-policy
    gates:
      - workflow: .github/workflows/renovate-policy-check.yml
        jobs:
          check: "Check Renovate automerge policy"
    freshness_sla_days: 7
    enforcement: blocking
    asserted_by: >-
      The Renovate automerge policy is enforced by
      .github/workflows/renovate-policy-check.yml, which runs on every push and
      pull_request to main and fails the build when a layered packageRule would
      automerge a major or minor update.
  - id: flatpak-tooling-drift
    gates:
      - workflow: .github/workflows/flatpak-tooling-drift-check.yml
        jobs:
          check-drift: "Classify each repo's flatpak index tooling"
    freshness_sla_days: 7
    enforcement: blocking
    asserted_by: >-
      Flatpak tooling drift is caught weekly by
      .github/workflows/flatpak-tooling-drift-check.yml, which classifies every
      flatpak-publishing repo as migrated, in sync, drifted, or unwired.
```

### Field reference

| Field | Where | Required | Meaning |
|---|---|---|---|
| `criteria` | top level | yes (a list) | The list of green criteria. An empty or missing list is treated as "nothing to check". |
| `id` | per criterion | recommended | Short slug; used verbatim in violation messages and PR annotations. |
| `gates` | per criterion | yes, for a real criterion | One entry per workflow that asserts this criterion. A criterion with no `gates` is silently skipped (unless it also sets `asserted_by`, which is itself a violation). |
| `gates[].workflow` | per gate | yes | Path to the workflow YAML, e.g. `.github/workflows/ste-lint.yml`. The basename (`ste-lint.yml`) must appear in `asserted_by`. |
| `gates[].jobs` | per gate | no | Map of `job_id` to an optional **verdict step name** (the `name:` of the step that makes the pass/fail decision). Omit the map to assert only at the workflow level; include it to pin the exact job and step. |
| `freshness_sla_days` | per criterion | yes, when `gates` present | Maximum age, in days, of the last successful run of the gate workflow before the criterion is considered stale. |
| `enforcement` | per criterion | no | `blocking` makes a failed gate fail the contract; anything else (e.g. `advisory`) is informational. |
| `asserted_by` | per criterion | yes, if `gates` present | Human-readable prose. Must contain the basename of every gated workflow (e.g. `renovate-policy-check.yml`). |

### Rules the contract enforces (and why)

The checker (`reusable-ci-contract.yml`) applies these checks in order. Knowing
them while authoring saves a round-trip:

1. **A `gates` block needs `freshness_sla_days`.** Without a freshness SLA a
   criterion can never go stale, which defeats the point.
2. **A workflow named in `gates` must exist** on the branch the contract runs
   on. A typo in the path is a broken claim.
3. **The workflow basename must be mentioned in `asserted_by`.** This couples the
   machine-readable gate to the human-readable rationale, so they cannot drift
   apart.
4. **The gate workflow must be reachable from an active trigger.** A workflow
   that only ever fires on `workflow_call` is not reachable on its own — it
   needs a caller workflow that triggers on `push`, `pull_request`, `schedule`,
   `release`, `merge_group`, or `workflow_run`. Reachability follows `uses: ./`
   edges transitively.
5. **Named jobs must exist.** If `jobs.check` is named, the workflow must define
   a `jobs.check`.
6. **A hard-disabled job fails.** A gate on a job whose `if: false` (or
   `${{ false }}`) is never going to run.
7. **A blocking gate may not `continue-on-error: true`.** That would let a
   blocking criterion fail silently.
8. **A verdict step name must match a real step.** If you pin `check: "Check
   Renovate automerge policy"`, that job must have a step with that exact name.

## Integrating `reusable-ci-contract.yml`

The contract is a **reusable workflow**. Your repo keeps its own `on:` trigger
and becomes a thin job that `uses:` it, exactly like the other org reusable
workflows (`ste-lint`, `reusable-lint`, `reusable-scorecard`, …).

Add a job to any workflow that already runs on an active trigger — most naturally
your existing CI workflow:

```yaml
# .github/workflows/ci.yml  (or any workflow with a push/pull_request trigger)
jobs:
  ci-contract:
    name: CI Contract Verification
    uses: tuna-os/.github/.github/workflows/reusable-ci-contract.yml@main
    # inputs are optional; the defaults match this repo's layout.
    with:
      criteria-path: .github/green-criteria.yml
      workflows-dir: .github/workflows
      python-version: "3.11"
```

Inputs (see
[reusable-ci-contract.yml](.github/workflows/reusable-ci-contract.yml) for the
full list and types):

| Input | Default | Meaning |
|---|---|---|
| `criteria-path` | `.github/green-criteria.yml` | Where the criteria file lives. |
| `workflows-dir` | `.github/workflows` | Directory scanned for the gated workflows. |
| `python-version` | `"3.11"` | Python used to run the checker. |

If `criteria-path` does not exist, the check prints
`No criteria file at …; skipping CI contract verification.` and exits 0 — so
adopting the pattern is opt-in, and the first commit in a repo is simply the
`green-criteria.yml` plus this job.

### What "green" means after you add it

- `green-criteria.yml` lists the criteria.
- Each gate points at a real, reachable workflow with a real job/step.
- The contract job passes only when every criterion is backed and fresh.

If a workflow is deleted, its criterion's `gates[].workflow` stops existing and
the contract fails. If a criterion is removed but a workflow keeps running with
nothing referencing it, that workflow is now dead CI minutes — the contract does
not flag dead workflows directly, but removing the gate makes the orphan obvious.

## Troubleshooting

The contract prints each failure as `• <id>: <message>`. The common ones:

| Message | Cause | Fix |
|---|---|---|
| `<id>: missing freshness_sla_days` | `gates` present but no `freshness_sla_days`. | Add `freshness_sla_days: <n>`. |
| `<id>: asserted_by names something but there is no \`gates\` block` | `asserted_by` set with no `gates`. | Add a `gates` block, or drop `asserted_by` if the criterion is genuinely empty. |
| `<id>: gate workflow <path> does not exist` | Typo or deleted workflow in `gates[].workflow`. | Correct the path; the file must exist on the branch. |
| `<id>: gate workflow <wf> is not mentioned in asserted_by` | The workflow basename is absent from `asserted_by` prose. | Add the basename (e.g. `ste-lint.yml`) to `asserted_by`. |
| `<id>: <wf> is not reachable from any active trigger` | The workflow only fires on `workflow_call`. | Reference it from a caller that triggers on push/pull_request/schedule, etc., or gate a different workflow. |
| `<id>: <wf> has no job '<job>'` | `jobs` maps to a job the workflow does not define. | Use the real `jobs.<id>` key, or drop that entry. |
| `<id>: <wf>:<job> is hard-disabled` | The job's `if` is `false` / `${{ false }}`. | Fix the `if` condition; a never-run job cannot assert anything. |
| `<id>: blocking gate <wf>:<job> has continue-on-error` | A blocking criterion's job swallows its own failure. | Remove `continue-on-error: true` from that job. |
| `<id>: <wf>:<job> has no step named '<step>'` | The pinned verdict step name does not match any step `name:`. | Use the exact step name from the workflow. |

### The file is missing entirely

`No criteria file at .github/green-criteria.yml; skipping CI contract verification.`
This is not a failure — the contract is a no-op until you create the file. Add
the file (copy the worked example above) and the contract job, then re-run.

### A criterion passes but the gate feels meaningless

A criterion can be "backed" yet weak — e.g. a gate that names a job but not the
verdict step, so any step passing satisfies it. Pin `jobs.<job>` to the step that
actually makes the pass/fail decision (its exit code is what CI reports), so the
claim matches reality.

## See also

- [`.github/workflows/reusable-ci-contract.yml`](.github/workflows/reusable-ci-contract.yml) — the checker; inputs, outputs, and the full check list.
- [`AGENTS.md`](../AGENTS.md) — how a change here propagates to every org repo.
