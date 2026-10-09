# publish-flatpak-index

Wraps [`update-flatpak-index`](../update-flatpak-index) with the clone,
commit, and push against `tuna-os/docs` — with a retry loop, because that
push routinely loses a race.

## The bug this fixes

Every app repo's `publish-flatpak.yml` clones `tuna-os/docs`, edits its own
entry in `static/flatpak/index/static`, and does a plain `git push origin
main`. All ~8 app repos write to that same branch. When two publishes land
within the same push window (common — several apps publish on tag pushes
and `workflow_dispatch` fires in bursts), the second push is rejected:

```
! [rejected]        main -> main (fetch first)
error: failed to push some refs to 'https://github.com/tuna-os/docs.git'
```

The job then fails outright. The OCI image was already pushed to GHCR
successfully by that point (`Push OCI to GHCR` is a separate, earlier
step), so the release exists and installs fine if you already know its
tag — but `flatpak remote-ls`/`flatpak update` never see it, because the
served index was never updated. Nothing retries; nothing alerts. The
release just silently doesn't show up.

## Usage

Replace the whole clone → update-index.py → commit → push block with:

```yaml
- uses: tuna-os/.github/.github/actions/publish-flatpak-index@3c51a447f9852d1dbb67ec5aba00a5512bfba2dc # publish-flatpak-index
  with:
    oci-dir: oci/mandelbrot-oci-x86_64
    repo-name: tuna-os/mandelbrot
    tags: latest
    token: ${{ secrets.FLATPAK_INDEX_TOKEN }}
```

For multi-arch publishes, call it once per architecture, same as before —
each call is its own independent clone/retry/push cycle. `index-file`
defaults to `static/flatpak/index/static`, `registry` to `ghcr.io`,
`docs-repo` to `tuna-os/docs`.

On a rejected push, the action re-clones `docs-repo` at its new tip and
regenerates *this app's* entry against it before retrying (up to
`max-attempts`, default 8, with jittered backoff). This is safe because
`update-index.py` only ever replaces the `(repo-name, architecture)` entry
it was given — it never rewrites another app's entry, so replaying it on a
newer base can't clobber a concurrent writer's change.

## Migration status

Tracks tuna-os/tunaos#1183 (script duplication) and tuna-os/tunaos#2104
(this race). Adopted so far: Tavern, finupdate, mariner, mandelbrot,
dualcut, gtk-office-suite (letters/tables/decks). Installer repos
(tuna-installer-{cosmic,kde,niri,xfce}, bootc-installer) still carry their
own copy of the old clone/push block — same follow-up scope #1183 already
called out for `update-index.py` itself.
