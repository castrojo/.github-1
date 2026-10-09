# update-flatpak-index

Canonical, single-source copy of `update-index.py` (tuna-os/tunaos#1183: the
script was byte-copied — identical git blob `127aed10...` — across 8 repos,
each independently drifting).

## Usage

Replace a repo's local `python3 .github/scripts/update-index.py ...` call
with:

```yaml
- uses: tuna-os/.github/.github/actions/update-flatpak-index@60958d8b0dcb2a5d6efa2bac3d135ede018f4e4b # pinned to repo SHA, not @main (issue #168)
  with:
    oci-dir: oci/mandelbrot-oci-x86_64
    index-file: index-repo/static/flatpak/index/static
    repo-name: tuna-os/mandelbrot
    tags: latest
```

`registry` defaults to `ghcr.io`; `index-file` defaults to `index/static`.
For multi-arch publishes, call the action once per architecture (matching
the existing per-repo loop pattern) — `update-index.py` only ever replaces
the entry for the architecture it was given, leaving other arches in the
index untouched.

## Migration status

This action was added as the first step of the tunaos#1183 consolidation
(recommendation #1: host the script once, consume via composite action).
It has since been wrapped by
[`publish-flatpak-index`](../publish-flatpak-index) (adds the
clone/commit/push-with-retry against `tuna-os/docs` that every caller used
to hand-roll — see that action's README for tunaos#2104), and consumed
indirectly through the reusable
[`publish-flatpak.yml`](../../workflows/publish-flatpak.yml) workflow
(recommendation #2). Direct callers of *this* action are what remains
duplicated, not `update-index.py` itself.

Confirmed migrated off the local `.github/scripts/update-index.py` copy
(verified by cloning each repo's default branch — no file at that path in
any of them): `Tavern`, `dualcut`, `mandelbrot`, `gtk-office-suite`. Not
verified either way from this repo (no visibility into their default
branch from here): `tuna-installer-{cosmic,kde,niri,xfce}`,
`bootc-installer` — tunaos#1183's original list named them too, and nothing
in this repo confirms whether they've moved off the script or the
clone/push block `publish-flatpak-index`'s README describes.

Recommendation #3 from tunaos#1183 (an interim drift-guard that fails when a
repo's committed copy diverges from canonical) is implemented in
[`.github/workflows/flatpak-tooling-drift-check.yml`](../../workflows/flatpak-tooling-drift-check.yml)
— but that workflow still lists the pre-migration repo set and has not been
updated for the migrations above; see the tracking issue for the exact
correction needed (it's a `.github/workflows/**` edit, so it can only ship
via that issue, not a PR from this agent).
