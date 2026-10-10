# update-flatpak-index

Canonical, single-source copy of `update-index.py` (tuna-os/tunaos#1183: the
script was byte-copied — identical git blob `127aed10...` — across 8 repos,
each independently drifting).

## Usage

Replace a repo's local `python3 .github/scripts/update-index.py ...` call
with:

```yaml
- uses: tuna-os/.github/.github/actions/update-flatpak-index@main
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

Confirmed migrated off the local `update-index.py` copy, verified 2026-10-10
against each repo's default branch via the GitHub contents API (no copy at
either `.github/scripts/update-index.py` or `scripts/update-index.py`):

- `Tavern` ✅ · `dualcut` ✅ · `mandelbrot` ✅ · `gtk-office-suite` ✅ ·
  `bootc-installer` ✅ (default branch `dev`)

The four installer repos in tunaos#1183's list no longer live in `tuna-os` —
the API returns 404 for `tuna-installer-{cosmic,kde,niri,xfce}`. They moved
to the `hanthor` org (or disappeared):

- `tuna-installer-kde` → `hanthor/tuna-installer-kde` ✅ migrated (no copy)
- `tuna-installer-cosmic` → `hanthor/tuna-installer-cosmic` ❌ still carries
  `.github/scripts/update-index.py`
- `tuna-installer-xfce` → `hanthor/tuna-installer-xfce` ❌ still carries
  `.github/scripts/update-index.py`
- `tuna-installer-niri` → no longer exists (404 in `tuna-os` and `hanthor`)

Two more callers in the drift set still carry a copy and have not migrated:
`tuna-os/blueshell` (`.github/scripts/update-index.py`, default branch
`ptyxis-port`) and `tuna-os/docs` (`.github/scripts/update-index.py`).
`tuna-os/flatpak-index` is the canonical source these migrate to, not a
caller — its `scripts/update-index.py` is expected to exist.

Recommendation #3 from tunaos#1183 (an interim drift-guard that fails when a
repo's committed copy diverges from canonical) is implemented in
[`.github/workflows/flatpak-tooling-drift-check.yml`](../../workflows/flatpak-tooling-drift-check.yml)
— but that workflow still lists the pre-migration repo set and has not been
updated for the migrations above; see the tracking issue for the exact
correction needed (it's a `.github/workflows/**` edit, so it can only ship
via that issue, not a PR from this agent).
