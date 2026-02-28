# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Project Overview

**navi-bootstrap** is a dual-engine Python project:

1. **navi_bootstrap** — Jinja2 rendering engine and template packs for bootstrapping projects to navi-os-grade posture
2. **grippy** — Agno-based AI code review agent with knowledge graph persistence and GitHub PR integration

- **Language:** Python
- **Python version:** >= 3.12
- **Build system:** hatchling
- **Package manager:** uv
- **CLI entry point:** `nboot` (Click-based)

### Repository Layout

```
src/
  navi_bootstrap/   # 10 modules — engine, CLI, spec, manifest, resolve, validate, diff, hooks, init, sanitize
  grippy/           # 10 modules — agent, schema, graph, persistence, review, retry, prompts, embedder, github_review
    prompts_data/   # prompt markdown files — persona, constitution, review modes, tone calibration
packs/              # 7 template packs — base, code-hygiene, github-templates, quality-gates, release-pipeline, review-system, security-scanning
tests/              # test files including adversarial/ suite
.github/workflows/  # CI: tests, Grippy review, CodeQL, scorecard, release
```

## Development Commands

```bash
# Install dependencies
uv sync

# Run all tests
uv run pytest tests/ -v

# Run tests with coverage (both packages)
uv run pytest tests/ -v --cov=src/navi_bootstrap --cov=src/grippy --cov-report=term-missing

# Lint (both packages)
uv run ruff check src/navi_bootstrap/ src/grippy/ tests/

# Format (both packages)
uv run ruff format src/navi_bootstrap/ src/grippy/ tests/

# Type check (both packages)
uv run mypy src/navi_bootstrap/ src/grippy/

# Security scan (navi_bootstrap only — grippy covered by CodeQL)
uv run bandit -r src/navi_bootstrap -ll

# Run all quality checks
uv run ruff format --check src/navi_bootstrap/ src/grippy/ tests/ && \
  uv run ruff check src/navi_bootstrap/ src/grippy/ tests/ && \
  uv run mypy src/navi_bootstrap/ src/grippy/

# Pre-commit (run all hooks)
pre-commit run --all-files
```

## Code Quality Standards

- Line length: 100 characters
- Linter: ruff (select: E, F, I, N, W, UP, B, RUF, C4)
- Type checking: mypy (strict mode)
- Security: bandit (navi_bootstrap), detect-secrets with baseline
- License headers: SPDX `MIT` enforced via pre-commit on `.py` files

## CI Pipeline

- **tests.yml** — pytest, ruff, mypy on every PR
- **grippy-review.yml** — Grippy AI code review on every PR
- **codeql.yml** — GitHub CodeQL security scanning
- **scorecard.yml** — OSSF scorecard
- **Branch protection:** `main` requires PRs + passing Grippy Code Review check

## Commit Conventions

- Use conventional commits: `feat:`, `fix:`, `chore:`, `docs:`, `test:`, `refactor:`
- Keep commits atomic — one logical change per commit
- Run quality checks before committing

## Scope Boundaries

- Do not modify files outside `src/`, `tests/`, `packs/`, and `docs/` without explicit approval
- Do not bump `requires-python` or change dependency version constraints without discussion
- Do not modify `.github/workflows/` without discussion — CI changes affect branch protection
- Document pre-existing violations in DEBT.md rather than fixing them silently
