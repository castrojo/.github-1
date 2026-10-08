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

- **It fails only when a *checked* repo still carries a drifted copy; a missing
  file is a warning, not a failure.** As of 2026-10-08 all eight repos in its
  list return 404 at `.github/scripts/update-index.py` — they have migrated
  onto the composite action (gtk-office-suite #224, mandelbrot, dualcut #192,
  the four `tuna-installer-*`, and `bootc-installer`). The check is therefore
  expected to go green on its next scheduled run; the last observed failure
  (2026-10-05) predates the final migrations. See "Operational status" below.
- **Its list is not the set of repos that carry a copy.** Two repos still ship a
  copy the check never looks at, so drift there is invisible:

| repo | path | blob | checked? |
|---|---|---|---|
| `.github` | `.github/actions/update-flatpak-index/update-index.py` | `6eaa8186` | canonical |
| `docs` | `.github/scripts/update-index.py` | `b7dc0458` | **no** |
| `flatpak-index` | `scripts/update-index.py` | `4c36d624` | **no** |

`tuna-os/flatpak-index`'s copy describes *itself* as the canonical one, which
is a second definition the org's check does not recognise. Migrating a repo
onto the composite action is the fix that removes the copy rather than
watching it.

## Operational status

`flatpak-tooling-drift-check.yml` is the interim guard for
[tuna-os#1183](https://github.com/tuna-os/tunaOS/issues/1183). This section
states what its failures mean, who owns them, and how it is resolved — so a
maintainer does not have to reconstruct it from a long-running red check.

- **Why it is still running — on purpose.** It exists only until every repo
  that carries a byte-copied `update-index.py` has migrated onto the
  `update-flatpak-index` composite action in this repo. While any *checked* repo
  still carries a drifted copy it fails; that failure is the symptom the guard
  exists to surface, not a broken pipeline. It is **not** a blocker and should
  not be disabled or archived — it is the thing that goes green as migration
  finishes, and the only watcher of the two remaining carriers above.
- **Ownership.** The guard lives in the org defaults repo (`tuna-os/.github`),
  whose code owner is `@hanthor` (`.github/CODEOWNERS`). The *resolution* —
  migrating a repo — is per repo and was tracked under
  [tuna-os#1183](https://github.com/tuna-os/tunaOS/issues/1183), closed
  2026-08-23 as the duplication *finding*; the repo-by-repo migration itself is
  what is left to do.
- **Resolution plan.** Finish the migration the eight checked repos already
  started: port `docs` and `flatpak-index` onto the composite action so there
  is nothing left to drift, and widen the workflow's repo list so it matches the
  repos that *actually* carry a copy (it currently misses both). Once the
  composite action is universal, delete the schedule — the guard has done its
  job.
- **Scheduled maintenance.** Runs `0 6 * * 1` (Mon 06:00 UTC) plus
  `workflow_dispatch`. The recurring failures were expected while migration was
  incomplete and are now clearing. A red run is not urgent: confirm which
  checked repo is still drifted, migrate it, and the next run is green.

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

## `.claude/skills/hive-contribute/`

A skill that works the hive's ready-work queue **without registering a relay**,
because every route under `/api/contribute` is an unconditional public path in
the hive's own `isPublicPath`. It holds no task lease, so it does soft
deconfliction only — treat a race as possible on every run. It lives here so
any agent with this org checked out picks it up.
