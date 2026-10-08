# Shared CI & Actions Guide

The [`tuna-os/.github`](https://github.com/tuna-os/.github) repo holds the
workflows and composite actions that tuna-os repos adopt instead of writing
their own CI from scratch. This guide is the single place to answer "which
tool exists, and what is it for?" — it lists every reusable workflow and
action, says when to use each, shows how they compose, and covers the
prerequisites and common errors. Each tool has a detailed README that this
guide links to.

## How repos consume these

Callers reference the tools by path and pin them to `@main`:

```yaml
# A reusable workflow becomes a thin job:
jobs:
  lint:
    uses: tuna-os/.github/.github/workflows/reusable-lint.yml@main

# A composite action becomes a step:
steps:
  - uses: tuna-os/.github/.github/actions/ste-lint@main
    with:
      budget-file: .ste-budget
```

Because every caller pins `@main`, **a merge in this repo is live for all
callers at their next run** — there is no version to hold a consumer back and
no way to roll back except another commit. Treat `publish-flatpak.yml`'s
inputs, each action's `inputs:` block, and each workflow's `secrets:` block as
a public API: renaming one, or changing what a default means, breaks callers
silently at their next run.

Two things are load-bearing and worth stating up front:

- Inputs that reach a script body must travel through `env:`, never
  `${{ }}` interpolation (the composite actions do this deliberately — see
  `../.github/actions/update-flatpak-index/README.md`).
- Fork PRs get a read-only token and empty secrets. Anything that writes or
  reads a secret must be guarded by a same-repository condition.

## Inventory

### Reusable workflows (`workflow_call`)

These are invoked as jobs by a caller's own workflow. The caller keeps its own
`on:` trigger block; this workflow only defines the `jobs:`.

| Workflow | File | One-line purpose |
| --- | --- | --- |
| CI Contract Verification | [`reusable-ci-contract.yml`](../.github/workflows/reusable-ci-contract.yml) | Asserts every criterion in `.github/green-criteria.yml` is actually exercised by reachable workflows/jobs/steps and meets freshness SLAs. |
| Fork Safety Checks | [`reusable-fork-safety.yml`](../.github/workflows/reusable-fork-safety.yml) | Statically verifies every `pull_request` workflow survives execution from a fork. |
| Lint | [`reusable-lint.yml`](../.github/workflows/reusable-lint.yml) | Runs shellcheck / yamllint / json-validate / actionlint / justfmt as a matrix. |
| Scorecard | [`reusable-scorecard.yml`](../.github/workflows/reusable-scorecard.yml) | OpenSSF Scorecard supply-chain analysis → SARIF → repo code scanning. |
| PR Reminders | [`reusable-pr-nudges.yml`](../.github/workflows/reusable-pr-nudges.yml) | Advisory reminders derived from the files a PR touches. Never fails a PR. |
| First Contributor Greetings | [`reusable-first-contributor.yml`](../.github/workflows/reusable-first-contributor.yml) | Greets first-time contributors on issues and PRs. |
| Add Help Wanted Label | [`reusable-add-help-wanted.yml`](../.github/workflows/reusable-add-help-wanted.yml) | Adds `help wanted` to unassigned issues that carry a help label. |
| Publish Flatpak | [`publish-flatpak.yml`](../.github/workflows/publish-flatpak.yml) | Build → GHCR → central index pipeline for a flatpak app. Callers keep their own trigger. |
| Simplified Technical English | [`ste-lint.yml`](../.github/workflows/ste-lint.yml) | Checks Markdown prose against ASD-STE100 with a per-repo budget. |

### Org-hygiene workflows (direct triggers)

These run on their own schedule/events, not via `workflow_call`. A repo adopts
them by copying the workflow file into its own `.github/workflows/`.

| Workflow | File | One-line purpose |
| --- | --- | --- |
| Renovate Automerge Policy Check | [`renovate-policy-check.yml`](../.github/workflows/renovate-policy-check.yml) | Fails the build if `renovate.json` would automerge a `major`/`minor` update (even via rule layering). |
| Drop Bot Review Requests | [`drop-bot-review-requests.yml`](../.github/workflows/drop-bot-review-requests.yml) | Drops auto-requested reviewers on bot-authored PRs so dependency bumps stop pinging humans. |
| Flatpak Tooling Drift Check | [`flatpak-tooling-drift-check.yml`](../.github/workflows/flatpak-tooling-drift-check.yml) | Weekly guard that a repo's byte-copied `update-index.py` has not diverged from canonical. |

### Composite actions

| Action | File | One-line purpose |
| --- | --- | --- |
| update-flatpak-index | [`.github/actions/update-flatpak-index/`](../.github/actions/update-flatpak-index/) | Canonical `update-index.py`: reads a local OCI layout and updates the central index's static file. |
| publish-flatpak-index | [`.github/actions/publish-flatpak-index/`](../.github/actions/publish-flatpak-index/) | Wraps `update-flatpak-index` with a clone/commit/push to `tuna-os/docs`, retrying against concurrent writers. |
| ste-lint | [`.github/actions/ste-lint/`](../.github/actions/ste-lint/) | The STE prose linter and its rule tests; travels with the caller so no repo carries a copy to drift. |

## Selection: which tool for what

- **"I want baseline PR checks."** → `reusable-lint.yml` (format + static
  analysis) plus `reusable-fork-safety.yml` (make sure those checks survive
  forks). Nothing to configure.
- **"I want to prove my CI actually tests what I claim."** →
  `reusable-ci-contract.yml`. Requires a `.github/green-criteria.yml` first
  (see prerequisites).
- **"I want supply-chain security scoring."** → `reusable-scorecard.yml`.
- **"I want to keep prose readable and machine-translatable."** →
  `ste-lint.yml`. Requires a seeded `.ste-budget` first.
- **"I publish a flatpak app."** → `publish-flatpak.yml` + the
  `publish-flatpak-index` / `update-flatpak-index` actions. Requires
  `FLATPAK_INDEX_TOKEN` (see prerequisites).
- **"I want new people to feel welcome."** → `reusable-first-contributor.yml`.
- **"I want help-wanted issues to self-label."** →
  `reusable-add-help-wanted.yml`.
- **"I want context-aware nudges on PRs."** → `reusable-pr-nudges.yml` plus a
  `.github/scripts/pr-nudges.sh` in your repo.
- **"My repo automerges major/minor updates and I need to stop that."** → copy
  `renovate-policy-check.yml` (and its script) into your repo.
- **"Dependency-bump PRs keep pinging my review queue."** → copy
  `drop-bot-review-requests.yml`.
- **"I still carry a byte-copied `update-index.py`."** → migrate to the
  `update-flatpak-index` action, then delete the copy. The drift check will
  keep flagging you until you do.

## Prerequisites

| Tool | Secret / file / permission needed | Where to set it |
| --- | --- | --- |
| `publish-flatpak.yml`, `publish-flatpak-index`, `update-flatpak-index` | `FLATPAK_INDEX_TOKEN` — token with push access to `tuna-os/docs` (the central index repo) | Repository **Settings → Secrets and variables → Actions** |
| `publish-flatpak.yml` | `GITHUB_TOKEN` (default) — used to log in to GHCR | Automatic; ensure the publish job has `contents: read` |
| `reusable-first-contributor.yml`, `reusable-add-help-wanted.yml` | `issues: write` | Declared inside the workflow; no setup |
| `reusable-pr-nudges.yml` (PR comment) | `pull-requests: write` | Declared inside the workflow |
| `reusable-scorecard.yml` | `security-events: write`, `id-token: write` | Declared inside the workflow; `id-token` needs Actions OIDC enabled (repo **Settings → Actions → Workflow permissions**) |
| `reusable-ci-contract.yml` | `.github/green-criteria.yml` exists | Commit the file; the workflow skips cleanly if it is absent |
| `ste-lint.yml` | `.ste-budget` exists (seed once) | Run the linter once, commit its count (see troubleshooting) |

## Integration examples

### Minimal PR checks

```yaml
jobs:
  lint:
    uses: tuna-os/.github/.github/workflows/reusable-lint.yml@main
  fork-safety:
    uses: tuna-os/.github/.github/workflows/reusable-fork-safety.yml@main
```

No secrets, no extra files. `reusable-lint.yml` runs each check as its own job
so a shellcheck failure does not hide a yamllint failure.

### Full quality gate

```yaml
jobs:
  lint:
    uses: tuna-os/.github/.github/workflows/reusable-lint.yml@main
  ci-contract:
    uses: tuna-os/.github/.github/workflows/reusable-ci-contract.yml@main
  fork-safety:
    uses: tuna-os/.github/.github/workflows/reusable-fork-safety.yml@main
  scorecard:
    uses: tuna-os/.github/.github/workflows/reusable-scorecard.yml@main
  ste:
    uses: tuna-os/.github/.github/workflows/ste-lint.yml@main
```

### Simplified Technical English

Seed the budget once, then ratchet it down over time:

```sh
node .github/actions/ste-lint/ste-lint.mjs --summary   # from a checkout of tuna-os/.github
```

Commit the printed total as `.ste-budget`, then:

```yaml
jobs:
  ste:
    uses: tuna-os/.github/.github/workflows/ste-lint.yml@main
```

### Publish a flatpak app

The caller keeps its own `on:` trigger (publish cadence differs per repo —
tags-only, `main`+tags, PR-gated builds) and becomes a thin job that
`uses:` the workflow with `secrets: inherit`:

```yaml
on:
  push:
    tags: ['v*']

permissions:
  contents: read

jobs:
  publish:
    uses: tuna-os/.github/.github/workflows/publish-flatpak.yml@main
    secrets: inherit
    with:
      app-id: org.tunaos.myeapp
      manifest-path: build-aux/org.tunaos.myeapp.yml
      repo-name: tuna-os/myeapp
      archs: '["x86_64","aarch64"]'
```

`secrets: inherit` forwards `FLATPAK_INDEX_TOKEN` and `GITHUB_TOKEN`. Set
`publish: false` on `pull_request` jobs to build without writing the index.
Tavern does not use this workflow — it has a `prod`/`main` branch split and a
promotion flow this workflow does not model.

For an app whose source lives in someone else's repository (e.g. republishing
a third-party app), set `source-repo` and `source-ref`; the caller still owns
the trigger policy and the registry path.

