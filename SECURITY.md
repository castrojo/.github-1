# Security Policy

TunaOS ships bootable container images and installer tooling. We take
security reports seriously.

## Reporting a vulnerability

**Do not open a public issue** for security vulnerabilities. Instead, use
GitHub's private vulnerability reporting:

1. Go to the affected repository (e.g. https://github.com/tuna-os/tunaOS).
2. Open **Security → Report a vulnerability** (or **Advisories → New draft
   security advisory**).
3. Include: affected repo + component, a minimal reproduction, impact, and —
   if known — a suggested fix.

Alternatively, contact the maintainers privately via a GitHub **Security
Advisories** in `tuna-os/tunaOS` if the affected repo does not have reporting
enabled.

## What to report

- Remote code execution or privilege escalation in installer / migration tooling.
- Unsafe handling of credentials, tokens, or secrets in CI workflows or built images.
- Supply-chain issues: unpinned dependencies, tampered build inputs, or
  unverified vendored binaries.
- Image content that violates the project's trust model (bootc layers, flatpaks,
  COPR packages).

## Disclosure

We aim to acknowledge reports within **5 business days** and ship a fix
through the normal release pipeline. We prefer coordinated disclosure:
please give us a reasonable window before publishing details.

## Scope

In scope: all `tuna-os/*` repositories and the artifacts they build.
Out of scope: third-party upstream projects we consume (bootc, GNOME, KDE,
COSMIC, Flatpak runtimes, etc.) — report those to their own maintainers.

## Automation note

This organization uses automated agents (hive) that open issues and PRs.
Reports about agent behavior should go through the same private channel; do
not engage an automated bot with sensitive details in a public issue.
