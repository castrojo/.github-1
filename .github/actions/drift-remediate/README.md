# Drift Remediate

Composite action that repairs a drifted `update-index.py` copy **in the repo that
calls it**. It exists so drift can be auto-repaired without a maintainer decision
or a cross-repo token: when this action runs inside an app repo's workflow,
`GITHUB_TOKEN` already has `contents: write` to that repo.

The org-level [`flatpak-tooling-drift-check.yml`](../../workflows/flatpak-tooling-drift-check.yml)
sweeps every flatpak-publishing repo on a weekly schedule but can only *file an
issue* — it cannot write to eight other repos. This action closes that gap for a
single repo, and the [`reusable-drift-check.yml`](../../workflows/reusable-drift-check.yml)
workflow wires it to each repo's own `push` so drift is caught the moment a copy
diverges, not up to a week later.

## What it does

1. Reads the canonical `update-index.py` sha from `tuna-os/flatpak-index`.
2. Compares it to the repo's own copy (`script-path`, default `.github/scripts/update-index.py`).
3. If they differ (drifted) or the copy is missing, overwrites/creates the copy
   from canonical, commits, and pushes.
4. If the direct push is refused (protected branch, no write), pushes a
   `drift-remediation/<timestamp>` branch and opens a PR instead.

## Inputs

| Input | Default | Description |
|---|---|---|
| `script-path` | `.github/scripts/update-index.py` | Path to the repo's own copy. |
| `canonical-repo` | `tuna-os/flatpak-index` | Repo owning the canonical copy. |
| `canonical-path` | `scripts/update-index.py` | Path to the canonical copy inside `canonical-repo`. |
| `remediate-missing` | `false` | Create the copy when missing (`unwired`). When `false`, a missing copy is reported only. |
| `branch` | `${{ github.ref_name }}` | Branch to remediate in place. |

## Usage

```yaml
jobs:
  drift:
    uses: tuna-os/.github/.github/workflows/reusable-drift-check.yml@main
    with:
      remediate: true
```

Grant `contents: write` to the calling workflow only on trusted branches (e.g.
`push: branches: [main]`). Remediation runs on `push`/`workflow_dispatch`, not
on `pull_request`, where the token is read-only.
