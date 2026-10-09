# Reusable actions

Composite actions hosted in `.github/actions/`. Every caller pins `@main`, so
a merge here is live for all repos that `uses:` them — see
[`AGENTS.md`](../AGENTS.md) for the blast radius.

Each action has a `README.md` with the full input list and migration status;
this file is the directory listing.

| Action | What it does |
|---|---|
| [`update-flatpak-index`](actions/update-flatpak-index) | Updates a Flatpak OCI index with a published image's metadata |
| [`publish-flatpak-index`](actions/publish-flatpak-index) | Wraps `update-flatpak-index` with clone/commit/push and retry against concurrent writers to `tuna-os/docs` |
| [`ste-lint`](actions/ste-lint) | Checks Markdown prose against ASD-STE100 with a per-repo budget |

## update-flatpak-index

Canonical single-source implementation of `update-index.py`
([tuna-os/tunaos#1183](https://github.com/tuna-os/tunaos/issues/1183): the
script was byte-copied across eight repos and drifted independently). Reads a
local OCI layout directory and updates a Flatpak `index/static` file with the
published image's digest, architecture, and `org.flatpak.*` labels.

```yaml
- uses: tuna-os/.github/.github/actions/update-flatpak-index@main
  with:
    oci-dir: oci/mandelbrot-oci-x86_64   # required: OCI layout dir (must contain index.json)
    repo-name: tuna-os/mandelbrot          # required: owner/repo on the registry
    tags: latest                           # default: latest
    # index-file: index/static             # default: index/static
    # registry: ghcr.io                    # default: ghcr.io
```

For multi-arch publishes, call once per architecture — the script only ever
replaces the entry for the architecture it was given. Adopted by no app repo
yet; each caller that still ships its own `update-index.py` is a follow-up.

## publish-flatpak-index

Wraps [`update-flatpak-index`](#update-flatpak-index) with the clone, commit,
and push against the central index repo — with a retry loop, because that push
routinely loses a race. Every app repo writes to the same branch of
`tuna-os/docs`, so two publishes close together race and the loser's release
silently never reaches the served index even though its OCI image already
landed in the registry.

```yaml
- uses: tuna-os/.github/.github/actions/publish-flatpak-index@main
  with:
    oci-dir: oci/mandelbrot-oci-x86_64   # required
    repo-name: tuna-os/mandelbrot          # required
    token: ${{ secrets.FLATPAK_INDEX_TOKEN }}  # required: push access to docs-repo
    tags: latest                           # default: latest
    # index-file: static/flatpak/index/static  # default
    # docs-repo: tuna-os/docs              # default
    # max-attempts: "8"                    # default: 8, jittered backoff
```

On a rejected push it re-clones `docs-repo` at its new tip and regenerates only
this app's entry before retrying. The index update is a targeted
`(repo-name, architecture)` merge, so replaying it on a newer base cannot
clobber a concurrent writer.

## ste-lint

Checks Markdown prose against
[ASD-STE100](https://asd-ste100.org/) — sentence length, active voice, `-ing`
forms, approved words, noun clusters, and paragraph length — with a per-repo
budget so conformance converts file by file instead of being demanded on day
one. The linter and its rules travel with this action so no repository carries
a separate copy to drift.

```yaml
# Most repos call the reusable workflow rather than this action directly:
jobs:
  ste:
    uses: tuna-os/.github/.github/workflows/ste-lint.yml@main
```

```yaml
# Or call the action directly:
- uses: tuna-os/.github/.github/actions/ste-lint@main
  with:
    # budget-file: .ste-budget   # default; the max number of findings tolerated
    # budget: ""                 # used when budget-file is absent (seed a repo first)
    # node-version: "24"         # default
    # run-tests: "true"          # run the linter's own rule tests first
```

The budget (`.ste-budget`) only ever goes down — seed a new repo with its
current finding count rather than `0`, then ratchet it lower as prose lands.
See the action's `README.md` for opting a file out in its own text.
