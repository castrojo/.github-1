# Adopting the org's reusable workflows

`tuna-os/.github` ships a set of **reusable workflows** (`on: workflow_call`)
that standardise CI, security, and contributor-engagement across every repo in
the org. This guide is about *composition*: which workflows to wire together for
a given kind of repo, what each one needs before it will run, and what it pulls
in.

For the per-workflow catalog — a one-line description of every workflow plus its
full `inputs:` / `outputs:` schema — see
[`.github/WORKFLOWS.md`](../.github/WORKFLOWS.md). This document assumes you have
read that and want to know how to combine the pieces.

## How a reusable workflow is called

A reusable workflow is called like any action: `uses:` points at its path in
this repo, and the caller keeps its own `on:` trigger and becomes a thin job:

```yaml
on:
  pull_request:
  push:
    branches: [main]

jobs:
  lint:
    uses: tuna-os/.github/.github/workflows/reusable-lint.yml@main
```

Three rules make this safe, and they are why the whole pattern works:

- **Pin `@main`.** This repo has no version tag to hold you back and no way to
  roll back except another commit, so a merge is live for every consuming repo
  on its next run. See [`AGENTS.md`](../AGENTS.md).
- **One job per workflow.** Each `workflow_call` is a single job; call it once
  per concern rather than nesting.
- **`with:` passes inputs; `secrets: inherit` forwards secrets.**

## Workflow overview

| Workflow | Purpose | Use when… | Prerequisite |
|---|---|---|---|
| [`reusable-ci-contract.yml`](../.github/workflows/reusable-ci-contract.yml) | Verifies every green criterion in `.github/green-criteria.yml` is asserted by a reachable, non-disabled workflow. | You want a machine-checkable promise that the CI gates you actually run. | `.github/green-criteria.yml` (optional — skips silently if absent) |
| [`reusable-lint.yml`](../.github/workflows/reusable-lint.yml) | Matrix of static-analysis checks: shellcheck, yamllint, json-validate, actionlint, justfmt. | You need cross-language lint gates. | Homebrew + the five tools (installed in-workflow) |
| [`ste-lint.yml`](../.github/workflows/ste-lint.yml) | Simplified Technical English prose check for docs. | Your README / CONTRIBUTING / guide prose must stay readable and unambiguous. | `.ste-budget` file (or a `budget` input) |
| [`reusable-fork-safety.yml`](../.github/workflows/reusable-fork-safety.yml) | Verifies `pull_request` workflows survive fork execution: explicit permissions, no `pull_request_target`, secrets/guarded write steps. | Your CI touches secrets or runs privileged resources (QEMU, KVM) and must be safe on untrusted fork code. | none |
| [`reusable-scorecard.yml`](../.github/workflows/reusable-scorecard.yml) | OpenSSF Scorecard supply-chain analysis → SARIF → code scanning. | You want SLSA / supply-chain security posture tracked in code scanning. | none (optional: publish to OpenSSF REST API) |
| [`reusable-first-contributor.yml`](../.github/workflows/reusable-first-contributor.yml) | Greets first-time contributors on issues and PRs. | You want to reduce friction for new contributors. | none |
| [`reusable-pr-nudges.yml`](../.github/workflows/reusable-pr-nudges.yml) | Advisory reminders for a PR, derived from the files it touches. Never fails a PR. | You want to keep review momentum without a hard gate. | `.github/scripts/pr-nudges.sh` (skips if absent) + a token to comment |
| [`reusable-add-help-wanted.yml`](../.github/workflows/reusable-add-help-wanted.yml) | Labels unassigned issues carrying `help wanted` / `good first issue`. | You want help-wanted issues easy to find. | none |

The first five are the engineering gates; the last three are community and
engagement. Most repos only need the CI contract, lint, and (for docs) STE.

## Prerequisites and secrets

Every workflow declares `contents: read` at minimum and installs its own
dependencies, so none of them require a `pip install` or `brew install` in the
caller. What they do need *before* you wire them in:

| Workflow | Top-level `permissions` | Extra job scopes | Secrets needed |
|---|---|---|---|
| `reusable-ci-contract` | `contents: read` | — | none |
| `reusable-lint` | `contents: read` | — | none |
| `ste-lint` | *(inherited from caller)* | — | none |
| `reusable-fork-safety` | `contents: read` | — | none |
| `reusable-scorecard` | `contents: read` | `security-events: write`, `id-token: write`, `actions: read` | none (needs `id-token` only to publish) |
| `reusable-first-contributor` | `contents: read` | `issues: write`, `pull-requests: write` | none |
| `reusable-pr-nudges` | `contents: read`, `pull-requests: write` | — | `token` (optional; defaults to `GITHUB_TOKEN`) |
| `reusable-add-help-wanted` | `contents: read` | `issues: write` | none |

Notes:

