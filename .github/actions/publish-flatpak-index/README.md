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

## Security

The action receives the `tuna-os/docs` push credentials as the `token` input,
bound to the `FLATPAK_INDEX_TOKEN` env var in the shell step. Commit
7c122b4 moved it out of command-line arguments (so `ps aux` can't capture it),
but it still sits in the step's environment.

- **Log leak -- mitigated.** The action emits `::add-mask::$FLATPAK_INDEX_TOKEN`
  before the token is first used, so GitHub replaces it with `***` in every log
  line after that -- covering the `curl -H "Authorization: Bearer ..."` check,
  the git auth header, and any error message that echoes the env var. This is
  the immediate fix for tuna-os/.github#162. It references `$FLATPAK_INDEX_TOKEN`
  (the env var), never `${{ inputs.token }}`, so GitHub's expression evaluator
  never parses the secret value as shell.
- **Environment exposure -- residual.** Masking only hides the token from logs;
  it stays in `/proc/$$/environ` and process memory, so a compromised
  dependency or step in the same job could still read it. Closing that needs
  GitHub Actions support for passing secrets over a file descriptor, or a switch
  to OIDC / short-lived credentials -- an upstream decision, not something this
  action can implement alone. Until then, keep the token scoped to the minimum
  (Contents: write to `tuna-os/docs` only) and run only first-party steps in the
  publish job.

## Usage

Replace the whole clone → update-index.py → commit → push block with:

```yaml
- uses: tuna-os/.github/.github/actions/publish-flatpak-index@main
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
