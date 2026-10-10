# Adopting shared GitHub Actions

This guide is for maintainers of repositories in the
[tuna-os](https://github.com/tuna-os) organization (and any repo that wants to
use the same tooling). It answers one question: **how do I stop hand-maintaining
something this org already maintains centrally?**

`tuna-os/.github` is the *org defaults repo*. It ships shared GitHub Actions and
reusable workflows that every repo is meant to `uses:` rather than reimplement.
Nothing here builds a product — every action and workflow applies to other
repositories. Adopting one means your repo no longer carries its own copy that
can drift, rot, or diverge.

Read [`CONTRIBUTING.md`](../CONTRIBUTING.md) for the contribution model and
[`AGENTS.md`](../AGENTS.md) for how a change here lands everywhere at once.

## Quick start

1. Find the shared action or reusable workflow that does what your repo already
   does by hand (see the inventory below).
2. Replace your local step with a single `uses:` line.
3. Delete the local copy, script, or block that it replaced.
4. Pin the reference to a commit SHA (see [Versioning](#versioning)).
5. Run the migration in a PR; the shared action's own tests run in CI.

Adopting is a two-file change — add a `uses:` line, delete a copy — not a rewrite.
The rest of this file is the detail for each tool.

## Inventory of shared tooling

| Shared action / workflow | What it does | Adopt when your repo … |
|---|---|---|
| [`update-flatpak-index`](https://github.com/tuna-os/.github/tree/main/.github/actions/update-flatpak-index) | Canonical `update-index.py`: reads a local OCI layout and updates a Flatpak index/static file with the published image's digest, architecture, and labels. | Still runs its own vendored `python3 .github/scripts/update-index.py …` instead of this action. |
| [`publish-flatpak-index`](https://github.com/tuna-os/.github/tree/main/.github/actions/publish-flatpak-index) | Clones the central index repo, updates one app's entry via `update-flatpak-index`, and pushes — with a retry loop against concurrent writers. | Does its own clone → update → commit → push to `tuna-os/docs`, or has silently lost a publish to a race. |
| [`publish-flatpak.yml`](https://github.com/tuna-os/.github/tree/main/.github/workflows/publish-flatpak.yml) (reusable) | Full build → GHCR → central-index pipeline for flatpak apps. Callers keep their own `on:` trigger and become a thin `uses:` job. | Maintains a bespoke build-and-publish workflow that overlaps this one. |
| [`ste-lint.yml`](https://github.com/tuna-os/.github/tree/main/.github/workflows/ste-lint.yml) (reusable) + [`ste-lint`](https://github.com/tuna-os/.github/tree/main/.github/actions/ste-lint) (action) | Checks Markdown prose against ASD-STE100 (Simplified Technical English) with a per-repo budget. | Lints its own README/docs for STE, or wants org-wide prose consistency. |
| [`reusable-lint.yml`](https://github.com/tuna-os/.github/tree/main/.github/workflows/reusable-lint.yml) (reusable) | Static analysis — shellcheck, yamllint, json-validate, actionlint, justfmt — across shell, YAML, JSON, Justfiles, and workflows. | Runs any of these linters by hand in its own CI. |

The reusable workflows (`publish-flatpak.yml`, `ste-lint.yml`, `reusable-lint.yml`)
are the usual adoption entry point: your repo keeps its own `on:` trigger block
(publish cadence and lint timing differ per repo) and becomes a thin job that
`uses:` the shared one. The composite actions (`update-flatpak-index`,
`publish-flatpak-index`, `ste-lint`) are what you call when you need just one
step inside a larger, repo-specific workflow.

## Migration path: `update-index.py`

**Current state.** `update-index.py` was byte-copied — identical git blob — across
eight repos with no shared source of truth ([tuna-os/tunaos#1183](https://github.com/tuna-os/tunaos/issues/1183)).
Vendored copies still live at `.github/scripts/update-index.py` in at least
`dualcut`, `docs`, and `Tavern` (and in `tuna-installer-{cosmic,kde,niri,xfce}`,
`bootc-installer`, `mandelbrot`, `gtk-office-suite`). Each copy drifts
independently, and nothing notices until a publish breaks.

**Why the canonical action is better.** `update-flatpak-index` is the single
source of truth for that script. Adopting it means:

- One implementation to fix, audit, and version — not eight.
- No copy to drift. An interim weekly
  [`flatpak-tooling-drift-check.yml`](https://github.com/tuna-os/.github/tree/main/.github/workflows/flatpak-tooling-drift-check.yml)
  already flags repos whose committed copy diverges from canonical; migrating
  removes the copy so there is nothing left to drift.
- Input validation and the OCI tag grammar live in one place.

**Step-by-step.**

1. In your publish workflow, replace the step that runs the local script:

   ```yaml
   # Before — your own copy:
   - run: python3 .github/scripts/update-index.py \
           --oci-dir oci/x86_64 --index-file index/static \
           --repo-name tuna-os/your-app --registry ghcr.io --tags latest

   # After — the shared action:
   - uses: tuna-os/.github/.github/actions/update-flatpak-index@main
     with:
       oci-dir: oci/x86_64
       index-file: index/static
       repo-name: tuna-os/your-app
       registry: ghcr.io
       tags: latest
   ```

2. Delete the local copy: `git rm .github/scripts/update-index.py`.
3. For multi-arch publishes, call the action once per architecture — it only
   ever replaces the entry for the architecture it was given, leaving other arches
   untouched.
4. Open the PR. The action carries its own tests; the shared action's tests run
   in CI.

**Testing and validation before deployment.** This is the hard part, and it is
why each migration is a per-repo follow-up rather than an org-wide sweep:
migrating touches a live publish pipeline that cannot be exercised here without
a real OCI build. Validate on a real tag push (or `workflow_dispatch`) after
merge — confirm the image lands in GHCR *and* its entry appears in the served
index (`flatpak remote-ls` against the docs site). If the index does not update,
the OCI image still installed; the release just never shows up.

**If the action does not meet your needs.** Open an issue in
`tuna-os/.github` describing the gap. Reference `tuna-os/tunaos#1183` so the
context is clear. If the fix is org-wide, port it into the canonical action; if
it is repo-specific, keep a thin local wrapper rather than forking the script.

## Migration path: `publish-flatpak-index`

**When to adopt.** Adopt this action if your publish workflow does its own
clone → `update-index.py` → commit → push to `tuna-os/docs`. The action wraps
`update-flatpak-index` with the clone, commit, and push — and, crucially, a
retry loop.

**The bug it fixes.** Every app repo writes to the same `tuna-os/docs` `main`
branch. When two apps publish close together (common on tag pushes, where
`workflow_dispatch` fires in bursts), the second push is rejected:

```
! [rejected]        main -> main (fetch first)
error: failed to push some refs to 'https://github.com/tuna-os/docs.git'
```

The job then fails outright. The OCI image was already pushed to GHCR, so the
release exists and installs — but `flatpak remote-ls` never sees it, because the
served index was never updated. Nothing retries; nothing alerts. The action
re-clones `docs-repo` at its new tip and regenerates *only this app's* entry
against it before retrying (up to `max-attempts`, default 8, jittered backoff).
That is safe because `update-index.py` only ever replaces the
`(repo-name, architecture)` entry it was given — it never rewrites another app's
entry, so replaying it on a newer base cannot clobber a concurrent writer.

**Step-by-step.**

```yaml
- uses: tuna-os/.github/.github/actions/publish-flatpak-index@main
  with:
    oci-dir: oci/x86_64
    repo-name: tuna-os/your-app
    tags: latest
    token: ${{ secrets.FLATPAK_INDEX_TOKEN }}
```

`token` is a `FLATPAK_INDEX_TOKEN` with push access to `tuna-os/docs`. For
multi-arch, call once per architecture — each call is its own independent
clone/retry/push cycle. `index-file` defaults to `static/flatpak/index/static`,
`registry` to `ghcr.io`, `docs-repo` to `tuna-os/docs`, `max-attempts` to `8`.

**Integration with existing workflows.** Most repos should skip both the raw
action and the manual clone/push block and adopt the full
[`publish-flatpak.yml`](https://github.com/tuna-os/.github/tree/main/.github/workflows/publish-flatpak.yml)
reusable workflow instead — it already wires build → GHCR → index, including the
per-arch `publish-flatpak-index` calls. Keep your own `on:` trigger (publish
cadence differs per repo) and become a thin job:

```yaml
jobs:
  publish:
    uses: tuna-os/.github/.github/workflows/publish-flatpak.yml@main
    with:
      app-id: org.tunaos.your-app
      manifest-path: build-aux/manifest.yaml
      repo-name: tuna-os/your-app
      archs: '["x86_64","aarch64"]'
    secrets: inherit
```

`secrets: inherit` supplies `FLATPAK_INDEX_TOKEN` (and `GITHUB_TOKEN`). Note
`publish-flatpak.yml` does not model a prod/main branch split — if your repo has
one (like `Tavern`), adopt `publish-flatpak-index` directly and keep your
promotion flow.

**Input mapping and customization.** The action's inputs map directly onto the
old block: `oci-dir`, `repo-name`, `registry`, `tags` come from your build;
`token` from your secret; `docs-repo` and `max-attempts` rarely need changing.
Treat the input block as a public API — see [Breaking changes](#breaking-changes-and-versioning).

## Migration path: `ste-lint` (Simplified Technical English)

**Run the org-wide prose lint.** Most repos call the reusable workflow rather
than the action directly:

```yaml
jobs:
  ste:
    uses: tuna-os/.github/.github/workflows/ste-lint.yml@main
```

Keep your own `on:` trigger (e.g. gated on `pull_request`). The workflow checks
`docs/` and `blog/` if present, plus `README.md`, `CONTRIBUTING.md`,
`SECURITY.md`, and `CODE_OF_CONDUCT.md` — all optional, so a repo with none of
them checks nothing and passes.

**What it checks.** Sentence length (20 words procedural / 25 descriptive),
active voice, `-ing` forms, approved words, noun clusters longer than three
words, and paragraphs longer than six sentences — against
[ASD-STE100](https://asd-ste100.org/).

**Customizing for your repo — the budget, not zero.** The check reads
`.ste-budget`, the maximum number of findings your repo tolerates. **The number
only ever goes down.** A gate that fails on day one gets disabled on day two, so
seed a new repo with its *current count*, not `0`:

```sh
node .github/actions/ste-lint/ste-lint.mjs --summary   # from a checkout of tuna-os/.github
```

Take the total, commit it as `.ste-budget`, then lower it in batches as prose
improves. The linter also reads a `budget` input when `.ste-budget` is absent.

**Opting a file out.** A file opts out *in its own text*, with a stated reason —
a reason is required, so the opt-out list does not become a place for prose to
go forgotten. Published blog posts, the Contributor Covenant, and bibliographies
are the established reasons.

**Why it lives here.** The linter and its rules travel with this action, so no
repo carries a copy that can drift. It was built in `tuna-os/docs` and moved here
because `docs/<slug>/` trees are generated from ~40 repos' READMEs — prose written
in those source repos was reaching the site unchecked, and a fix in the generated
tree is reverted by the next sync. Checking at the source is what makes it work.

## Evaluating shared actions

Adopt a shared action when all of these are true:

- **A canonical implementation exists** in `tuna-os/.github`. The org's rule is
  one source of truth per artifact — before adding a copy of a script, workflow,
  or spec, check whether a canonical version exists and reuse it.
- **The shared behavior covers your use case.** The action models the common
  path; repo-specific edges belong in a thin local wrapper, not a fork.
- **You can live without the drift.** Once you adopt it, your behavior is defined
  by the central repo. That is the point — you trade independent control for a
  single, audited source.

Keep a local implementation only when the shared action genuinely does not fit:
a different publish cadence model (prod/main promotion), repo-specific rules the
action does not parameterize, or a contract the action is not meant to own. Match
the shared contract; do not fork it. Deliberate duplication is flagged in review.

**Suggesting a new shared action.** If you find yourself reimplementing the same
thing in a third repo, open an issue in `tuna-os/.github` proposing it as a new
shared action or reusable workflow. Structure it like the others: a problem
statement, the repos affected, and the proposed input/output contract. The
maintainers consolidate duplicates — see the pattern in how `update-index.py`
became `update-flatpak-index`.

## Breaking changes and versioning

**There is no version to hold a consumer back, and no rollback except another
commit.** A merge to `main` is live for every caller at once — callers pin
`@main`, so a merge is immediately in production. The reusable workflow's inputs
and each action's `inputs:` block are a public API: renaming one, or changing
what a default means, breaks callers silently at their next run.

**Pinning: `@main` vs a commit SHA.** `@main` is convenient while developing, but
it means every push to the action's branch is an unreviewed, unversioned change
to every caller. The org's practice (commit pinning third-party actions,
`tuna-os/.github#263`) is to pin to a commit SHA for reproducibility and to make
each caller's dependency explicit and reviewable:

```yaml
# Prefer a pinned SHA in production (get the action's current commit with
#   `gh api repos/tuna-os/.github/commits --jq '.[0].sha'`):
- uses: tuna-os/.github/.github/actions/ste-lint@<action-sha> # pin to the action's commit

# @main is acceptable for a repo still standardizing; pin before going to prod.
- uses: tuna-os/.github/.github/actions/ste-lint@main
```

When the shared action bumps a transitive third-party action (e.g.
`actions/checkout`, `actions/setup-node`), the action is pinned to a SHA
internally, so callers are protected from that drift — but pin your own `uses:`
line to the action's SHA so you control when you pick up its changes.

**Handling a breaking change.** Because a merge is immediate, a breaking change to
a shared action's input contract is felt by every caller at their next run:

- If you own a caller and the change breaks you, update the caller's `with:` block
  and pin to the new action SHA in the same PR.
- If the change was accidental, the only fix is another commit in the shared
  repo — there is no tag to point back to. Report it as a bug in `tuna-os/.github`.
- Anticipate: treat the input block as a public API. Add new inputs as optional
  with safe defaults; never rename or redefault an existing one without a
  coordinated bump across callers.

**A security note.** The flatpak actions route every input through `env:` rather
than `${{ }}` interpolation into the script body. Actions substitutes expressions
into the script *text* before bash parses it, so an interpolated value is parsed
as shell — an unquoted value is command injection. This action is the migration
target for repos whose jobs hold `packages: write` and `FLATPAK_INDEX_TOKEN`, so
adopt it rather than a hand-rolled clone/push block that might not be as careful.

## See also

- [`CONTRIBUTING.md`](../CONTRIBUTING.md) — contribution model, branch prefixes, DCO sign-off.
- [`AGENTS.md`](../AGENTS.md) — how changes here land everywhere at once, the drift check, branch policy.
- [`tuna-os/tunaos#1183`](https://github.com/tuna-os/tunaos/issues/1183) — the consolidation this tooling implements.
- [`tuna-os/.github#263`](https://github.com/tuna-os/.github/issues/263) — pinning actions to commit SHAs.
