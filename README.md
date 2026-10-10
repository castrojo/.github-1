# tuna-os/.github

The **org-defaults repo** for [tuna-os](https://github.com/tuna-os). Nothing here
builds a product — everything here is a shared default that applies to the other
repositories in the org.

A change here is a change everywhere at once. There is no version to hold a
consumer back and no way to roll back except another commit, so treat the files
below as a public contract.

## What lives here

| Path | What it is |
|---|---|
| `.github/ISSUE_TEMPLATE/` | Shared issue templates (`bug`, `feature`, `adoption`) |
| `.github/PULL_REQUEST_TEMPLATE.md` | Shared PR template |
| `.github/DISCUSSION_TEMPLATE/` | Shared GitHub Discussion templates |
| `.github/workflows/` | Workflows; the `reusable-*` ones are `workflow_call` libraries |
| `.github/actions/` | Composite actions (`publish-flatpak-index`, `ste-lint`, `update-flatpak-index`) |
| `project-starter/` | A scaffold **copied into new repos** (this repo validates its own copy in CI, but does not run it as a product)
| `profile/README.md` | The organisation's public landing page (GitHub profile README) |
| `default.json` | Shared [Renovate](https://docs.renovatebot.com/) policy |
| `renovate.json` | This repo's own Renovate config (extends the shared policy) |
| `codecov.yml` | Coverage thresholds for this repo's CI |
| `ruff.toml` | Python lint config for this repo |
| `scripts/` | Python helpers (`check-renovate-automerge-policy.py`) and their tests |
| `AGENTS.md` / `CLAUDE.md` | Agent instructions — read these before editing |
| `CONTRIBUTING.md` | How to contribute |
| `CODE_OF_CONDUCT.md`, `SECURITY.md` | Community and security guidance |
| `ROADMAP.md`, `ROADMAP-INDEX.md` | Per-repo roadmap + org-wide inventory |

## How a change propagates

Four mechanisms, with different blast radii:

| Path | Reaches |
|---|---|
| `.github/ISSUE_TEMPLATE/`, `PULL_REQUEST_TEMPLATE.md`, `DISCUSSION_TEMPLATE/`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md` | Every org repo that does **not** ship its own copy — immediately, with no merge in that repo |
| `profile/README.md` | The organisation's public landing page |
| `.github/workflows/*.yml` with `on: workflow_call`, and `.github/actions/*` | Every repo that `uses:` them — callers pin `@main`, so a merge is live for them |
| `project-starter/` | A template **copied** into new repos; not used by this repo |

`default.json` is consumed by other repos as `"extends": ["local>tuna-os/.github"]`.

**Opt-in and caveats**

- A repo that ships its own copy of a template or doc diverges from this repo;
  the table above only applies where the copy is absent.
- Workflows and actions are a public API. Renaming an input or changing a
  default breaks callers silently at their next run.
- There is no versioning and no rollback — a merge is live everywhere at once.

## Key documents

- **[AGENTS.md](./AGENTS.md)** — the maintainer/agent guide. Depth; read before editing.
- **[CONTRIBUTING.md](./CONTRIBUTING.md)** — how to open a PR.
- **[ROADMAP-INDEX.md](./ROADMAP-INDEX.md)** — org-wide roadmap inventory (and why branch names are not all `main`).
- **[CODE_OF_CONDUCT.md](./CODE_OF_CONDUCT.md)**, **[SECURITY.md](./SECURITY.md)** — community and security guidance.

## When to edit here

- **Adding a new issue/discussion template** → affects every repo that doesn't ship its own copy.
- **Changing `profile/README.md`** → updates the org's public landing page.
- **Adding a reusable workflow or action** → affects every repo that `uses:` it (callers pin `@main`).
- **Editing `renovate.json` / `default.json`** → changes dependency automation across the org.
- **Editing `scripts/`** → only affects this repo's own checks.

## Conventions

- Branch prefixes: `arch/`, `fix/`, `feat/`, `chore/`.
- Sign every commit — DCO sign-off is required: `git commit -s`.
- Local check: `python3 scripts/check-renovate-automerge-policy.py renovate.json`.
