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
- To tell an active repository from a retired one, see [`ROADMAP-INDEX.md`](ROADMAP-INDEX.md) (the active-repo inventory) and [`REPO_LIFECYCLE.md`](REPO_LIFECYCLE.md) (the supersede/archive process).
- For security issues, use the private channel described in `SECURITY.md` —
  never paste secrets or exploit details into a public issue.
