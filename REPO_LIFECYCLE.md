# Repository Lifecycle Procedures

**Applies to:** every `tuna-os` repository. This is the *how*; the
[Portfolio Lifecycle Registry](docs/portfolio-lifecycle.md)
(tuna-os/.github#112) records the *what is true today*, and
[ROADMAP-INDEX.md](ROADMAP-INDEX.md) inventories the *active* repos. Read all
three together.

A repository is not a permanent object. It is created, may be superseded, is
retired, and then lives on as history. This document records the process for
each transition and — because this is the org-defaults repo — the org-level
updates every transition triggers. A transition with no follow-up update leaves
dead automation running, a stale inventory, and ambiguity about who owns the
repo next.

## Why this exists

AGENTS.md and ROADMAP-INDEX.md reference lifecycle events (an archive here, a
superseded repo there) but never state the process. The result, described in
tuna-os/.github#134:

- Archiving is done but not explained, so the next maintainer does not know
  which org files to update afterward.
- A deprecated repo that is never archived keeps costing work every run
  (Renovate opens update PRs for it, CI builds it, drift checks read it).
- There is no documented difference between "superseded", "archived", and
  "historical read-only", so repos drift into an ambiguous middle state.

This doc closes that gap.

## Lifecycle stages

| Stage | Meaning | Further planning? | GitHub state |
|---|---|---|---|
| **active** | Under maintenance: features, fixes, dependency updates. Governed by its own `ROADMAP.md`. | Yes | Open, `archived: false` |
| **deprecated** | A canonical implementation supersedes it. Kept only as historical reference. Do not add new dependencies on it. | Retire it — archival is the only remaining step. | Open, `archived: false` (README marked DEPRECATED) |
| **archived** | Retired. Takes no further planning. Serves as historical reference and is marked **read-only** on the org profile. | No | `archived: true` |
| **read-only** | The profile-facing label for an archived repo: it still exists and can be cloned/read, but no one ships to it or plans against it. | No | `archived: true` |

`deprecated` and `archived` are the two states that cause the most stray work,
because in both the repo is still open on GitHub. `read-only` is not a separate
GitHub state — it is how an `archived` repo is presented on the org landing
page. `active` → `deprecated` → `archived` is the normal path; a repo can go
straight from `active` to `archived` when it is retired without a successor.

A repository must not stay `deprecated` past its gate. The gate is the point
where a maintainer confirms the canonical replacement is complete and archives
the repo. The registry (tuna-os/.github#112) tracks gates; this doc describes
how to close one.

## Transitions

### 1. Active → Deprecated (a successor exists)

Deprecation is a documentation and dependency action, not a GitHub setting.

1. **Confirm the successor is complete.** The canonical repo must replace the
   deprecated one, not merely exist. Record the evidence (a README line, a
   merged migration PR) — this is the same evidence the registry records.
2. **Point consumers at the successor.** Mark the repo's own `README.md`
   `DEPRECATED` at the top and link the canonical implementation (the
   `suite-common-rust` → `gtk-office-suite/suite-common/` pattern). This is the
   only change that lives in the deprecated repo itself.
3. **Stop new work.** Announce in the successor issue/PR that the deprecated
   repo is frozen; no new features or dependency bumps beyond security fixes.
4. **Record it.** The registry (tuna-os/.github#112) adds the row with the
   canonical replacement and evidence. This doc does not need an edit — the
   repo is still active in ROADMAP-INDEX until it is archived.

Do **not** archive at this step. A deprecated-but-open repo can still be read
for reference and can receive the migration PRs that move consumers off it.

### 2. Deprecated → Archived (closing the gate)

Archiving is a maintainer-only GitHub action. Only an org maintainer can set
`archived: true` in the repository settings; this repo's docs cannot take the
action for them.

1. **Consumer audit.** Find who still depends on the deprecated repo — search
   dependency declarations and `git ls-tree` across the org, or ask in the
   successor issue. Record the count as evidence. Nothing moves until the last
   consumer has migrated.
2. **Maintainer confirms the gate.** A maintainer verifies the successor is
   complete and every consumer has migrated, then archives the repo in GitHub
   settings (`Settings → General → Archived repository`).
3. **Stop the maintenance cost.** Remove the repo from every org-wide automation
   that still touches it (see below). Archiving stops CI *builds* for the repo,
   but it does not remove the repo from Renovate's or a drift check's *list*.
4. **Update the org artifacts.** Flip the registry row to `archived` with the
   date, and remove the repo from the active inventory (see Org-level updates).

### 3. Active → Archived (retirement without a successor)
Same mechanics as step 2, but there is no canonical replacement to point at.
Common causes: the feature is dropped, or the repo was experimental. Record the
reason in the registry and on the repo's README before archiving, so the next
person knows it was intentional, not an accident.

### 4. Archived → historical / read-only

Archival is generally terminal. An archived repo is kept for reference (its
code, releases, and issue history remain readable and cloneable). Do **not**
un-archive to resurrect work — branch or fork it instead. Mark it read-only on
the org profile so contributors do not file issues against a repo that takes no
action. Un-archiving is only for correcting a mistaken archive.

## Org-level updates every transition requires

A transition is not done until the org artifacts that describe the repo are
updated. This is the part that is usually forgotten.

| Artifact | Active | Deprecated | Archived |
|---|---|---|---|
| `ROADMAP-INDEX.md` (this repo) | Listed, coverage checked | Still listed (repo still open) | **Removed** from the table + scope note |
| [Portfolio Lifecycle Registry](docs/portfolio-lifecycle.md) (tuna-os/.github#112) | Not a row | Row added: replacement + evidence | Row flipped to `archived` + date |
| `profile/README.md` (org landing page) | Normal link | Normal link | **Marked read-only** |
| Renovate (consumer repos / org preset) | Bumps it | Freeze; migrate consumers | **Removed from its scope** |
| CI: drift checks, publish workflows, roadmap regen | In scope | In scope | **Removed from its list** |
| The repo's own `ROADMAP.md` | Maintained | Frozen | Dropped from the active set automatically |

Notes:

- **ROADMAP-INDEX.md** is a manual, point-in-time snapshot (see its
  "Regenerating this table" block). An archived repo leaves the table and gets
  a line in the scope note explaining why. The inventory is scoped to
  non-archived repos by construction (`select(.isArchived==false)`), so once a
  repo is archived it stops being counted — the edit is to keep the historical
  record honest, not to change the denominator retroactively.
- **Automation is the silent cost.** Archiving a repo stops GitHub CI from
  building it, but Renovate, the flatpak tooling drift check, and any roadmap
  regeneration workflow hold their own repo lists. A retired repo left in those
  lists keeps generating open PRs, warnings, or 404s forever. Removing it from
  each list is a required step, not a nicety.
- **Inherited templates are not repo-specific.** The issue forms,
  `project-starter/`, and shared workflows apply to the whole org, so retiring
  one repo does not require a template change — unless that repo inherited a
  *local copy* of a shared artifact, which should be removed with the repo.

## Examples from recent transitions

- **`kde-build-meta` → `tromso` (superseded, then removed).** `kde-build-meta`
  defaulted to `master` and was documented as superseded by `tromso` (active,
  `main`). Its retirement tracker was `tuna-os/kde-build-meta#19`. The repo no
  longer resolves via the GitHub API as of 2026-10-08 — it was archived and then
  removed. The correct sequence was: mark it superseded, migrate consumers to
  `tromso`, archive it, remove it from ROADMAP-INDEX, and record the successor
  in the registry.
- **`bonito-x13s` (archived, historical read-only).** The Lenovo ThinkPad X13s
  bootc/ISO repo (`aarch64/Qualcomm SC8280XP`) was archived on 2026-08-12 with
  no successor — the hardware is end-of-life. It is kept as historical
  reference and marked read-only on the org profile. No roadmap, no automation,
  no further planning.
- **`ubuntu`, `letters` (archived together).** Both were archived 2026-08-12
  and excluded from ROADMAP-INDEX's active scope. Same pattern: archived,
  read-only, dropped from the inventory.
- **`suite-common-rust` (deprecated, gate open).** Its README marks it
  `DEPRECATED` and points consumers at `gtk-office-suite/suite-common/`, but the
  org has not archived it. This is the open case: it is still open on GitHub, so
  Renovate, CI, and reviewers still touch it. Closing the gate (audit →
  maintainer confirms → archive → stop automation → update artifacts) is exactly
  the deprecated → archived procedure above.

## Decision ownership

Lifecycle decisions span the whole portfolio, so ownership is explicit:

- **Maintainer.** Only an org maintainer can archive or un-archive a repository
  (it is a GitHub repository setting). Only a maintainer can close a gate or
  remove a repo from org-wide automation scopes. This doc can describe the
  process; it cannot perform the archive.
- **Portfolio Lifecycle Coordinator.** The role is not filled yet. It would
  track gates across the portfolio, verify they close on time, and escalate
  overdue ones. A maintainer assigns a name.
- **Strategist / architect / guide agents.** They surface milestones, record
  state in the registry, and maintain these docs. They do not own the
  retirement decision and cannot archive a repo.

## Verifying a repo's state

Never assume. Resolve the default branch and archived flag per repo rather than
guessing:

```bash
gh api repos/tuna-os/<repo> --jq '{default_branch, archived, archived_reason, pushed_at}'
```

Then confirm the org artifacts agree:

```bash
# Is it still in the active inventory?
gh api repos/tuna-os/<repo> --jq '.default_branch'   # then check ROADMAP-INDEX
# Is automation still touching it?
grep -rn "<repo>" .github/workflows/ renovate.json 2>/dev/null
```

`archived: true` with `pushed_at` months old is retired history. `archived:
false` with a `DEPRECATED` README and a migrated consumer base is a gate ready
to close.

## Related

- [ROADMAP-INDEX.md](ROADMAP-INDEX.md) — the active-repository inventory;
  excludes archived repos by scope.
- [Portfolio Lifecycle Registry](docs/portfolio-lifecycle.md)
  (tuna-os/.github#112) — the deprecated/archived counterpart: state,
  ownership, and gates.
- [CONTRIBUTING.md](CONTRIBUTING.md) — how to contribute; points at these
  artifacts to tell active work from retired work.
- tuna-os/.github#134 — the finding that asked for these procedures.

---

*Maintained as an organization-level governance artifact. Changes land by PR
against this file. Archiving is a maintainer-only GitHub action; this doc
describes the process and the follow-up updates, but a maintainer performs it.
— hive: backend=omp model=lab-worker/ornith*
