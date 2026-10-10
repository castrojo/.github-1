# Contributing to TunaOS

Thanks for wanting to contribute! TunaOS is a set of organizations-spanning
repositories that build bootable, immutable Linux desktop images from a matrix
of base OS × desktop × kernel × drivers, plus installer and migration tooling.

## Where things live

| Area | Repos |
|---|---|
| Image build factory | `tuna-os/tunaOS`, `tuna-os/tunaos-packages`, `tuna-os/tromso` |
| Installers | `tuna-os/bootc-installer`, `tuna-os/tuna-installer-{cosmic,kde,niri,xfce}` |
| Migration | `tuna-os/wootc`, `tuna-os/bootc-migrate` |
| Apps | `tuna-os/gtk-office-suite` (Letters, Tables, Decks), `tuna-os/Tavern` |
| Docs | `tuna-os/docs` (index lives in `docs/static/flatpak/index/static`) |

**Note:** This table is a representative sample. For the complete, authoritative inventory of active repositories and their default branches, see [`ROADMAP-INDEX.md`](ROADMAP-INDEX.md). New repositories are added regularly — check that document to discover them.

## Getting started

1. **Pick a repository and open an issue first** — describe the change and
   why before writing code. Small fixes (typos, docs) can skip this.
2. **Fork the repo** (or ask a maintainer for push access) and create a
   branch. We use the `arch/`, `fix/`, `feat/`, `chore/` prefix convention.
3. **Check the repo's `AGENTS.md` / `justfile`** — most repos standardize
   build/test/lint behind `just` recipes (`just build`, `just test`, `just fix`).
4. **Sign your commits** — every commit must be DCO-signed-off
   (`git commit -s`). This certifies you wrote the change and can license it.

## Working on this repository

This section is for people changing `tuna-os/.github` itself — the shared
scripts, reusable workflows, and composite actions that other repos `uses:`
and inherit. It is not about building a tunaOS image; it is about editing the
glue. The rest of this document is aimed at contributors to product repos.

### Prerequisites

| Tool | Why | Minimum |
|---|---|---|
| Python 3 | `scripts/check-renovate-automerge-policy.py` and its self-test run on it. CI uses `ubuntu-24.04` (Python 3.12); `ruff.toml` targets `py311`. | 3.11 |
| bash | Composite actions run `shell: bash` with `set -euo pipefail`. | 4 (5.x on CI) |
| Node 24 | The `ste-lint` action and its rule tests run on Node; the action pins `node-version: "24"`. | 24 |
| `gh` CLI | Forking, reading the issue, opening the PR. | latest |
| `actionlint`, `shellcheck`, `yamllint`, `jq` | Local lint mirrors. Optional — the shared `reusable-lint.yml` runs them in CI — but running them locally catches problems before the first CI run. | any recent |

`jq` is only needed to sanity-check JSON (`jq . renovate.json`). Everything
else runs directly.

### Verify before you push

The checks that matter for this repo run straight from a checkout, no build
step:

```bash
# Policy gate: refuses a renovate.json that would automerge a major update.
python3 scripts/check-renovate-automerge-policy.py renovate.json
python3 scripts/check-renovate-automerge-policy.py default.json
python3 scripts/check-renovate-automerge-policy.py project-starter/renovate.json

# Boundary test for that gate: minor passes, major fails, the scoping rules
# that stop a narrow override from cancelling a broad bypass still hold.
python3 scripts/test-renovate-automerge-policy.py

# ste-lint action rule tests. The generated-tree tests self-skip here
# because this is not the docs aggregator.
node .github/actions/ste-lint/ste-lint.test.mjs
```

If you touched a shell script, `shellcheck` it first:

```bash
shellcheck --severity=error --exclude=SC1091,SC2114 .github/actions/*/action.yml
```

If you touched a workflow, `actionlint` it:

```bash
actionlint .github/workflows/*.yml
```

(Install via `brew install actionlint shellcheck yamllint jq`, the Go
`go install` paths, or the prebuilt releases. CI runs these in
`reusable-lint.yml` regardless, so a missed local run still fails upstream —
but the local run is what lets you iterate.)

### Common tasks

**Add a new reusable workflow** (a `.yml` with `on: workflow_call:`):

