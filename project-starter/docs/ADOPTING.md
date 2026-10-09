# Adopting TunaOS project patterns

## Baseline

Use a Justfile as the public local interface. `just check` must run the same fast checks that CI runs. Keep `e2e`, releases, and screenshot capture explicit or scheduled when they require privileged hardware, long execution, or secrets.

Enable the CI template only after replacing the checkout action version with the organisation’s current pinned policy and installing the project's tools. Configure branch protection to require **only** `CI / required-checks`; update its `needs` list whenever a new required job is added.

## Dependency updates

The organisation baseline automerges `minor`/`patch`/`pin`/`pinDigest`/`digest` Renovate updates, after branch protection passes — `major` updates always need human review before merge (tuna-os/.github#12). Do not widen `renovate.json`'s automerge `matchUpdateTypes` to include `major`, and do not set top-level `automerge`/`platformAutomerge` to `true` — that reintroduces exactly the org-gate bypass tracked in tuna-os/tunaOS#1612. The tuned OS configuration adds custom managers for image digests and pinned workflow SHAs. Copy those custom managers only when those file formats exist. For an upstream that moves several times a day, use `minimumReleaseAge` to coalesce updates.

Validate any hand-edited `renovate.json` with `npx -p renovate renovate-config-validator` before committing — a syntactically invalid config (e.g. a stray `"ignore": true` key, which isn't valid Renovate schema) silently halts *all* Renovate PRs for the repo, not just the one broken rule. That only catches schema errors, not policy violations: a config can be perfectly valid JSON and still automerge major (that's exactly how tunaOS#1612 happened). `ci.yml`'s `renovate-policy` job runs `scripts/check-renovate-automerge-policy.py` against `renovate.json` on every push and PR, resolving the same rule-layering Renovate itself does (top-level `automerge`, overridden in order by each `packageRule`) and failing the build if any path leaves `major` automerging — keep that job in `required-checks`' `needs` list.

### Validating the policy locally

Schema validation and policy validation are complementary, not interchangeable. `npx -p renovate renovate-config-validator` (above) rejects a *syntactically invalid* config; `scripts/check-renovate-automerge-policy.py` rejects a *valid* config that still automerges a `major` update — the class that passed the schema validator in tunaOS#1612. Run the checker locally before you commit, the same way CI runs it on every push and PR:

```bash
python3 scripts/check-renovate-automerge-policy.py renovate.json
```

It exits 0 when compliant and 1 when it finds a rule that automerges `major`, printing the offending rule and the policy it breaks (`tuna-os/.github#12`). When it fails, read the printed rule: the fix is to stop an `automerge: true` path from reaching `major`, either by removing the broad `automerge: true` (top-level, or a `packageRule` with no `matchUpdateTypes`, which applies to every update type) or by adding an explicit `{"matchUpdateTypes": ["major"], "automerge": false}`. Do the `renovate-config-validator` pass first if you haven't — a config that fails schema validation halts *all* Renovate PRs, and you won't get a clean policy answer until it is fixed.

The check resolves `renovate.json` the way Renovate does: top-level `automerge` is the default, then each `packageRule` is applied in order with later rules winning. That ordering is what trips people up, because a rule that looks like it closes the gap can still leave `major` automerging, and `automerge` can be *reintroduced* at a lower level even when the top level disables it. An example that looks valid but violates the policy:

```json
{
  "automerge": false,
  "packageRules": [
    { "matchUpdateTypes": ["major"], "automerge": true }
  ]
}
```

Top-level `automerge: false` says no, but the later rule re-enables it for `major`, and the checker reports it. The mirror-image trap is a *scoped* rule that only covers one package:

```json
{
  "automerge": true,
  "packageRules": [
    { "matchPackageNames": ["left-pad"], "matchUpdateTypes": ["major"], "automerge": false }
  ]
}
```

That disables `major` for `left-pad` only; the top-level `automerge: true` still automerges `major` for every other package, and a scoped rule can never cancel that broader path. The checker treats any rule that scopes by package, datasource, or manager as unable to clear a broader violation (the `SCOPING_KEYS` block in `scripts/check-renovate-automerge-policy.py`), so a narrow override is never mistaken for a closed gap.

`ci.yml`'s `renovate-policy` job runs this same script on every push and PR — the same rule-layering resolution described above, wired into `required-checks`' `needs` list — so the layering traps just shown are exactly what it catches: a config that looks valid locally and violates policy cannot merge. Run the local check first so you hit those failures cheaply, on your own machine, before the gate does.

## Flatpak remote

The central remote pattern in `tuna-os/docs` is intentionally two-stage:

1. Build each manifest in a known Flatpak builder environment and export OCI.
2. Publish the OCI and update the central static index only after a successful build.
3. Deploy the site when `static/flatpak/**` changes.
4. Run a remote sanity check that consumes the generated `.flatpakrepo`.

Do not grant cross-repository credentials to pull-request runs. Put index mutation behind trusted events and use a dedicated, minimally scoped token.

## Documentation evidence

TunaOS captures installer/desktop screens from QEMU, uploads artifacts even on failure, validates that capture meaningfully succeeded, and then a docs-side workflow imports the newest successful artifacts and regenerates the guide. This avoids hand-maintained product tours going stale.

The reusable rule is: **test the product, retain the evidence, publish only validated evidence.**

## Release and operational guardrails

- Serialize semantic releases on the protected default branch; queue rather than cancel releases.
- Use concurrency cancellation for superseded CI, but not for releases or remote mutations.
- Retain logs and artifacts on failure. Give each long-running stage its own timeout.
- For fork PRs, never run privileged QEMU/KVM jobs or expose secrets. Guard with a same-repository condition.
- Prefer containerized development/test environments where host toolchain drift is costly.
- Commit generated assets only when changed and mark generated-doc commits to avoid recursive CI where appropriate.
