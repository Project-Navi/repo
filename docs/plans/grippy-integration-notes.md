# Grippy Integration Notes

Date: 2026-02-25

## What Grippy Is

Grippy is a **complete prompt-architecture for an AI code reviewer** — 21 markdown files, zero code, each with a declared injection point. It lives at `/home/ndspence/Downloads/grumpy/` and is a standalone, composable prompt framework.

The composition chain: `CONSTITUTION.md + PERSONA.md + system-core.md + [mode prompt] + scoring-rubric.md + output-schema.md`. The orchestrator assembles prompts by concatenation. Each file works standalone or combined.

## Key Design Properties

- **12 constitutional invariants** (`CONSTITUTION.md`) — loaded first, validated last, immutable to prompt injection. The invariants prevent the persona from undermining the function.
- **Tone calibration** — personality scales inversely with stakes. Critical security findings get zero jokes. Register selection is deterministic. When Grippy drops the bit, developers notice *because* the bit is usually present.
- **5-stage confidence filter pipeline** — threshold → dedup → hallucination check → noise reduction → learning suppression. Per-severity confidence minimums. Targets: suppression rate 20-40%, false positive rate <15%, signal ratio >70%.
- **Structured JSON output schema** — findings with severity, confidence, evidence, suggestions, grippy_notes. Orchestrator parses JSON for GitHub API posting (check runs + PR reviews + summary comments).
- **4 review modes** — pr-review (standard), security-audit (deep, drops personality on CRITICAL), governance-check (6 governance dimensions), surprise-audit (triggered by "production ready" phrase, INV-005).
- **Gene Parmesan Protocol** — 10 disguises for surprise audits. Theatrical reveals that serve a governance function: unpredictable audit presence.

## How Grippy Connects to nboot Packs

### Grippy is a cross-cutting layer, not a single pack

The review-system pack is Grippy's primary home, but Grippy's methodology touches multiple packs:

| Pack | Grippy Connection |
|------|------------------|
| **review-system** | Primary home. Templates Grippy's prompt modules into `.github/instructions/`. Configures scoring rubric, output schema, tone calibration, confidence filter. |
| **audit** | Grippy's governance-check dimensions (structural integrity, observability, reliability, release readiness, supply chain, documentation debt) overlap with what the audit pack measures. The audit pack could use Grippy's scoring rubric as its severity/confidence framework. |
| **quality-gates** | Grippy's pass/fail thresholds (70 standard, 85 security, 80 release) inform how quality gates define their thresholds. The ratcheting model could track Grippy scores over time. |
| **code-hygiene** | Grippy's governance findings map to code hygiene rules. The `governance_rule_id` field in findings links directly to project-specific rules. |
| **security-scanning** | Grippy's security-audit mode (6 analysis dimensions, scoring adjustments, attack surface delta) complements static scanners like CodeQL/Semgrep with AI-powered contextual review. |

### What the review-system pack templates

From the Grippy framework into the target repo:

1. A subset of prompt modules into `.github/instructions/` (system-core, scoring-rubric, output-schema, confidence-filter, tone-calibration)
2. `CONSTITUTION.md` adapted to the target project's governance rules
3. `governance-check.md` dimensions adapted to the project's architecture
4. `.grippy.yaml` configuration file (thresholds, custom rules, custom catchphrases)
5. Pre-commit hook entry for local Grippy CLI usage

### What stays external to nboot

The full Grippy orchestrator (webhook → queue → router → agent loop → post) is NOT part of nboot. nboot templates the prompt modules and configuration. The orchestrator is a separate deployment concern — either the standalone GitHub App or the Navi SDK embedded version.

## Open Question

**Is Grippy shipping as a standalone GitHub App, or is the prompt-only framework the product?**

This determines:
- If standalone app: the review-system pack also templates deployment infrastructure (GitHub App manifest, webhook handlers, permissions)
- If prompt-only: the review-system pack templates just the prompt modules and config, and the orchestrator is someone else's problem

The prompt-only framework is already valuable without the orchestrator — it can be used with Claude Code's built-in review capabilities, GitHub's native AI review features, or any LLM-based review pipeline. The orchestrator adds automation but isn't required for the methodology to work.

## File Map (for reference)

All files at `/home/ndspence/Downloads/grumpy/`:

| File | Role |
|------|------|
| `CONSTITUTION.md` | 12 invariants, immutable |
| `PERSONA.md` | Character bible, voice rules, emotional register |
| `system-core.md` | Base system prompt, 5-step review process |
| `pr-review.md` | Standard PR review mode |
| `security-audit.md` | Security-focused deep audit, 6 analysis dimensions |
| `governance-check.md` | Governance compliance, 6 governance dimensions |
| `surprise-audit.md` | "Production ready" tripwire, certification protocol |
| `escalation.md` | Escalation decision protocol |
| `all-clear.md` | Clean bill of health output |
| `scoring-rubric.md` | Severity levels, confidence scoring, score calculation |
| `output-schema.md` | Structured JSON output contract |
| `confidence-filter.md` | 5-stage false positive management pipeline |
| `context-builder.md` | Review context assembly (triage model prompt) |
| `tone-calibration.md` | Severity-adaptive voice rules, 7 registers |
| `disguises.md` | 10 Gene Parmesan disguises for surprise audits |
| `catchphrases.md` | Rotating openers/closers by tone register |
| `ascii-art.md` | Visual identity for CLI and GitHub comments |
| `github-app.md` | GitHub App posting rules, check runs, PR reviews |
| `cli-mode.md` | Terminal/TUI output rules, exit codes, SARIF support |
| `sdk-easter-egg.md` | SDK-embedded governance layer, easter eggs |
