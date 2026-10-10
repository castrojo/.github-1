# Developing and Maintaining Shared GitHub Actions

This guide is for the person who *writes* a shared action in this repository.
It covers anatomy, creating a new action, modifying an existing one, versioning,
and the pitfalls that bite people who build actions here.

If you are a repository maintainer deciding whether to *adopt* a shared action,
start with the action's own `README.md` under `.github/actions/` instead. If you
are keeping this repository's workflows green, the Maintainer Runbook is the
operational counterpart.

## The one rule everything else follows

Callers pin this repository at `@main`:

```yaml
- uses: tuna-os/.github/.github/actions/ste-lint@main
```

A merge to `main` is therefore **live for every consumer at once**. There is no
tag to hold a consumer back, and there is no rollback except another commit.
Every action's `inputs:` block is a public API. Renaming an input, or changing
what a default value means, breaks callers silently at their next run.

Treat every change here as if it publishes to every repository simultaneously.
That single fact drives every section below.

## 1. Anatomy of a shared action

Every shared action here is a **composite action**. Its `action.yml` declares
inputs and a list of steps; the real logic lives in the script files the steps
call.

```yaml
name: "My action"
description: >-
  One or two sentences. This text and the inputs below are searchable and
  part of the public contract, so keep them accurate.
inputs:
  oci-dir:
    description: What it does and what it expects. Required inputs say so.
    required: true
  registry:
    description: Default value shown to callers who omit the input.
    required: false
    default: ghcr.io
runs:
  using: composite
  steps:
    - name: Run the logic
      shell: bash
      env:
        OCI_DIR: ${{ inputs.oci-dir }}   # route inputs through env:, never inline
      run: |
        python3 "$GITHUB_ACTION_PATH/my-script.py" --oci-dir "$OCI_DIR"
```

A few parts carry more weight than they appear:

- **`description` fields are part of the contract.** Callers read them to learn
  what an input does. Keep them current when an input's meaning changes.
- **`default:` values are behaviour.** A caller who omits an input relies on the
  default. Changing a default is a breaking change even though no name moves.
- **`required: true` vs a default.** Prefer an explicit `required: true` for
  inputs a caller must always supply. Use a `default:` for inputs that have a
  sensible value most callers share.
- **`outputs:`** declare when an action emits values for the caller to read.
  Declare an output only when you actually write it with
  `echo "name=$(...)" >>"$GITHUB_OUTPUT"`.

The three actions that ship today follow this shape:

| Action | Does | Notable inputs |
|---|---|---|
| [`update-flatpak-index`](../.github/actions/update-flatpak-index) | Updates one app's entry in the central Flatpak index from a local OCI layout | `oci-dir`, `repo-name`, `tags`, `require-appstream` |
| [`publish-flatpak-index`](../.github/actions/publish-flatpak-index) | Runs the update script, then clones, commits, and pushes to the central index — with a retry loop for concurrent writers | adds `token`, `docs-repo`, `max-attempts` |
| [`ste-lint`](../.github/actions/ste-lint) | Checks Markdown prose against ASD-STE100 against a per-repo budget | `budget-file`, `budget`, `run-tests`, `base-ref` |

## 2. Creating a new shared action

Use this checklist. Every item exists for a reason the sections below explain.

1. **Create the directory** `.github/actions/<name>/`. The directory name is the
   last path segment callers use in their `uses:` line, so choose it to describe
   the job, not the implementation.
2. **Write `action.yml`.** Declare `name`, `description`, every `inputs:` with a
   `description`, and the `runs:` block. Route every input through `env:` in the
   script step — never inline it in the `run:` text (see section 5).
3. **Write the script** the steps call, beside `action.yml`. Keep the logic in a
   file, not in a long inline `run: |` block, so it is testable.
4. **Write `README.md`.** Document the inputs and their defaults, a copy-paste
   `uses:` example pinned to `@main`, and what the action does when it fails.
   The README is the human face of the inputs block.
5. **Write tests beside the script.** A checker that is not tested gets switched
   off, and then nothing is checked at all.