- **`ste-lint` needs a budget.** Create `.ste-budget` holding the repo's current
  finding count (seed it honestly, not zero — a gate that fails on day one gets
  disabled on day two). The linter only ever decreases the budget.
- **`reusable-pr-nudges` runs the caller's script.** It sparse-checks out
  `.github/scripts/pr-nudges.sh`; if that file is absent the job skips cleanly.
  Pass `secrets: inherit` (or a `token`) only if you want the PR comment; the
  step-summary reminders work on any token.
- **`reusable-scorecard`'s `publish-results: true`** sends results to the
  OpenSSF REST API. Leave it `false` (the default) unless you want that export;
  the SARIF still uploads to code scanning either way.

## Integration patterns

### CI-only (minimal)

The smallest useful setup is lint plus a CI contract. This is close to what
`project-starter/.github/workflows/ci.yml` ships by hand (`just check`, a
Renovate-policy check, a workflow-permissions check, and a `required-checks`
gating job) — but expressed on the shared workflows:

```yaml
on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  lint:
    uses: tuna-os/.github/.github/workflows/reusable-lint.yml@main

  ci-contract:
    uses: tuna-os/.github/.github/workflows/reusable-ci-contract.yml@main
```

Keep the `renovate-policy` and `workflow-permissions` jobs from the starter if
the repo manages Renovate or ships its own workflows — the shared workflows do
not cover them. Add `reusable-fork-safety` (below) once any job touches secrets.

### Documentation-heavy

Add STE prose checking on top of lint, and seed the budget so the gate does not
fail on the first run:

```yaml
jobs:
  lint:
    uses: tuna-os/.github/.github/workflows/reusable-lint.yml@main

  ste:
    uses: tuna-os/.github/.github/workflows/ste-lint.yml@main
    with:
      budget-file: .ste-budget
```

```bash
# Seed the budget once, then commit it:
node .github/actions/ste-lint/ste-lint.mjs --summary > .ste-budget
```

Pair it with the capture-then-publish evidence pattern from
`project-starter/.github/workflows/docs-artifacts.yml`: test the product, retain
the evidence, and let a docs-side workflow import the newest successful
artifacts — so the guide regenerates instead of going stale.

### Flatpak app

A Flatpak app builds in a privileged QEMU/KVM container and publishes to GHCR,
so it is the one profile that must prove it is fork-safe *before* any privileged
job runs. Put fork safety first and have the privileged job `needs:` it:

```yaml
jobs:
  fork-safety:
    uses: tuna-os/.github/.github/workflows/reusable-fork-safety.yml@main

  publish:
    needs: fork-safety
    if: always() && needs.fork-safety.result == 'success'
    # The org's Flatpak publisher is itself reusable. Keep the trigger policy in
    # the caller (tags-only, main+tags, PR-gated, …) and forward the index token:
    uses: tuna-os/.github/.github/workflows/publish-flatpak.yml@main
    secrets: inherit
    with:
      app-id: org.tunaos.finupdate
      manifest-path: build-aux/org.tunaos.finupdate.yml
      repo-name: tuna-os/finupdate
```

The privileged QEMU/KVM job never runs on a fork (fork-safety gates it, and the
starter constrains it to the trusted owner with `if: github.repository == …`),
and secrets such as `FLATPAK_INDEX_TOKEN` stay off untrusted runs. Add
`reusable-scorecard` for supply-chain posture and `reusable-lint` for the repo's
own scripts. See `project-starter/docs/ADOPTING.md` for the two-stage remote
pattern and its credential boundaries.

### Community-first

Engagement workflows never block a build; add them alongside CI to welcome
contributors and keep PRs moving:

```yaml
on:
  pull_request:
  issues:
    types: [labeled]

jobs:
  first-contributor:
    uses: tuna-os/.github/.github/workflows/reusable-first-contributor.yml@main

  pr-nudges:
    uses: tuna-os/.github/.github/workflows/reusable-pr-nudges.yml@main
    secrets: inherit

  add-help-wanted:
    # Caller supplies the `issues` trigger above; this labels unassigned
    # issues that carry a `help wanted` / `good first issue` label.
    uses: tuna-os/.github/.github/workflows/reusable-add-help-wanted.yml@main
```

## Cross-references

- [`AGENTS.md`](../AGENTS.md) — the impact model: why a change to any reusable
  workflow lands everywhere at once, and why callers pin `@main`.
- [`.github/WORKFLOWS.md`](../.github/WORKFLOWS.md) — the catalog: every
  workflow's one-line description and full input/output schema.
- [`project-starter/`](../project-starter/) — the template copied into new repos.
  Its `ci.yml`, `docs-artifacts.yml`, and `flatpak-remote.yml` are the reference
  implementations of the CI-only, documentation, and Flatpak patterns above; its
  `docs/ADOPTING.md` explains the baseline and the remote pattern.
- [`CONTRIBUTING.md`](../CONTRIBUTING.md) — how to contribute, where these gates
  fit, and the DCO sign-off requirement.