## Troubleshooting & FAQ

**`ci-contract` passes with "No criteria file ... skipping."**
The workflow skips cleanly when `.github/green-criteria.yml` is absent. Commit
that file with your criteria (each criterion has `id`, `gates`,
`freshness_sla_days`, and optionally `enforcement: blocking`) to make the gate
do work.

**`ste-lint` fails with "No `.ste-budget` and no `budget` input."**
The repo has not been seeded. Run `--summary` (above), commit the total as
`.ste-budget`, then ratchet the number down as prose is cleaned up. A gate
seeded at `0` fails on day one and gets disabled on day two.

**A flatpak release lands in GHCR but not on the site.**
The OCI image and the index update are separate steps. If the image published
but the index never updated, the `publish-flatpak-index` push lost a race to
another app publishing to `tuna-os/docs` and exhausted its retry loop (default
8 attempts with jittered backoff). Confirm `FLATPAK_INDEX_TOKEN` is set and has
push access to `tuna-os/docs`; the retry handles ordinary races on its own.

**`fork-safety` flags my `pull_request` workflow.**
Give the workflow (or the offending job/step) an explicit `permissions:` block,
and guard any step that writes or reads a secret with a same-repository
condition such as `github.event_name != 'pull_request'` or `head.repo.fork`.
`pull_request_target` is flagged outright — use `pull_request` instead.

**`lint` shows actionlint warnings but still passes.**
actionlint runs with `continue-on-error: true` — it is advisory, not blocking.

**`scorecard` fails on `id-token: write`.**
The job requests an OpenSSF OIDC token; enable *Read workflow permissions and
write ID tokens* in the repo's Actions settings. Set `publish-results: true`
only if you want the score posted to the OpenSSF REST API.

**The drift check keeps opening issues about my repo.**
You still carry a byte-copied `.github/scripts/update-index.py`. Migrate to the
`update-flatpak-index` composite action and delete the local copy — that is the
fix that removes the drift rather than watching it.

## Detailed references

- Workflows: `.github/workflows/*.yml` (see the filenames in the tables above).
- Actions: `.github/actions/update-flatpak-index/`,
  `.github/actions/publish-flatpak-index/`, `.github/actions/ste-lint/` — each
  has a README explaining the bug it fixes and its full input list.
- [`AGENTS.md`](../AGENTS.md) — how changes here land everywhere at once, the
  drift check, and the security model behind the actions.
- [`project-starter/docs/ADOPTING.md`](../project-starter/docs/ADOPTING.md) —
  adopting the org baseline in a new repo.
