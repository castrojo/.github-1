# Organization Enablement Roadmap

**Last updated**: 2026-10-08 | **Maintainer**: Tuna OS organization maintainers

## Mission

Make `tuna-os/.github` the reliable organization-wide front door for
contributors and maintainers: shared community-health guidance should work for
every repository, while portfolio-level planning inventories should stay
current enough to support prioritization.

## Current Status

The repository provides shared contribution and security guidance, issue and
pull-request templates, a reusable project starter, and an org-wide roadmap
inventory. Most authorized repositories inherit its issue forms, so changes
here affect the contributor experience across the portfolio.

### Priorities

| Priority | Item | Tracking | Status |
|---|---|---|---|
| P0 | Make inherited issue forms repository-neutral and keep image-specific fields local to `tuna-os/tunaos` | #32 | Not started |
| P1 | Automate default-branch-aware refreshes of `ROADMAP-INDEX.md` | tuna-os/tunaos#1295 | Proposed; manual coverage reached 36/37 |
| P1 | Complete adoption of the canonical Flatpak index action and retire the interim copy-drift guard | tuna-os/tunaos#1183 | In progress |
| P1 | Give inherited planning artifacts a named human owner: remove automation bylines from the starter template and sweep the 37 committed files across 19 repositories that inherited them | #54 | Template fixed (#55); CI check added to prevent recurrence; repository sweep not started |
| P2 | Define an owner and review cadence for org-level community-health files | #32 | Proposed |

## 2026 Q3 Exit Goals

| Goal | Success measure | Tracking |
|---|---|---|
| Correct the shared issue-entry funnel | Shared forms collect repository-neutral context; image-specific forms live in `tuna-os/tunaos`; representative app, library, installer, and CI repositories are verified | #32 |
| Make portfolio planning observable | Maintain the verified 36/37 active-repository baseline; resolve the superseded `kde-build-meta` lifecycle; automation work is separately scoped | tuna-os/tunaos#1295, tuna-os/kde-build-meta#19 |

## 2026 Q4 Goals

| Goal | Success measure | Tracking |
|---|---|---|
| Prevent roadmap inventory drift | A scheduled, default-branch-aware check proposes reviewable updates when repository coverage changes | tuna-os/tunaos#1295 |
| Reduce duplicated release tooling | Callers migrate to the canonical Flatpak index action and the temporary drift guard can be removed | tuna-os/tunaos#1183 |
| Measure contributor-funnel health | Quarterly review records issue-form overrides, misrouted reports, and first-response outcomes | #32 |
| Make governance documents attributable to people | No committed file in the portfolio attributes org policy to an automation agent; every roadmap names a human or team owner | #54 |

## Decision Principles

1. Shared defaults must be useful to every repository that inherits them.
2. Product-specific questions belong in local templates, not the org fallback.
3. Portfolio inventories must query each repository's actual default branch.
4. Scheduled automation should propose reviewable changes rather than silently
   rewrite planning artifacts.

## Review Cadence

Review this roadmap at each quarter boundary and whenever a shared template or
project-starter contract changes. Every roadmap item should link to an issue
with an owner, acceptance criteria, and evidence of completion before its
status is marked done.

## How to Contribute

See [CONTRIBUTING.md](CONTRIBUTING.md). Planning changes should explain which
repositories inherit the affected org-level default and link the tracking
issue used to coordinate any repository-local follow-up.

---
*Maintained as an organization-level planning artifact. Changes land by PR against this
file; see [CONTRIBUTING.md](CONTRIBUTING.md).*
