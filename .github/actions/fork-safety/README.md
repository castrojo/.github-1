# fork-safety

Verifies that every `pull_request` workflow is safe to run from a fork. It is
the check that used to live as ~140 lines of Python embedded in the
`reusable-fork-safety.yml` workflow step (tuna-os/.github#275). Moved into a
standalone, unit-tested CLI packaged as this action, so the rules live in one
tested place and travel with the action to every caller instead of being
untestable inside a workflow step.

Most repos should call the reusable workflow rather than this action directly:

```yaml
jobs:
  fork-safety:
    uses: tuna-os/.github/.github/workflows/reusable-fork-safety.yml@main
```

## What it checks

On a `pull_request` event raised from a fork, GitHub issues a read-only
`GITHUB_TOKEN` and all repository secrets are empty. For every workflow that
fires on `pull_request` this verifies that:

- **permissions are declared** — the workflow has a top-level `permissions:`
  block, and every job that is not itself a `uses:` call declares its own;
- **`pull_request_target` is not used** — it exposes repository secrets to
  untrusted fork code; and
- **write actions and secrets are guarded** — every step that runs a write
  command (`git push`, `gh ...` mutating calls, `actions/github-script`, ...) or
  references a secret other than the read-only `GITHUB_TOKEN` carries a
  fork-aware condition.

A step counts as fork-guarded when its job `if`, its own `if`, an earlier
step's outputs it depends on, or a literal guard string
(`github.event_name != 'pull_request'`, `head.repo.fork`, `IS_FORK`, ...) is
present, or when the step sets `continue-on-error` (the runner swallows the
failure so a fork cannot actually write).

## Inputs

| Input | Default | Meaning |
|---|---|---|
| `workflows-dir` | `.github/workflows` | Directory of workflow YAML files to check. |
| `python-version` | `3.11` | Python to run the validator on. |
| `run-tests` | `true` | Run the validator's unit tests before the check. |

## Behaviour at the boundaries

- **No workflows directory** — the check prints a notice and exits 0 rather than
  failing. There is nothing to check, not a clean bill of health.
- **No `pull_request` workflows** — the check reports zero violations.

## Testing

The composite action runs `check-fork-safety.test.py`, which imports the
validator by path and drives `check_safety` against fixture directories plus the
`main` CLI exit codes. To run them standalone:

```bash
python3 -m pip install pyyaml
python3 check-fork-safety.test.py
```
