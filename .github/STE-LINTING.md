# Simplified Technical English (STE) linting

This repo lints prose in every other org repo. This guide explains the setup
and how to bring a new repo into compliance. Read it before you add the
workflow to a repo.

## What STE is

Simplified Technical English is a controlled language. It has a set of prose
rules and a dictionary of approved words. The standard is ASD-STE100. The
Aviation Specification Board is the publisher of this standard. This repo applies Part 1 from
[`.github/actions/ste-lint/ste-rules.mjs`](actions/ste-lint/ste-rules.mjs).

Part 2 (the dictionary) stays out of the code.
That part is a controlled document owned by ASD. An out-of-date copy would be
worse than none. The goal is prose that reads the same for every reader,
including readers whose first language is not English.

## Why it matters for docs

The docs aggregator builds pages from repo READMEs. Then it skips the generated
trees on its own run. The next sync reverts a fix in the generated tree. The
real author is another repository. The source check was the missing part.

Every repo answers for its own prose. Only the aggregator has generated trees
to set aside.

## Workflow setup

The check is a workflow you can reuse at
[`.github/workflows/ste-lint.yml`](workflows/ste-lint.yml). It carries its own
`on:` block for `workflow_call`. A caller keeps its own trigger and becomes a
thin job that uses the workflow.

Add a job like this to a repo workflow:
```yaml
jobs:
  ste:
    name: Simplified Technical English
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7
        with:
          # Full history. The advisory report diffs this branch against its
          # base. A shallow checkout has no base, so the report degrades to
          # whole-repo noise.
          fetch-depth: 0
      - uses: tuna-os/.github/.github/actions/ste-lint@main
        with:
          # Seed this on the first run. See "Seeding .ste-budget" below.
          budget: "250"
```

The action uses a commit SHA, not a tag that moves. Callers pin the call to
`@main`. A merge in this repo is live for every repo that calls it. Keep the
call at `@main`; a past commit freezes the rules.

The action reads two inputs:

| Input | Meaning |
| --- | --- |
| `budget` | A number. The maximum violations the run allows. |
| `ste-file` | The path to the rule file. It defaults to the one in this repo. |

## Seeding `.ste-budget`

A budget is a single number. It is the maximum number of violations the repo
tolerates on the day it joins the org. Commit it as `.ste-budget` at the
repo root.

Seed it in three steps:
1. Run the linter once and read the total.
   ```bash
   node .github/actions/ste-lint/ste-lint.mjs --summary
   ```
   The `--summary` flag prints counts per file and every opt-out with its
   reason. It also lists the trees the run treated as generated.
2. Commit that number to `.ste-budget`. Write it by hand if your shell
   chokes on the extraction. The file holds one integer and nothing else.
3. Point the workflow at the file. Drop the `budget:` input and keep the
   `.ste-budget` file in the tree.

Do not set the budget to zero. A gate that fails on day one dies on day two.
Commit the real count. Let the ratchet (below) pull it down over time.

## How to read a violation

Each violation carries a file, a line, a rule number, and the approved word
when the rule names one. The rule number points at the source file. Read that
line to see the exact rule and its approved replacement.

## How to fix a violation

Replace the flagged word with the approved word the violation names. Rewrite
when you can. Opt out only with a stated reason. Shorten a long paragraph into
two.

## How the gate decides

The report never fails a run. The gate decides pass or fail. It compares the
count to the budget. The gate fails when the count is above the budget.

## The ratchet

The budget is a ceiling, not a floor. The ratchet removes the easy way out. A
new violation pushes the count up. The gate fails. The author must fix it. The
budget then rises to match.

## Writing opt-outs that survive

An opt-out with no reason becomes the default. Then the checker measures
nothing. The checker reports an opt-out with no reason. It also reports a file
without an opt-out, so you see every repo that still needs one.

Two ways to set a violation aside exist, and both need a stated reason:

- A whole file can opt out on its first line. The comment opens a comment,
  names `ste-disable-file:`, gives a reason, and closes the comment.
- A region can opt out between two markers. The first opens the disable state
  with `ste-disable:` and a reason; the second closes it with `ste-enable`.

## The full rule set

The guide covers the rules that touch prose. The source file lists every rule,
including the ones about technical names. Read the source before you change a
rule. The sibling guide shows how to write actions safely.
