# Observability

Observability assessment and stack guidelines for the `tuna-os/.github`
org defaults repository.

This repo does not build a product; its output is policies, composite
actions, and reusable workflows that other repositories `uses:` and consume.
"Observability" here therefore means something narrower than it would for a
service: **can you tell when one of those artifacts misbehaves, and can you
trace why?** This document records the current assessment, states what the
stack is and — just as importantly — what it deliberately is not, and gives
concrete guidance for the two things this repo *does* control: the logging
of its scripts and the diagnostics of its workflows.

## Scope

- This repo's own telemetry posture and the guidelines that go with it.
- Structured logging for scripts under `.github/` and `scripts/`.
- Diagnostics for the workflows and actions under `.github/`.

It does **not** cover observability inside the consumer repositories that use
these workflows and actions. When a caller repo wants metrics on its own
build, that is that repo's decision and belongs in its own docs.

## Assessment

The audit behind this issue found the following.

### 1. No external backend is configured — and none is warranted

No OpenTelemetry exporter, Prometheus server, or OTLP collector is wired into
this repo. That is the correct state, not a gap to fill:

- There are no in-product signals to export. This repo ships configuration
  and CI, not a running service with request latency, error rates, or
  queue depth.
- There are no SLOs on a user-facing endpoint, so there is no dashboard a
  missing data point would leave blind.
- There is no consumer of a metrics endpoint. A backend with nothing to feed
  it is maintenance cost with no return.

If a metrics backend is ever added, the guideline is **opt-in per consumer
repo, documented there, never org-wide here.** This repo's job is to stay
observable to its own consumers, not to export numbers nobody reads.

### 2. The execution boundary is GitHub Actions

Everything in this repo runs as a GitHub Actions job. The logs, status
checks, and run history that GitHub produces **are** the observability
surface. The rest of this document is about making that surface as
diagnosable as possible, because it is the only one this repo has.

### 3. The repo already ships its own diagnostics

This is the telemetry this repo actually has, and it should stay healthy:

| Artifact | What it makes observable | Where |
|---|---|---|
| Renovate automerge policy check | A repo's `renovate.json` is not silently automerging `major` updates | `scripts/check-renovate-automerge-policy.py`, `renovate-policy-check.yml` |
| STE prose linter | Prose findings held to a ratcheting budget | `.github/actions/ste-lint/`, `ste-lint.yml` |
| CI contract verification | Every green criterion is asserted by a reachable workflow/job/step | `reusable-ci-contract.yml` (+ `.github/green-criteria.yml` when present) |
| Flatpak tooling drift check | A copied `update-index.py` has diverged from the canonical action copy | `flatpak-tooling-drift-check.yml` |
| Coverage gating | Project and patch coverage targets | `codecov.yml` (project 45%, patch 70%) |

## Stack guidelines

Given the assessment, the stack is: **GitHub Actions logs and status checks,
with exit codes as the machine signal and structured text as the human
signal.** No metrics backend.

- **Primary channel: logs + status checks.** A failure shows as a red check
  and a log; that is the whole surface. Design for it.
- **Secondary channel: Codecov.** Coverage is the one numeric gate this repo
  carries. Keep the project/patch targets in `codecov.yml` meaningful.
- **Deliberately not in scope: metrics/trace/backend.** Adding one here would
  create an exporter with no data and a dashboard with no readers. If a
  consumer repo needs it, implement it in that repo.

## Structured logging guidance for scripts

Scripts in this repo are the machine-facing half of observability: CI and
humans read their output to decide pass/fail and to debug. Two scripts set
the convention — `check-renovate-automerge-policy.py` and
`ste-lint.mjs` — and new scripts should follow them.

1. **Signal on exit code, not only on text.** The exit code is the
   machine-readable verdict; the text is the human-readable reason. Keep them
   in lockstep.
   - `check-renovate-automerge-policy.py`: `0` compliant, `1` violation (or
     the file could not be read/parsed).
   - `ste-lint.mjs`: `1` when the finding count exceeds the `--max` budget.
2. **Use stable, greppable prefixes.** Lines that carry a verdict start with a
   fixed token — `ERROR:`, `FAIL:`, `OK:` — so a failure is findable in a
   long log and greppable in automation.
3. **Route diagnostics to stderr, results to stdout.** Errors and failures go
   to `stderr`; the normal result line goes to `stdout`. This keeps the two
   streams separable for both humans and CI.
4. **Name every skip, never let a total move silently.** `ste-lint.mjs`
   prints each opted-out file with its reason and lists every generated tree
   it skipped, so the reported total is the whole total — a total that moves
   without explanation is exactly how a suppressed finding hides. New scripts
   that skip work must say what they skipped and why.
5. **Hold a budget and ratchet it.** `ste-lint`'s `--max` lets CI hold a
   finding count and drift it down over time rather than demanding perfection
   on day one. Scripts that accumulate findings should expose the same knob.
6. **Keep inputs as data, not code.** This is the same property that makes a
   log trustworthy. `update-flatpak-index/action.yml` routes every input
   through `env:` rather than `${{ }}` interpolation, precisely so an
   interpolated value cannot be parsed as shell (`AGENTS.md`). A script that
   trusts its inputs as data produces output you can reason about; a script
   that interpolates them produces output that can lie.

## CI workflow diagnostics guidance

Workflows and actions are the shared surface: a merge to `main` is live for
every caller at their next run, because callers pin `@main`. That blast
radius (`AGENTS.md`) is itself an observability concern — a bad change shows
up everywhere at once, often silently. Make new workflows diagnosable.

1. **Trace a failure top-down.** Status check → workflow run → job → step.
   Give each job and each meaningful step a `name:` so the run view is
   navigable without opening the YAML.
2. **Be deliberate with `if:` and `continue-on-error`.** A blocking gate
   must never carry `continue-on-error`, or its failure is swallowed. The CI
   contract verification explicitly checks for this (`reusable-ci-contract.yml`).
3. **Keep workflows reachable from an active trigger.** A workflow that
   nothing fires is unobservable dead code. The CI contract checks that
   every gated workflow is reachable from an active trigger (`push`,
   `pull_request`, `schedule`, and similar). Add that trigger when you add a
   workflow.
4. **Reusable workflows and actions are the high-blast-radius half.** Other
   repos consume anything under `.github/workflows/` with `workflow_call`,
   and everything under `.github/actions/`. Name their inputs and steps, and
   fail loudly on bad input. Treat a change to them as a change made
   everywhere at once.
5. **Let the self-checks stay green.** The drift check has been failing on
   scheduled runs since 2026-08-17 (`AGENTS.md`). A diagnostic that is
   already red teaches nobody anything. Treat it as known backlog, not new
   noise.

## Known gaps

- **Drift check is red.** `flatpak-tooling-drift-check.yml` has failed on
  every scheduled run since 2026-08-17. Its repo list is also not the set of
  repos that carry a copied `update-index.py`. It is an interim guard, not a
  finished one.
- **CI contract is inert until a criteria file lands.**
  `reusable-ci-contract.yml` verifies `.github/green-criteria.yml` *when
  present*. That file is not on the default branch, so the check now skips.
  Activate it once a team writes criteria.
- **No per-repo metrics.** By design. If a consumer repo needs them, that
  work lives in that repo, not here.

## References

- Issue: [tuna-os/.github#60](https://github.com/tuna-os/.github/issues/60)
- Automerge policy: [tuna-os/.github#12](https://github.com/tuna-os/.github/issues/12) (incidents tunaOS#1612, tunaOS#1636)
- Repo policy and blast-radius notes: `AGENTS.md`
- Contributing and commit conventions: `CONTRIBUTING.md`
