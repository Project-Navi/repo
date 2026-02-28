# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Project Overview

**navi-bootstrap** is a Jinja2 rendering engine and template packs for bootstrapping projects to navi-os-grade posture.

- **Language:** Python
- **Python version:** >= 3.12
- **Build system:** hatchling
- **Package manager:** uv
- **CLI entry point:** `nboot` (Click-based)

### Repository Layout

```
src/
  navi_bootstrap/   # 10 modules — engine, CLI, spec, manifest, resolve, validate, diff, hooks, init, sanitize
packs/              # 7 template packs — base, code-hygiene, github-templates, quality-gates, release-pipeline, review-system, security-scanning
tests/              # test files including adversarial/ suite
.github/workflows/  # CI: tests, CodeQL, scorecard, release
```

## Development Commands

```bash
# Install dependencies
uv sync

# Run all tests
uv run pytest tests/ -v

# Run tests with coverage
uv run pytest tests/ -v --cov=src/navi_bootstrap --cov-report=term-missing

# Lint
uv run ruff check src/navi_bootstrap/ tests/

# Format
uv run ruff format src/navi_bootstrap/ tests/

# Type check
uv run mypy src/navi_bootstrap/

# Security scan
uv run bandit -r src/navi_bootstrap -ll

# Run all quality checks
uv run ruff format --check src/navi_bootstrap/ tests/ && \
  uv run ruff check src/navi_bootstrap/ tests/ && \
  uv run mypy src/navi_bootstrap/

# Pre-commit (run all hooks)
pre-commit run --all-files
```

## Code Quality Standards

- Line length: 100 characters
- Linter: ruff (select: E, F, I, N, W, UP, B, RUF, C4)
- Type checking: mypy (strict mode)
- Security: bandit, detect-secrets with baseline
- License headers: SPDX `MIT` enforced via pre-commit on `.py` files

## CI Pipeline

- **tests.yml** — pytest, ruff, mypy on every PR
- **codeql.yml** — GitHub CodeQL security scanning
- **scorecard.yml** — OSSF scorecard

## Commit Conventions

- Use conventional commits: `feat:`, `fix:`, `chore:`, `docs:`, `test:`, `refactor:`
- Keep commits atomic — one logical change per commit
- Run quality checks before committing

## Scope Boundaries

- Do not modify files outside `src/`, `tests/`, `packs/`, and `docs/` without explicit approval
- Do not bump `requires-python` or change dependency version constraints without discussion
- Do not modify `.github/workflows/` without discussion — CI changes affect branch protection
