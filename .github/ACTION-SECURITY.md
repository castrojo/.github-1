# Action input security: route inputs through `env:`, not interpolation

Every composite/script action in this org is a small shell program. Its
arguments come from `inputs:`. Those inputs are attacker-controlled. Any repo
that `uses:` the action writes into them. Any caller that supplies a `with:`
value from a pull-request workflow writes into them too. Treat every input as
untrusted shell.

The one rule that keeps an input data instead of code:

> **Never substitute a user-facing input into a script body with
> `${{ }}`. Route it through `env:` so the shell expands it as a value, never
> as text it parses.**

This is not defensive style. It is load-bearing in
[`.github/actions/update-flatpak-index/action.yml`](actions/update-flatpak-index),
the migration target for eight repos whose jobs hold `packages: write` and
`FLATPAK_INDEX_TOKEN`. The sections below explain why, show the exploit against
the rendered script, and give the pattern to copy.

## Why interpolation is unsafe

GitHub Actions substitutes `${{ }}` expressions into the script text before the
runner hands the script to bash. The interpolated value is therefore code, not
data. bash parses it.

```yaml
- shell: bash
  run: |
    python3 update-index.py --tags ${{ inputs.tags }}
```

A caller that passes `tags: latest; touch /tmp/PWNED` renders this:

```sh
python3 update-index.py --tags latest; touch /tmp/PWNED
```

bash parses the semicolon as a command separator and runs `touch /tmp/PWNED`.
We demonstrated this live against the rendered script in `update-flatpak-index`.
`tags: latest; touch /tmp/PWNED` created the file, and the step exited 0, so the
injection looked like a clean run.

## Why quoting narrows but does not close the hole

The instinct is to quote the interpolation:

```yaml
run: |
  python3 update-index.py --tags "${{ inputs.tags }}"
```

A payload without an embedded quote — `latest; touch /tmp/PWNED` — stays trapped
in one argument and does not execute. But a value with a double quote ends the
quoted region:

```
inputs.tags = latest" ; touch /tmp/PWNED ; echo "
```

This renders to:

```sh
python3 update-index.py --tags "latest" ; touch /tmp/PWNED ; echo ""
```

`touch /tmp/PWNED` runs. Quoting narrows the surface. A payload without a quote
is neutralized. But a quote in the value escapes. Do not rely on quoting as the
control.

## The pattern: `env:` makes inputs data

An `env:` value is expanded by the shell after the command line is already
parsed. It can only become a value. It cannot introduce a new command or change
command structure.

```yaml
- shell: bash
  env:
    TAGS: ${{ inputs.tags }}
  run: |
    set -euo pipefail
    read -ra tag_args <<<"$TAGS"
    python3 update-index.py --tags "${tag_args[@]}"
```

`TAGS` is data. `read -ra` splits it into an array. `"${tag_args[@]}"` expands
each element as its own fully-quoted argument. Bash has no text to parse as
commands, so no payload can escape.

### The multi-value case: `read -ra` vs bare word-splitting

An input is sometimes a space-separated list (tags, paths, names). You must
split it deliberately. But the split must come from an env var, not from leaving
an interpolated value unquoted.

```sh
# Safe: the list is data. read -ra splits it. The quotes keep each tag whole.
read -ra tag_args <<<"$TAGS"
python3 update-index.py --tags "${tag_args[@]}"

# Unsafe in spirit: a bare $TAGS relies on word-splitting. A reader cannot tell
# that from an interpolated ${{ inputs.tags }} — the exact pattern that was exploitable. Always name the env var and quote the expansion.
```

`update-flatpak-index` validates each tag against the OCI grammar before it
reaches `update-index.py`. A malformed input is a clear `::error` here, not a
stray argument downstream:

```sh
read -ra tag_args <<<"$TAGS"
if [ "${#tag_args[@]}" -eq 0 ]; then
  echo "::error::tags input is empty" >&2
  exit 1
fi
for tag in "${tag_args[@]}"; do
  if ! [[ "$tag" =~ ^[A-Za-z0-9_][A-Za-z0-9._-]{0,127}$ ]]; then
    echo "::error::invalid OCI tag: $tag" >&2
    exit 1
  fi
done
```

## Secrets always go through `env:` — never in `with:` or a URL

Route a secret through `env:`. Keep it out of process arguments, `.git/config`,
and the log.

`publish-flatpak-index` takes `token: ${{ secrets.FLATPAK_INDEX_TOKEN }}` and
moves it straight into the environment:

```yaml
env:
  FLATPAK_INDEX_TOKEN: ${{ inputs.token }}
```

Then it authenticates with a header written over stdin so the token never lands
in `git remote -v`, `.git/config`, or a process listing:

```sh
export GIT_TERMINAL_PROMPT=0
auth_header="AUTHORIZATION: basic $(echo -n "x-access-token:$FLATPAK_INDEX_TOKEN" | base64 -w0)"
git -C "$INDEX_REPO" config --local http.extraheader "$auth_header"
```

It also fails fast on an empty token. It does not retry against concurrent
writers and blame them for an auth failure the caller cannot see.

## The safe `with:` vs `env:` split

Not everything belongs in `env:`. `setup-node` takes `node-version` through
`with:`. A version number is not a shell argument. The action reads it in its
own input handling, and the action never expands it into a command line. The
rule of thumb:

- **`with:`** for inputs the action consumes natively (a version number, a
  selector, a boolean flag the action reads in JS or Python).
- **`env:`** for anything that becomes a value inside a `run:` script, and every
  value that a script turns into a shell argument.

`ste-lint` follows this split. `node-version` is a `with:` input. The strings
and booleans the script expands into commands (`budget-file`, `budget`,
`base-ref`, `annotations`) all travel through `env:`.

## When to apply this

Apply it to any action that accepts a user-controlled string and puts it into a
shell command as an argument. Checklist:

- [ ] Every input that reaches a `run:` script is declared under `env:`, not interpolated with `${{ }}` in the `run:` text.
- [ ] Values that become shell arguments are quoted on expansion (`"$VAR"`, `"${arr[@]}"`).
- [ ] Space-separated list inputs are split with `read -ra` (or equivalent) against the env var, never by leaving a var bare.
- [ ] Untrusted inputs are validated against an allow-list grammar before they reach a downstream tool, so a bad value is a clear error, not a stray arg.
- [ ] Secrets go through `env:` and never appear in `with:`, a URL, a command, or a log line.

If a script builds an argument out of `${{ inputs.* }}` anywhere, a caller can
inject shell with the same payload that created `/tmp/PWNED`.

## The actions this documents

| Action | Pattern |
|---|---|
| [`update-flatpak-index`](actions/update-flatpak-index) | `env:` for every input, `read -ra` + OCI-tag validation, `"${tag_args[@]}"` |
| [`publish-flatpak-index`](actions/publish-flatpak-index) | secret through `env:`, header-based git auth, fail-fast on empty token |
| [`ste-lint`](actions/ste-lint) | the safe `with:` (native) vs `env:` (script) split |

All three live under [`.github/actions/`](actions).
