# ste-lint

Checks Markdown prose against [ASD-STE100](https://asd-ste100.org/) —
Simplified Technical English — with a per-repo budget.

Most repos should call the reusable workflow rather than this action directly:

```yaml
jobs:
  ste:
    uses: tuna-os/.github/.github/workflows/ste-lint.yml@main
```

## What it checks

Sentence length (20 words procedural / 25 descriptive), active voice, `-ing`
forms, approved words, noun clusters of more than three words, and paragraphs
longer than six sentences.

## Budget, not zero

The check reads `.ste-budget` — the maximum number of findings the repo
tolerates. The number only ever goes down; lower it whenever a batch of prose
lands. A gate that fails on day one gets disabled on day two, so **seed a new
repo with its current count** rather than with `0`:

```sh
node .github/actions/ste-lint/ste-lint.mjs --summary   # from a checkout of tuna-os/.github
```

Take the total, commit it as `.ste-budget`, then ratchet.

## What it checks by default

`docs/` and `blog/` if present, plus `README.md`, `CONTRIBUTING.md`,
`SECURITY.md` and `CODE_OF_CONDUCT.md`. All optional — a repo with none of
them checks nothing and passes.

## Opting a file out

A file can opt out **in its own text**, with a stated reason. A reason is
required: it is what stops the opt-out list from becoming a place where prose
goes to be forgotten. Existing reasons include published blog posts (editing
one to satisfy a linter rewrites the record), the Contributor Covenant (quoted
as published), and bibliographies (link text reproduces others' titles).

## The docs aggregator

`tuna-os/docs` skips `docs/<slug>/` trees written by its `sync-org-docs.mjs`,
because a fix there is reverted by the next sync and the real author is another
repository. That detection is resolved at runtime from the repo being checked,
so it is active in the aggregator and inert everywhere else — which is why
running this check *in the source repos* is what actually gets that prose
covered.

## What a failing run tells you

A bare `STE budget exceeded: 251 > 247` is a total, not a hint. The run now
says what to fix, where:

- On failure, the full detail follows the verdict: `file:line`, rule number,
  what is wrong, and — where the rule names one — the approved replacement.
  Reproduce it locally with `just ste`.
- On pull requests, an advisory section reports only what the branch itself
  introduced, as `::warning` annotations that render inline on the PR's Files
  tab. It never decides pass/fail; the budget gate does.

For agents: `ste-lint.mjs --changed-only --base origin/main --format json`
prints one object per new finding (`file`, `line`, `rule`, `message`,
`sentence`) on stdout, with human context on stderr. Parse that instead of
scraping the log.

## Security

The inputs this action expands into shell commands (`budget-file`, `budget`,
`base-ref`, `annotations`) all travel through `env:`; the one `with:` input,
`node-version`, is a number the action consumes natively, not a shell
argument. See [`.github/ACTION-SECURITY.md`](../../ACTION-SECURITY.md) for the
rule behind the `with:` vs `env:` split.
