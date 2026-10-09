# Reusable Workflows

TunaOS ships a set of organization-wide **reusable workflows** (`on: workflow_call`)
that standardize CI/CD, security, and contributor-engagement patterns across every
repo in the org. This document lists each one, says when to use it, shows how to
call it, and records its inputs and outputs.

> **Do not fork these.** Each workflow is a public API — callers pin `@main`, so a
> change in this repo is live for every consuming repo on its next run (see
> [`AGENTS.md`](./AGENTS.md)). If a workflow needs a new capability, add an input
> here rather than copying the file into a repo.

## Workflow overview

| Workflow file | One line | Use when… | Hive practice |
|---|---|---|---|
| [`reusable-ci-contract.yml`](.github/workflows/reusable-ci-contract.yml) | Verifies every green criterion in `.github/green-criteria.yml` is asserted by a reachable workflow. | You want a machine-checkable contract that the CI gates you promised actually run. | #1 (epic #2250, issue #2260) |
| [`reusable-lint.yml`](.github/workflows/reusable-lint.yml) | Matrix of static-analysis checks: shellcheck, yamllint, json-validate, actionlint, justfmt. | You need cross-language lint gates (shell, YAML/JSON, Actions, Justfiles). | #14 (epic #2250, issue #2260) |
| [`ste-lint.yml`](.github/workflows/ste-lint.yml) | Simplified Technical English prose check for docs. | You have README / CONTRIBUTING / guide prose that must stay readable and unambiguous. | — |
| [`reusable-fork-safety.yml`](.github/workflows/reusable-fork-safety.yml) | Verifies `pull_request` workflows survive fork execution (permissions, `pull_request_target`, secret/write guarding). | Your CI runs privileged resources (QEMU, KVM) or touches secrets and must be safe on untrusted fork code. | #13 (epic #2250, issue #2260) |
| [`reusable-scorecard.yml`](.github/workflows/reusable-scorecard.yml) | OpenSSF Scorecard supply-chain security analysis → SARIF → code scanning. | You want SLSA / supply-chain security posture tracked and shown in code scanning. | #10 (epic #2250, issue #2260) |
| [`reusable-lint.yml`](.github/workflows/reusable-lint.yml) + [`ste-lint.yml`](.github/workflows/ste-lint.yml) | (combo) Lint + STE prose. | Documentation-heavy repo that needs both syntax and prose gates. | — |
| [`reusable-first-contributor.yml`](.github/workflows/reusable-first-contributor.yml) | Greets first-time contributors on issues and PRs. | You want to reduce friction for new contributors. | (epic #2250, issue #2260) |
| [`reusable-pr-nudges.yml`](.github/workflows/reusable-pr-nudges.yml) | Advisory reminders for stalled PRs, derived from the files they touch. Never fails a PR. | You want to keep review momentum without pinging with a hard gate. | #11 (epic #2250, issue #2260) |
| [`reusable-add-help-wanted.yml`](.github/workflows/reusable-add-help-wanted.yml) | Adds a `help wanted` label to unassigned issues carrying `help wanted` / `good first issue`. | You want unassigned help-wanted issues to be easy to find. | (epic #2250, issue #2260) |

The first seven rows are the core engineering gates; the last four are community and
engagement. Most repos only need the CI contract, lint, and (for docs) STE.

## How to integrate

A reusable workflow is called like any action, with `uses:` pointing at its path in
this repo. Callers keep their own `on:` trigger and become a thin job:

```yaml
on:
  pull_request:
  push:
    branches: [main]

jobs:
  ci:
    uses: tuna-os/.github/.github/workflows/reusable-ci-contract.yml@main
```

Notes:

- **Path.** `.github/workflows/<name>.yml@main`. Pin `@main`; this repo has no
  version to hold you back and callers merge live immediately.
- **`with:` passes inputs, `secrets: inherit` forwards secrets.** See the table below
  for which inputs exist and their defaults.
- **One job per workflow.** Each `workflow_call` is a single job; call it once per
  concern rather than nesting.
- **`ste-lint` keeps its own `on:`.** It is designed to be wrapped: your repo keeps a
  normal trigger and `uses:` it as a thin job (see the STE pattern below).

### Per-workflow integration

**CI contract** — requires `.github/green-criteria.yml` to exist; the check skips
silently if it does not.

```yaml
jobs:
  ci-contract:
    uses: tuna-os/.github/.github/workflows/reusable-ci-contract.yml@main
```

**Lint** — runs every check in the default matrix. Trim the matrix if a repo does not
have that file type:

```yaml
jobs:
  lint:
    uses: tuna-os/.github/.github/workflows/reusable-lint.yml@main
    with:
      checks: '["shellcheck", "yamllint"]'
```

**Simplified Technical English** — keep the caller's trigger and wrap the workflow:

```yaml
jobs:
  ste:
    uses: tuna-os/.github/.github/workflows/ste-lint.yml@main
    with:
      budget-file: .ste-budget
```

Seed `.ste-budget` with the honest current count, not zero — the budget only ever
decreases, and a gate that fails on day one gets disabled on day two:

```bash
node .github/actions/ste-lint/ste-lint.mjs --summary
```

**Fork safety** — put this job ahead of any privileged job so a fork cannot run it
before approval:

```yaml
jobs:
  fork-safety:
    uses: tuna-os/.github/.github/workflows/reusable-fork-safety.yml@main

  qemu-tests:
    needs: fork-safety
    if: always()
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - run: just qemu-tests
```

**Scorecard** — uploads a SARIF to code scanning. Pass `publish-results: true` only
if you also want the results sent to the OpenSSF REST API.

```yaml
jobs:
  scorecard:
    uses: tuna-os/.github/.github/workflows/reusable-scorecard.yml@main
    with:
      publish-results: false
```

**First-contributor greetings** — no inputs needed; the defaults are already friendly.

```yaml
jobs:
  first-contributor:
    uses: tuna-os/.github/.github/workflows/reusable-first-contributor.yml@main
```

**PR nudges** — runs the caller's nudge script. Point `script-path` at your own if it
lives somewhere other than the default:

```yaml
jobs:
  pr-nudges:
    uses: tuna-os/.github/.github/workflows/reusable-pr-nudges.yml@main
    with:
      script-path: .github/scripts/pr-nudges.sh
    secrets: inherit
```

**Add help wanted** — no inputs; wires to the `issues` trigger automatically.

```yaml
on:
  issues:
    types: [labeled]

jobs:
  add-help-wanted:
    uses: tuna-os/.github/.github/workflows/reusable-add-help-wanted.yml@main
```

## Input / output reference

Extracted from each workflow's `on.workflow_call` schema. None of these workflows
declare `outputs:`; they report results via exit status, a step summary, an
annotation, or a comment, depending on the workflow.

| Workflow | Input | Type | Default | Meaning |
|---|---|---|---|---|
| `reusable-ci-contract` | `criteria-path` | string | `.github/green-criteria.yml` | Where the green-criteria contract lives. |
| | `workflows-dir` | string | `.github/workflows` | Directory scanned for reachable workflows. |
| | `python-version` | string | `"3.11"` | Python for the verification script. |
| `reusable-lint` | `checks` | string (JSON array) | `["shellcheck","yamllint","json-validate","actionlint","justfmt"]` | Which matrix checks to run. |
| `ste-lint` | `budget-file` | string | `.ste-budget` | File holding the max tolerated findings. |
| | `budget` | string | `""` | Budget to use when `budget-file` is absent. |
| | `node-version` | string | `"24"` | Node runtime for the linter. |
| | `run-tests` | boolean | `true` | Run the linter's own test suite. |
| | `runs-on` | string | `ubuntu-latest` | Runner for the job. |
| | `checkout-ref` | string | `""` | Ref to check out; empty means the triggering ref. |
| `reusable-first-contributor` | `pr_message` | string | (friendly default) | Comment posted to first-time PR authors. |
| | `issue_message` | string | (friendly default) | Comment posted to first-time issue authors. |
| `reusable-fork-safety` | `workflows-dir` | string | `.github/workflows` | Directory scanned for fork-unsafe workflows. |
| | `python-version` | string | `"3.11"` | Python for the verification script. |
| `reusable-pr-nudges` | `script-path` | string | `.github/scripts/pr-nudges.sh` | Nudge script in the caller repo. |
| | `token` *(secret)* | secret | `GITHUB_TOKEN` | Token used to post the PR comment. |
| `reusable-scorecard` | `publish-results` | boolean | `false` | Also publish to the OpenSSF REST API. |
| `reusable-add-help-wanted` | — | — | — | No inputs. |

## Secrets and permissions

| Workflow | Top-level `permissions` | Extra job scopes | Secrets |
|---|---|---|---|
| `reusable-ci-contract` | `contents: read` | — | none |
| `reusable-lint` | `contents: read` | — | none |
| `ste-lint` | *(inherited from caller)* | — | none |
| `reusable-fork-safety` | `contents: read` | — | none |
| `reusable-scorecard` | `contents: read` | `security-events: write`, `id-token: write`, `actions: read` | none (optional `publish-results`) |
| `reusable-first-contributor` | `contents: read` | `issues: write`, `pull-requests: write` | none |
| `reusable-pr-nudges` | `contents: read`, `pull-requests: write` | — | `token` (optional) |
| `reusable-add-help-wanted` | `contents: read` | `issues: write` | none |

Forward organization secrets to a reusable workflow with `secrets: inherit`. Minimize
secrets visible to fork PRs — `reusable-fork-safety.yml` exists precisely to catch a
workflow that leaks them.

## Related

- [`AGENTS.md`](./AGENTS.md) — why a change here lands everywhere at once; the impact
  model for editing any file under `.github/`.
- [`CONTRIBUTING.md`](./CONTRIBUTING.md) — how to contribute to TunaOS and where these
  gates fit in a workflow.
- Epic #2250, issue #2260 — the Hive practices each workflow adopts.
- Issue [#140](https://github.com/tuna-os/.github/issues/140) — the request that produced this index.
