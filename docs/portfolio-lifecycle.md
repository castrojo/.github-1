# Portfolio Lifecycle Registry

**Last verified**: 2026-10-08 · **Source**: `gh repo view tuna-os/<repo> --json name,isArchived,description` against the active `tuna-os` organization, cross-checked against each repository README.

ROADMAP-INDEX lists the active repositories and their roadmap coverage. This registry lists the repositories that reached a lifecycle milestone. A repository reaches a milestone when the org supersedes it, retires it, or archives it. This registry keeps the state visible, so the org does not keep deprecated code in service forever.

## Why this exists

The org deprecated `suite-common-rust` but did not archive it. A deprecated repository that the org did not archive still costs work every run. Renovate opens update PRs for it. CI runs for it. Reviewers read code that nobody should use.

The gap is invisible until someone audits a dependency. This registry makes the state clear. It gives a process to move a repository from deprecated to archived.

## Lifecycle states

| State | Meaning | Further planning? |
|---|---|---|
| active | The repo is under maintenance. It gets features, fixes, and dependency updates. | Yes. The repo roadmap governs it. |
| deprecated | A canonical implementation supersedes it. The org keeps it only as a historical reference. Do not add new dependencies on it. Migrate to the canonical implementation. | Retire it. Archival is the only remaining step. |
| archived | The org retired it. It takes no further planning. | No. |

A repository must not stay deprecated past its gate. The gate is the point where a maintainer confirms the canonical replacement is complete and archives the repository.

## Registry

The verified columns come from the GitHub API and each repository README on the date above. A maintainer fills the decision columns. These columns record who is accountable and when the gate closes. Automation does not fill them.

| Repository | Default branch | Verified status | Canonical replacement | Evidence | Decision: owner | Decision: gate | Decision: maintenance scope |
|---|---|---|---|---|---|---|---|
| `suite-common-rust` | main | deprecated | `tuna-os/gtk-office-suite` (`gtk-office-suite/suite-common/`) | The README marks the crate DEPRECATED and points consumers at the monorepo version | Pending maintainer | Pending maintainer | Historical reference only |
| `ubuntu` | — | archived | — | The org archived it on 2026-08-12 (confirmed via API). It takes no further planning. | — | — | n/a |
| `letters` | — | archived | — | The org archived it on 2026-08-12 (confirmed via API). It takes no further planning. | — | — | n/a |
| `kde-build-meta` | — | superseded | `tuna-os/tromso` | The org documented it as superseded by `tromso`. The retirement tracker is `tuna-os/kde-build-meta#19`. The repository no longer resolves via the API as of 2026-10-08. Confirm its archival state with a maintainer. | Pending maintainer | Pending maintainer | Historical reference only |

### Not in this registry

The report calls `suite-common-python` a deprecated repository with an overdue gate. This repository does not exist in the `tuna-os` organization. The org does not track it as a lifecycle item. This report is wrong, so the registry omits it.

Active repositories are not lifecycle items. The org governs them with their own roadmaps and inventories them in ROADMAP-INDEX.md.

## Decision ownership

Lifecycle decisions affect the whole portfolio. This registry names an owner for every decision.

- **Maintainer.** A maintainer holds the decision to move a repository from deprecated to archived. Only an org maintainer can archive a repository. Only a maintainer who edits the repository or this registry can close a gate.
- **Portfolio Lifecycle Coordinator.** The org has not filled this role yet. This role tracks deadlines for decisions across the portfolio. It verifies gates close on time. It escalates overdue gates. A maintainer assigns a name to this role.
- **Strategist and architect agents.** They surface milestones and maintain this registry. They do not own the retirement decision.

## Execution checklist

1. **Consumer audit.** Find who still uses the deprecated version. Search `git ls-tree` and dependency declarations in the org, or ask in the canonical issue. Record the count in this registry.
2. **Confirm the canonical replacement.** The linked implementation must be complete. It must replace the deprecated version. The `suite-common-rust` README states this already.
3. **Archive.** A maintainer archives the repository. This registry cannot take this action on its own.
4. **Update this registry.** Flip the state to archived. Record the archival date.
5. **Stop the maintenance cost.** Disable org-wide automation for the retired repository. This includes Renovate, CI, and drift checks.

## Open maintainer actions

- **The org deprecated `suite-common-rust`, but it did not archive it.** This is the only confirmed deprecated-and-active repository in the portfolio. A maintainer must confirm the canonical migration. Then a maintainer archives it and removes the org-wide automation that still bumps it.
- **Assign the Portfolio Lifecycle Coordinator.** Record a decision gate for `suite-common-rust`.
- **Confirm the state of `kde-build-meta`.** This repository no longer resolves via the API. Check whether the `tromso` migration archived it.

---

*Maintained as an organization-level governance artifact. Changes land by PR against this file. The contributor guide explains the process. Decision columns are maintainer-owned and intentionally left for a human to fill.*

— hive: backend=omp model=lab-worker/ornith
