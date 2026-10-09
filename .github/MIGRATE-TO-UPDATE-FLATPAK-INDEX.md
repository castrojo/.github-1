# Migrate to the update-flatpak-index action

Playbook for a repository that still vendors `.github/scripts/update-index.py`
and runs it directly from its publish workflow. Migrating deletes the local
copy and points the workflow at the single-source-of-truth tooling in
`tuna-os/.github`.

> Related: [tuna-os/tunaos#1183](https://github.com/tuna-os/tunaOS/issues/1183)
> (the script duplication this resolves),
> [tuna-os/.github#37](https://github.com/tuna-os/.github/issues/37) (the drift
> tracking issue), and
> [`flatpak-tooling-drift-check.yml`](workflows/flatpak-tooling-drift-check.yml)
> (the weekly guard that flags a divergent copy).

## 1. Why migrate

- **One source of truth.** `update-index.py` was byte-copied across repos
  (tunaos#1183) and each copy drifted independently. The canonical copy now
  lives in `tuna-os/flatpak-index/scripts/update-index.py`; the
  `update-flatpak-index` action here is a byte-identical synced copy of it
  (blob `4c36d624d4e579680efca08e2689439ccc9cbf00`).
- **No ongoing drift risk.** The
  [`flatpak-tooling-drift-check.yml`](workflows/flatpak-tooling-drift-check.yml)
  compares each flatpak-publishing repo's local copy to canonical every Monday
  and opens an issue when any diverges. Migrating deletes the copy, which is the
  only permanent fix — the check cannot tell "moved the file" from "migrated"
  on its own.
- **Hardened input handling.** The action routes every input through `env:`
  rather than `${{ }}` interpolation into the script body, so a caller value
  cannot be parsed as shell. That is load-bearing for repos whose jobs hold
  `packages: write` and `FLATPAK_INDEX_TOKEN`.

## 2. Pre-flight: is your copy canonical?

Run this against your repo's default branch:

```bash
# Canonical blob (update-index.py in tuna-os/flatpak-index):
gh api repos/tuna-os/flatpak-index/contents/scripts/update-index.py --jq '.sha'
# => 4c36d624d4e579680efca08e2689439ccc9cbf00

# Your local copy:
gh api repos/tuna-os/<repo>/contents/.github/scripts/update-index.py --jq '.sha'
```

Interpretation:

- **404** — you already migrated (no local copy). Nothing to do; just confirm a
  workflow already uses the shared tooling.
- **Equal to `4c36d624…`** — your copy is byte-identical to canonical. Safe to
  migrate; there is no delta to resolve.
- **Different** — you have a local delta. Before migrating, decide whether to
  (a) port the delta back to the canonical script (a PR to
  `tuna-os/flatpak-index`), or (b) drop it. Migrating without resolving the
  delta silently discards the difference. The most common historical delta is
  the `org.freedesktop.appstream.*` label set — the current canonical keeps
  them; an older copy that dropped them leaves software centres with only the
  application ID. See Troubleshooting.

Also confirm what your workflow currently does, because that decides which
migration target you want (next section).

## 3. Choose a migration target

The drift check counts a repo as *migrated* if its workflow uses **any** of the
shared tooling. Pick the one that matches what you are replacing:

| You currently have in your workflow | Migrate to | It replaces |
|---|---|---|
| just `python3 .github/scripts/update-index.py …` after building the OCI image | [`update-flatpak-index`](actions/update-flatpak-index) action | the script call only |
| the script call **plus** a hand-rolled clone/commit/push to `tuna-os/docs` | [`publish-flatpak-index`](actions/publish-flatpak-index) action | the script + clone/commit/push (adds a retry on the push race) |
| the whole build → GHCR → index pipeline | [`publish-flatpak.yml`](workflows/publish-flatpak.yml) reusable workflow | everything; your `on:` trigger and secrets stay yours |

### 3a. To the `update-flatpak-index` action

Find the step that runs the local script — it looks like:

```yaml
- name: Update flatpak index
  run: |
    python3 .github/scripts/update-index.py \
      --oci-dir oci/mandelbrot-oci-x86_64 \
      --index-file index-repo/static/flatpak/index/static \
      --repo-name tuna-os/mandelbrot \
      --tags latest
```

Replace it with:

```yaml
- name: Update flatpak index
  uses: tuna-os/.github/.github/actions/update-flatpak-index@main
  with:
    oci-dir: oci/mandelbrot-oci-x86_64
    index-file: index-repo/static/flatpak/index/static
    repo-name: tuna-os/mandelbrot
    tags: latest
```

Inputs: `oci-dir` (required), `repo-name` (required), `index-file` (default
`index/static`), `registry` (default `ghcr.io`), `tags` (default `latest`),
`require-appstream` (default `false`). For multi-arch publishes, call the action
once per architecture — it only replaces the entry for the architecture it is
given, leaving other arches in the index untouched.

### 3b. To the `publish-flatpak-index` action

If you also clone `tuna-os/docs`, edit your entry in
`static/flatpak/index/static`, and `git push origin main`, drop all of that and
use the wrapper instead. It clones/commits/pushes with a retry loop, because the
push to `docs` `main` routinely loses a race to a concurrent publish:

```yaml
- name: Update central index
  uses: tuna-os/.github/.github/actions/publish-flatpak-index@main
  with:
    oci-dir: oci/mandelbrot-oci-x86_64
    repo-name: tuna-os/mandelbrot
    tags: latest
    token: ${{ secrets.FLATPAK_INDEX_TOKEN }}
```

`index-file` defaults to `static/flatpak/index/static`, `docs-repo` to
`tuna-os/docs`. One call per architecture. On a rejected push the action
re-clones `docs-repo` at its new tip and regenerates *your* entry against it
before retrying — safe because the underlying script only ever rewrites the
`(repo-name, architecture)` entry it was given.

### 3c. To the reusable `publish-flatpak.yml` workflow

If you hand-roll the build → GHCR → index job, turn it into a thin job that
`uses:` the workflow, and keep your own `on:` trigger (publish cadence differs
per repo — tags-only, main+tags, PR-gated builds, and so on):

```yaml
publish-flatpak:
  uses: tuna-os/.github/.github/workflows/publish-flatpak.yml@main
  secrets: inherit
  with:
    app-id: org.tunaos.mandelbrot
    manifest-path: org.tunaos.mandelbrot.yaml
    repo-name: tuna-os/mandelbrot
    archs: '["x86_64","aarch64"]'
```

`secrets: inherit` supplies `FLATPAK_INDEX_TOKEN`. Set `publish: false` to
build-only (see Testing). This workflow does not model Tavern's prod/main
branch split and promotion flow — that is a separate follow-up (tunaos#1183).

## 4. Delete the local copy

```bash
git rm .github/scripts/update-index.py
```

If anything was vendored alongside the script (a local copy of the `docs/METAINFO.md`
guidance the script's warning points at, for example), drop it too — the
canonical references live in `tuna-os/flatpak-index`.

## 5. Test without triggering a real publish

You cannot fully exercise the action/workflow path offline: it needs a real OCI
build and, for the push paths, a write to `tuna-os/docs`. But you can verify the
*script* and the *workflow wiring* cheaply.

**Script (covers 3a, and the update half of 3b/3c).** `update-index.py` is
standard-library only and writes wherever `--index-file` points, so run it
against a scratch index file and diff the output — no registry, no `docs` write:

```bash
# Point --index-file at a throwaway file, not your real index/static:
python3 .github/actions/update-flatpak-index/update-index.py \
  --oci-dir oci/mandelbrot-oci-x86_64 \
  --index-file /tmp/scratch-index.json \
  --repo-name tuna-os/mandelbrot \
  --tags latest
# Inspect /tmp/scratch-index.json and confirm the (repo-name, arch) entry.
```

Run against a minimal OCI layout (`index.json` + `blobs/sha256/<manifest>` +
`blobs/sha256/<config>` carrying the required `org.flatpak.*` labels) this
writes a `Results[]` entry with the manifest digest, architecture, tags, and the
filtered `org.flatpak.*` / `org.freedesktop.appstream.*` labels. The
AppStream-icon warning is expected unless the image carries the icon labels; it
is a warning, not a failure, unless you pass `--require-appstream`.

**Workflow (covers 3c).** Run the migrated workflow with `publish: false` — the
reusable workflow builds the OCI image and exports it but skips the GHCR push and
the central-index update, so you can validate the build+export path on a PR or a
`workflow_dispatch` with no side effects. Flip to `publish: true` on the tag.

**Action (covers 3b).** There is no dry-run flag; the action clones and pushes.
Validate the wiring via the `publish: false` path on 3c, or accept that a
tagged release run is the first real test — the per-`(repo-name, arch)` replay
is idempotent, so a retried run cannot clobber a concurrent writer.

## 6. Rollback

The migration is a workflow-YAML change plus a `git rm` of the script. To revert:

- Restore the pre-migration commits (`git revert` the branch, or check out the
  pre-migration versions of the workflow and re-add the script).
- The examples pin the action to `@main`; callers pin `@main`, so a merge is live
  for them immediately. If you must hold a caller back from a future action
  change, pin to a specific commit SHA (`@<sha>`) instead. Reverting your
  workflow commit rolls the reference back with it.

## 7. Troubleshooting

- **Drift check still fires after migrating.** The check only counts a repo as
  migrated if *some* workflow references the shared tooling. Confirm your
  workflow points at `tuna-os/.github/.github/(workflows/publish-flatpak.yml|actions/(publish|update)-flatpak-index)@`
  and that no other workflow still calls the old script.
- **The entry lands in the wrong place.** The `update-flatpak-index` action
  defaults `index-file` to `index/static`, while `publish-flatpak-index` and the
  central docs index use `static/flatpak/index/static`. If your entry is in the
  wrong spot, you omitted/overrode the wrong default — set `index-file`
  explicitly.
- **The push to `tuna-os/docs` is rejected.** That is the concurrent-publish
  race the `publish-flatpak-index` retry loop exists to absorb. If you are still
  on a hand-rolled `git push origin main`, switch to the action (3b).
- **Your local copy had a real delta.** See step 2: port it to
  `tuna-os/flatpak-index/scripts/update-index.py` first, or you have dropped it.

## References

- [`update-flatpak-index` action](actions/update-flatpak-index/README.md) — this
  action's own status page and migration status.
- [`publish-flatpak-index` action](actions/publish-flatpak-index/README.md) —
  the clone/commit/push wrapper.
- [`publish-flatpak.yml` workflow](workflows/publish-flatpak.yml) — the reusable
  build → GHCR → index pipeline.
- [`flatpak-tooling-drift-check.yml`](workflows/flatpak-tooling-drift-check.yml)
  — the weekly drift guard; tracking issue tuna-os/.github#37.
- [tuna-os/tunaos#1183](https://github.com/tuna-os/tunaOS/issues/1183) — the
  consolidation this all serves.