1. Give it a clear `name:` — callers see this in their logs.
2. Declare every input with a `type:` and a `default:` unless it must be
   required. Inputs are a public API (see below).
3. Declare a top-level `permissions:` block (least privilege). This repo's
   own workflows are the reference — copy the shape from an existing one.
4. `actionlint` it, and point a caller at your branch once to exercise it.
   A `workflow_call` workflow never runs on its own; someone has to `uses:`
   it before a bug is visible.
5. If it is meant to be the shared default, add it to the repos that should
   adopt it — there is no automatic rollout.

**Modify an action's inputs** (`.github/actions/*/action.yml`):

Inputs travel through `env:`, never through `${{ }}` interpolation into the
script body — actions substitute expressions into the script *text* before
bash parses them, so an interpolated value is parsed as shell. This is
deliberate and load-bearing (documented in `AGENTS.md` and demonstrated
against `update-flatpak-index`). When you change an input:

- Treat every existing caller as live. Callers pin `@main`, so a merge is
  live for them immediately and there is no rollback except another commit.
- Renaming an input, or changing what a `default:` means, breaks callers
  silently at their next run. Rename only with a migration PR per caller, or
  keep the old name as a deprecated alias.
- Test the default **and** a custom value, and a value with spaces/special
  characters — that is the injection case the `env:` routing exists to close.

**Update the shared PR template** (`PULL_REQUEST_TEMPLATE.md`):

- It renders on the "Open a pull request" page in every org repo. There is no
  local preview — the way to verify it renders is to open a test PR in any
  repo and confirm the body matches.
- Remember the template prose is also STE-checked (it is one of the files
  `ste-lint` scans), so keep sentences short and active.

### Blast radius

Before editing anything under `.github/`, read `AGENTS.md`. A change here
lands everywhere at once: a `workflow_call` workflow or action that callers
pin `@main` goes live for every repo the moment it merges, with no separate
merge in those repos and no way to roll back except another commit. That is
why this section exists separately from the product-facing "getting started"
above: editing this repo means editing the shared layer every repo inherits.

## PR checklist

- [ ] Commit messages are signed off (`git commit -s`)
- [ ] `just fix` passes (format + lint) where the repo defines it
- [ ] Tests pass (`just test` or the relevant CI workflow)
- [ ] No secrets or machine-specific paths are committed
- [ ] Docs/changelog updated if behavior changed

## Architecture expectations

- **This is an image factory, not a distro.** Changes that alter built images
  must show evidence (build + boot + smoke test) in the PR.
- **One source of truth per artifact.** Before adding a new copy of a script,
  workflow, or spec, check whether a canonical version exists (e.g. the flatpak
  publish tooling, `update-index.py`). Prefer reusing it over copying.
- **Deliberate duplication is flagged.** Some frontends intentionally
  reimplement a shared contract per language (see
  `tuna-os/docs/docs/bootc-installer-asahi/UNIFIED-INSTALL-CONTRACT.md` —
  the `recipe.json` contract shared by the installer frontends). Match the
  contract; don't fork it.
- **Agents file `[architect]`/`[sec-check]`/`[strategist]` issues.** These are
  structural findings — treat them as prioritized backlog, not noise.

## CI/CD security

Every workflow in a tunaOS repository must declare an explicit top-level
`permissions:` block, following the principle of least privilege:

```yaml
permissions:
  contents: read
```

A workflow with no block inherits the repository's configured default token
scope, which is almost always broader than the jobs actually need. This is the
baseline called for by
[tuna-os/.github#155](https://github.com/tuna-os/.github/issues/155).

- **New repos** inherit it for free: `project-starter/` ships a `ci.yml` with
  the block and a `workflow-permissions` job that runs the check.
- **Existing repos** should adopt it with the shared tooling from
  `tuna-os/.github`: copy `workflow-templates/ci.yml` (a compliant starting
  point) and run the check — `python3 scripts/check-workflow-permissions.py
  .github/workflows`. The script and a ready-to-run workflow ship there and are
  copied in.

## Getting help

- Ask in the relevant issue or PR.
- See the [`tuna-os/docs` repository](https://github.com/tuna-os/docs) for architecture and build-pipeline reference documentation. Start with its `README.md` for an overview of the image factory and repository organization.
- For security issues, use the private channel described in `SECURITY.md` —
  never paste secrets or exploit details into a public issue.