6. **Declare permissions.** If the action runs a workflow step, that workflow
   must declare a top-level `permissions:` block (see section 5).
7. **Pin third-party actions.** Any `uses:` of a third-party action inside your
   action pins to a commit SHA, not a version tag (see section 4).

### Minimum template

```yaml
name: "New shared action"
description: >-
  One-line summary of what it does and the job it owns.
inputs:
  example-input:
    description: What the caller supplies and what it means.
    required: true
runs:
  using: composite
  steps:
    - name: Run
      shell: bash
      env:
        EXAMPLE_INPUT: ${{ inputs.example-input }}
      run: |
        python3 "$GITHUB_ACTION_PATH/script.py" --input "$EXAMPLE_INPUT"
```

### Document before you merge

Because the action is live on merge, the `README.md` must ship with it. A caller
reading a new `uses:` line needs the input names, their defaults, and the
failure mode. An action whose inputs are undocumented is a public API with no
manual.

## 3. Modifying an existing action

### Changes that are safe-ish

- **Adding an input** with its own `default:`. Existing callers ignore it. It is
  still live on merge, so add it with a sensible default and document it.
- **Adding an output** that callers can optionally read.
- **Loosening validation** that previously rejected valid input.

None of these are risk-free — they still go live everywhere at once — but they
do not break a caller that already works.

### Changes that break callers

- **Renaming an input** or an output. Callers that pass the old name silently
  get the default, which is usually the slowest kind of failure.
- **Changing a `default:` value.** A caller who omitted the input relied on the
  old value.
- **Changing what a value means.** `tags: latest` meaning "the latest tag" while
  a caller assumed "the literal string `latest`" is a meaning change, not a name
  change.
- **Making a previously-optional input required.** Callers who omitted it now
  fail to start.

### Deprecation strategy

You cannot deprecate an input and keep it quiet: callers run your new code on
their next run, so a removed input breaks them immediately. To deprecate:

1. **Add the replacement alongside the old input.** Keep the old input working
   for a window. Announce the removal date and the replacement.
2. **After the window, remove the old input** in a commit that also updates the
   `README.md` and the `description` fields.
3. **Or convert to a no-op that errors.** If you must remove quickly, replace the
   input's handling with a step that fails with a pointer to the replacement. A
   loud error is better than a silent wrong default.

Communicate the change the same way every change here communicates: a notice
that names the input, what moves, and the replacement. There is no version to
hold consumers back, so the notice is the only advance warning they get.

## 4. Publishing and versioning

### What "publishing" means here

There is no publish step. Committing to `main` *is* the publish. Two levels of
pinning are in play:

- **Your action as consumed by others.** Callers pin this repository at `@main`.
  A merge is live for them at once. See section 3 for how to change behaviour
  without breaking them.
- **Third-party actions your action uses.** Pin *these* to a commit SHA, not a
  version tag. This repository pins them for that reason (for example
  `actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1`). A mutable tag
  like `v4` can move under you and change your callers' behaviour without a
  commit here.

### Why `@main` and not a version tag

This repository does not tag releases of its actions. Callers therefore pin to
`@main`, which always points at the latest merge. The trade-off is deliberate:
`@main` means a bug fix reaches consumers the same minute it merges, at the cost
of no stable intermediate point.

### Emergency rollback

There is no tag to point back to. Rollback is **another commit** that reverts
the change. To make rollback possible in the first place:

- Keep the change small and reviewable so a revert is a clean single commit.
- Get it correct the first time. The runbook's escalation path treats a red
  shared workflow as an emergency precisely because you cannot simply repoint a
  tag.
- If a change must be reversible, tag a known-good commit of this repository
  before merging, so a caller can pin to that SHA while you fix the regression.

### How changes propagate

```
merge to main ──▶ every caller's next run uses the new code
                  (same minute; no staging, no rollout)
```

Because propagation is instant, verify locally before you merge (see section 6).
A change that passes review but fails on the first real run lands everywhere at
once.

## 5. Common patterns and pitfalls

### Never put an input back into a script body

