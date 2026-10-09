# ROADMAP-INDEX.md maintenance

This file is the operating procedure for
`ROADMAP-INDEX.md` — the org-wide inventory of which `tuna-os` repositories
ship a `ROADMAP.md`. `ROADMAP-INDEX.md` is the snapshot; this document is how
the snapshot is kept accurate. Read this before you touch the table, and point
anyone who asks "how do I refresh the roadmap index?" here.

## 1. Scope and meaning

"ROADMAP.md coverage" answers one yes/no question per repository: **does a
`ROADMAP.md` exist at the root of this repo's default branch?**

The table has three columns:

| Column | Meaning |
|---|---|
| Repo | The `tuna-os` repository name. |
| Default branch | That repo's resolved `default_branch` (never assumed). |
| ROADMAP.md? | `✅` if `ROADMAP.md` is reachable at `ref=<default_branch>`, else `❌`. |

What it measures and what it does **not**:

- It measures **presence on the default branch**, not roadmap quality, depth,
  or whether the roadmap is reachable from other branches.
- The **denominator** is every non-archived repo returned by
  `gh repo list tuna-os --limit 200` — currently **40**. It is not the number
  of rows already in the table.
- **Exclusions**: `ubuntu` and `letters` — both archived 2026-08-12. Archived
  repos take no planning by definition and are dropped from the denominator.
- A `❌` row is a deliberate lifecycle call for some repos (e.g. `kde-build-meta`
  is documented as superseded by `tromso`); absence of a row is a different,
  worse failure (see §2 and §4).

## 2. Why it drifts

The inventory is a point-in-time snapshot of a moving target. It goes stale in
four distinct ways, and each is easy to miss:

1. **New repos appear silently.** A repo created outside the table's existing
   rows produces no error, no wrong `❌`, and no count change — the row is just
   missing. Re-checking only the rows already present cannot notice a repo being
   born. (`spindle` was created 2026-08-26 and stayed absent until the 2026-09-02
   pass; it is now the highest-velocity repo in the org.)
2. **Default branches change.** A `ROADMAP.md` merged to the old default branch
   is invisible once the default moves. `bootc-installer` had a `ROADMAP.md` on
   `main` for two days while its actual default was `dev` (82 commits ahead) —
   the exact inventory method missed it.
3. **PRs target a non-default branch.** A roadmap PR merged to a feature branch
   never counts, even though the work exists.
4. **The denominator moves.** Repos archived, deprecated, or renamed change the
   denominator and the `❌` list together.

The downstream cost is real: `tunaos/ROADMAP.md`'s Community section checks
against this table's count, so a stale table lets that claim drift — which is
exactly how it last landed at "9/42" against a real 15/37.

## 3. Refresh procedure

Regenerate the table from source of truth (`gh repo list`), never by editing
rows by hand. Run this from any checkout with the `gh` CLI authenticated:

```bash
gh repo list tuna-os --limit 200 --json name,isArchived --jq \
  '.[] | select(.isArchived==false) | .name' | sort > /tmp/active_repos.txt
while read -r repo; do
  branch=$(gh api "repos/tuna-os/$repo" --jq '.default_branch')
  if gh api "repos/tuna-os/$repo/contents/ROADMAP.md?ref=$branch" >/dev/null 2>&1; then
    echo "$repo|$branch|yes"
  else
    echo "$repo|$branch|no"
  fi
done < /tmp/active_repos.txt
```

Steps:

1. Run the block above and capture the output.
2. Diff it against the committed table in `ROADMAP-INDEX.md`.
3. For every difference, record the cause (new repo / default-branch move /
   roadmap merged / repo archived) — a row change with no note is a half-finished
   refresh.
4. Update the table, bump the "Last verified" date at the top, and add a one-line
   scope note if the denominator changed.
5. Open a PR against `main` (see §6 for cadence).

**Do not swap the exit-code check for a string check.** The `then` branch keys
off `gh api`'s **exit status** (`>/dev/null 2>&1`), not on capturing `--jq`
output and testing for emptiness. On a 404, `gh api` prints the raw JSON error
body to stdout *past* a `--jq` filter, so a string test reports a false "has a
roadmap" positive. This is the single most common bug in a hand-rewritten copy
of the block.

