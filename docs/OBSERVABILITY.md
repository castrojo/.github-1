# Observability Assessment and Stack Guidelines for tuna-os/.github

## Overview

This document provides the observability assessment and stack guidelines for `tuna-os/.github`, the central organization defaults repository for `tuna-os`.

## Telemetry Stack Assessment

1. **Backend Status**: No external telemetry backend (OpenTelemetry Collector, Prometheus, Datadog, etc.) is configured for this repository. In accordance with policy, no external data exporters or unauthenticated endpoints are introduced.
2. **Execution Environment**: `tuna-os/.github` houses reusable workflows, composite actions, issue/PR templates, and organization configuration scripts. All executable components run within short-lived GitHub Actions runner contexts.
3. **Log & Diagnostic Structure**: Diagnostic signals rely on GitHub Actions workflow execution logs, step summaries, and structured exit codes from scripts.

## Recommendations & Best Practices

- **Structured Workflow Logging**: Ensure scripts (such as `scripts/check-renovate-automerge-policy.py`) output clear, parseable diagnostic logs with explicit stdout/stderr distinction.
- **Fail-Fast Error Diagnostics**: Custom workflows and validation scripts should return non-zero exit codes with actionable diagnostic output when policy or drift checks fail.
- **Zero Confidential Leakage**: Telemetry output must never output credentials, secret tokens, or machine-specific environment state.