This is the single most important pitfall, and it is load-bearing here. Route
every input through `env:` and read it from the environment. **Do not**
interpolate it into the `run:` text with `${{ }}`:

```yaml
# WRONG — the value becomes shell text
run: python3 script.py --tags ${{ inputs.tags }}

# RIGHT — the value is data, not shell
env:
  TAGS: ${{ inputs.tags }}
run: |
  python3 script.py --tags "$TAGS"
```

GitHub Actions substitutes `${{ }}` expressions into the script **text before
bash parses it**. An interpolated value is therefore parsed as shell. Quoting
narrows the hole but does not close it: a value containing a double quote ends
the quoted region. `update-flatpak-index` routes every input through `env:` for
this reason.

### Multi-value inputs

Some inputs are lists (`tags: latest stable`). The action splits them with
`read -ra` and passes them unquoted so word-splitting spreads them into separate
arguments:

```bash
read -ra tag_args <<<"$TAGS"
python3 script.py --tags "${tag_args[@]}"
```

`nargs="+"` in the script then receives each tag as its own argument. Do this
deliberately; it is the split the multi-tag case needs.

### Validate input before you use it

Fail on malformed input with a clear message, not as a stray argument downstream.
`update-flatpak-index` validates each OCI tag against a regex and errors with the
offending value. A clear failure here is a debugging win for the caller.

### Avoid shell injection

The `env:` pattern above is the injection fix: the value is data, so bash never
reinterprets it. Combined with input validation (previous point), this closes
the hole that `${{ }}` interpolation leaves open. When you must shell out, keep
values quoted and untrusted values validated.

### Keep secrets out of logs and process lists

`publish-flatpak-index` pushes with a token, and it keeps that token out of
logs, config, and process listings:

- It base64-encodes the token through **stdin**
  (`echo -n "x-access-token:$TOKEN" | base64 -w0`) rather than as a command-line
  argument, so the token does not show up in `ps` or process listings.
- It applies the resulting `Authorization` header on a throwaway clone in a
  `mktemp` directory that the action deletes at the end. The token never reaches
  a persistent `.git/config`, `git remote -v`, or shell history.
- It reads the token from a masked GitHub secret routed through the `token`
  input, never as a literal in the workflow or a committed file.

### Fail fast on problems that are not races

`publish-flatpak-index` retries only lost push races. An authentication failure
 is not a race, so it fails immediately with the real reason instead of retrying
eight times and blaming a concurrent writer. Distinguish "retry" problems from
"this is wrong now" problems.

### Declare workflow permissions

A composite action that runs inside a workflow inherits that workflow's
permissions. Every workflow in this repository declares a top-level
`permissions:` block following least privilege. If your action's workflow needs
`contents: write` or `packages: write`, declare exactly that and no more. A
workflow with no block inherits the repository's default token scope, which is
almost always broader than the job needs.

## 6. Verify before you merge

Run these from a checkout of this repository before opening a PR. Both policy
checks are also enforced in CI.

```bash
# Renovate automerge policy on this repo's own config
python3 scripts/check-renovate-automerge-policy.py renovate.json

# Every workflow declares a top-level permissions: block
python3 scripts/check-workflow-permissions.py .github/workflows

# The ste-lint action's own rule tests (run from this checkout)
node .github/actions/ste-lint/ste-lint.test.mjs
```

For touched code, also run the linters for the language you changed:

```bash
shellcheck .github/actions/<name>/*.sh      # shell steps
actionlint .github/workflows/*.yml           # workflow YAML
```

If your action ships a script, run that script's own test suite the same way the
action runs it in CI. `ste-lint` runs `ste-lint.test.mjs` via its `run-tests`
input before it lints; mirror that — ship a test file and run it locally the
same way the action runs it.

## Related documentation

- [`AGENTS.md`](../AGENTS.md) — the blast-radius model and the `env:`-vs-
  injection rule in the repository's own words.
- [`CONTRIBUTING.md`](../CONTRIBUTING.md) — branch prefixes, signed commits, and
  the PR checklist.
- The action `README.md` files under `.github/actions/` — the per-action
  consumer-facing reference this guide complements.