## 4. Scope trap: never hardcode `main`

The table resolves each repo's `default_branch` at refresh time. **Hardcoding
`main` is how a roadmap got stranded on the wrong branch while `dev` stayed
unplanned**, and it is the failure this maintenance process exists to prevent.

The following active repos do **not** default to `main` (verify each refresh, as
these change):

| Repo | Default branch |
|---|---|
| `blueshell` | `ptyxis-port` |
| `hive` | `v4` |
| `fisherman` | `dev` |
| `bootc-installer` | `dev` |
| `changelog-action` | `master` |
| `kde-build-meta` | `master` |
| `mariner` | `master` |

A hardcoded-`main` refresh reports all of these against the wrong ref — either
a false `❌` (roadmap exists on the real default) or a false `✅` (a roadmap
merged to `main` that is not the default). Resolve the default per repo, the way
the §3 block does.

## 5. Automation plan

The manual refresh in §3 works but relies on a human remembering to run it at
the quarter boundary — the same class of human forgetfulness that let
`tunaos/ROADMAP.md` drift. The fix is a scheduled workflow that regenerates the
table and opens a drift PR, so the inventory cannot go stale unobserved.

- **Tracked by** [tuna-os/tunaos#1295](https://github.com/tuna-os/tunaOS/issues/1295)
  (original coverage-gap finding) and
  [tuna-os/tunaos#1361](https://github.com/tuna-os/tunaOS/issues/1361)
  (inventory-drift + stranded-branch bug). #1295 is closed (2026-09-24) as the
  finding; the *automation* it proposes has not yet landed in this repo.
- **Why it is blocked.** A scheduled workflow cannot be trusted on local
  reasoning alone — it needs a real CI run to validate the schedule, the drift
  comparison, and the auto-PR. And a fork PR does not run CI by default; a
  maintainer must enable "allow CI for fork PRs" before that validation pass can
  happen. Until one scheduled/dispatched run completes green, the automation
  stays "proposed".
- **Unblocking steps.** (1) Land the workflow + generator in this repo as a PR
  against `main`. (2) Have a maintainer allow fork CI. (3) Trigger one
  `workflow_dispatch` run and confirm it reports drift correctly and opens a PR.
  (4) Switch the schedule to weekly. An implementation exists as
  [tuna-os/.github#211](https://github.com/tuna-os/.github/pull/211)
  (`scripts/roadmap-index.py`, `scripts/test-roadmap-index.py`,
  `.github/workflows/roadmap-index-automation.yml`) — review and merge that
  rather than re-deriving the approach.

## 6. Quarterly checklist

Refresh **when either** of these fires:

- **Quarter boundary** — Q1 Mar 31, Q2 Jun 30, Q3 Sep 30, Q4 Dec 31.
- **Any roadmap or repository lifecycle campaign** — a new repo created, a repo
  archived/deprecated, a default-branch change, or a batch of roadmap merges
  (e.g. after a "get every repo planned" push).

**How:** run the §3 procedure, record the cause of every diff, bump the
"Last verified" date, open a PR against `main`. Once the automation in §5 lands,
this checklist becomes a *review* step (triage the drift PR) rather than a
manual regeneration.

## Related

- [`ROADMAP-INDEX.md`](../ROADMAP-INDEX.md) — the snapshot this maintains.
- [tuna-os/tunaos#1295](https://github.com/tuna-os/tunaOS/issues/1295) — original
  coverage-gap finding; tracks the automation.
- [tuna-os/tunaos#1361](https://github.com/tuna-os/tunaOS/issues/1361) —
  inventory drift + bootc-installer stranded-branch bug.
- [tuna-os/.github#52](https://github.com/tuna-os/.github/issues/52) — scope gap:
  `spindle`, `blueshell`, `hive` absent from the table (37 → 40 denominator).
- [tuna-os/.github#211](https://github.com/tuna-os/.github/pull/211) — the
  automation implementation (review/merge target for §5).
- [tuna-os/.github#218](https://github.com/tuna-os/.github/pull/218) — inline
  "Maintenance & ownership" section in `ROADMAP-INDEX.md`; the maintenance
  *policy* lives here in the dedicated file.
