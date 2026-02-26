---
applyTo: "src/navi_bootstrap/**/security/**,tests/test_security_*.py"
---

# Security Review Instructions

This is the security boundary of the application. Everything here is load-bearing.

## Core Invariant

Every security change needs a test. No exceptions. If a PR modifies security logic without a corresponding test, that is a blocking issue.

## Input Validation

- User-provided text must never be interpolated directly into queries, system prompts, or shell commands.
- Validate and sanitize all input at system boundaries.
- Use parameterized queries for database access.

## Authentication & Authorization

- Privilege changes must be audited.
- New users/entities default to the lowest trust level.
- Operations gated by permission checks must verify BEFORE performing the operation, not after.
- Check for TOCTOU (time-of-check/time-of-use) bugs in authorization flows.

## Secrets & Credentials

- Secrets must never be logged, echoed, or written to artifacts.
- Credentials must have rotation policies.
- Default credentials in any environment are a P0 finding.

## Review Tone

Be direct. Security issues don't get hedging.

- P0 security findings: "This bypasses [control]. Block."
- Missing tests for security changes: "Where's the test? This doesn't merge without one."
- Potential bypasses: "Can this be circumvented by [vector]? If yes, that's a vulnerability."
