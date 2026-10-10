# ci-contract

Verifies that every green criterion in a `green-criteria.yml` file is asserted
by a **reachable** workflow job/step. It is the validator that used to live as
90+ lines of Python embedded in the `reusable-ci-contract.yml` workflow step
(tuna-os/.github#206). Moved into a standalone, unit-tested CLI packaged as this
action, so the contract rules live in one tested place and travel with the
action to every caller instead of being untestable inside a workflow.

Most repos should call the reusable workflow rather than this action directly:

```yaml
jobs:
  ci-contract:
    uses: tuna-os/.github/.github/workflows/reusable-ci-contract.yml@main
```

## What it checks

A green criterion (`.github/green-criteria.yml`, when present) records what must
make CI green. For each criterion this verifies that every named gate:

- refers to a workflow that actually exists in the directory;
- is reachable from an active trigger (`push`, `pull_request`, `schedule`,
  `merge_group`, `workflow_run`, `release`) — either directly or through a
  `workflow_call` chain;
- is named in the criterion's `asserted_by` prose;
- has the named job, which is not hard-disabled (`if: false`) and, when the gate
  is `enforcement: blocking`, not `continue-on-error`;
- has the named step.

The criterion must also carry a `freshness_sla_days` value, so a gate that stops
being run does not silently keep a criterion green on paper.

## Behaviour at the boundaries

- **No `green-criteria.yml`** — the check skips with exit 0 rather than failing.
  Defining the file (what actually makes CI green) is a content decision for the
  repo that owns the criteria; the action only enforces whatever it is pointed
  at.
- **No workflows directory** — exit 1, because that means the inputs are wrong.

## Inputs

| Input | Default | Meaning |
|---|---|---|
| `criteria-path` | `.github/green-criteria.yml` | File of green criteria to verify. |
| `workflows-dir` | `.github/workflows` | Directory of workflow YAML files. |
| `python-version` | `3.11` | Python the validator runs on. |
| `run-tests` | `true` | Run the validator's own unit tests first. |

Inputs are passed to the script through `env:`, never interpolated into the
script body, so a caller-supplied path is always data and can never be parsed as
shell.

## Reproduce locally

```sh
python3 .github/actions/ci-contract/check-ci-contract.test.py   # the unit tests
python3 .github/actions/ci-contract/check-ci-contract.py         # the check
```
