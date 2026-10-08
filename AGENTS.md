# AGENTS.md — agent guide for tuna-os/.github

The **org defaults repo**. Nothing here builds a product; everything here
applies to other repositories.

## A change here lands everywhere at once

Four different mechanisms, with different blast radii:

| Path | Reaches |
|---|---|
| `.github/ISSUE_TEMPLATE/`, `PULL_REQUEST_TEMPLATE.md`, `DISCUSSION_TEMPLATE/`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md` | Every org repo that does not ship its own copy — immediately, with no merge in that repo |
| `profile/README.md` | The organisation's public landing page |
| `.github/workflows/*.yml` with `on: workflow_call`, and `.github/actions/*` | Every repo that `uses:` them — and callers pin `@main`, so a merge is live for them |
| `project-starter/` | A template **copied** into new repos; not used by this repo |

There is no version to hold a consumer back and no way to roll back except
another commit. `publish-flatpak.yml`'s inputs and each action's `inputs:`
block are a public API: renaming one, or changing what a default means, breaks
callers silently at their next run.

## Don't put an input back into a script body

`update-flatpak-index/action.yml` routes every input through `env:` rather
than `${{ }}` interpolation, and that is load-bearing. **Actions substitutes
expressions into the script TEXT before bash parses it**, so an interpolated
value is parsed as shell. Quoting narrows it and does not close it — a value
containing a double quote ends the quoted region — and `--tags` was unquoted
outright, deliberately, so word-splitting would spread a multi-tag list into
argparse's `nargs="+"`.

Demonstrated against the rendered script: `tags: latest; touch /tmp/PWNED` ran
the `touch`, created the file, and still **exited 0**, so the step looked
clean. As an env var the value is data, and `read -ra` does the splitting the
multi-tag case actually needs. No caller was exploitable — the only one passes
a literal `latest` — but this action is the migration target for eight repos
whose jobs hold `packages: write` and `FLATPAK_INDEX_TOKEN`.

## The drift check, and what it does not cover

`flatpak-tooling-drift-check.yml` is an interim guard for
[tuna-os#1183](https://github.com/tuna-os/tunaOS/issues/1183): `update-index.py`
was byte-copied across repos with no shared source of truth. Weekly, it
compares eight application repos' `.github/scripts/update-index.py` against
`.github/actions/update-flatpak-index/update-index.py`, which it treats as
canonical, and opens or comments on an issue when any has drifted.

Two things to know before touching it:

- **It has failed on every scheduled run since 2026-08-17.** `dualcut` is in
  its list and has drifted; the other seven no longer carry the file, which
  the workflow reports as a warning.
- **Its list is not the set of repos that carry a copy.** On default branches
  today:

| repo | path | blob | checked? |
|---|---|---|---|
| `.github` | `.github/actions/update-flatpak-index/update-index.py` | `6eaa8186` | canonical |
| `dualcut` | `.github/scripts/update-index.py` | `c6e3acca` | yes — drifted |
| `flatpak-index` | `scripts/update-index.py` | `b7dc0458` | **no** |
| `docs` | `.github/scripts/update-index.py` | `b7dc0458` | **no** |
| `Tavern` | `.github/scripts/update-index.py` | `ec916224` | **no** |
| `Tavern` | `scripts/update-index.py` | `127aed10` | **no** |

`tuna-os/flatpak-index`'s copy describes *itself* as the canonical one, which
is a second definition the org's check does not recognise. Migrating a repo
onto the composite action is the fix that removes the copy rather than
watching it.

## Default branches are not all `main`

`ROADMAP-INDEX.md` is the org-wide inventory, and it exists because the
TunaOS ROADMAP drifted against a guess. The lesson is written into it:
**`bootc-installer`, `fisherman`, `changelog-action`, `kde-build-meta` and
`mariner` default to something other than `main`.** Hardcoding `main` is how a
roadmap got stranded on the wrong branch while `dev` stayed unplanned. Resolve
the default branch per repo rather than assuming.

## Checks

```bash
python3 scripts/check-renovate-automerge-policy.py renovate.json
```

`renovate-policy-check.yml` enforces [#12](https://github.com/tuna-os/.github/issues/12)
against this repo's own `renovate.json`: a syntactically valid config can still
automerge major and minor updates once `packageRules` are layered
(tuna-os#1612, tuna-os#1636), which a schema validator alone would not catch.

`scripts/check-renovate-automerge-policy.py` and
`project-starter/scripts/check-renovate-automerge-policy.py` are byte-identical
copies today, with nothing enforcing that.

## Workflow permissions check

```bash
python3 scripts/check-workflow-permissions.py .github/workflows
```

`workflow-permissions-check.yml` enforces [tuna-os/.github#155](https://github.com/tuna-os/.github/issues/155): every workflow must declare a top-level `permissions:` block. A workflow with none inherits the repository's configured default token scope, which is almost always broader than the jobs actually need. The check is dependency-free — it parses only top-level mapping keys and their indentation, so it runs on the ubuntu runner without a `pip install`.

`scripts/check-workflow-permissions.py` and `project-starter/scripts/check-workflow-permissions.py` are byte-identical copies today; copy the script into any repo that ships its own copy, the way the renovate check does.

`publish-flatpak.yml` and `ste-lint.yml` were the two workflows that lacked the block; `publish-flatpak.yml` takes `contents: write` (checkout + `gh release upload`) and `packages: write` (GHCR push + index update), `ste-lint.yml` takes `contents: read`.

## Shared tooling guide

This is the onboarding doc for the reusable workflows and composite actions here: which to adopt for each need, the secrets/tokens each requires, integration examples, and troubleshooting. New repos are pointed to it from `project-starter/docs/ADOPTING.md`.

## `.claude/skills/hive-contribute/`

A skill that works the hive's ready-work queue **without registering a relay**,
because every route under `/api/contribute` is an unconditional public path in
the hive's own `isPublicPath`. It holds no task lease, so it does soft
deconfliction only — treat a race as possible on every run. It lives here so
any agent with this org checked out picks it up.
