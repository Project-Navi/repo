# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Project Overview

**navi-bootstrap** — Jinja2 rendering engine and template packs for bootstrapping projects to navi-os-grade posture

- **Language:** python
- **Python version:** >= 3.12
- **Source:** `src/navi_bootstrap/`
- **Tests:** `tests/`


## Development Commands

```bash
# Install dependencies
uv sync

# Run tests
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
uv run ruff format --check src/navi_bootstrap/ tests/ && uv run ruff check src/navi_bootstrap/ tests/ && uv run mypy src/navi_bootstrap/

# Pre-commit (run all hooks)
pre-commit run --all-files
```

## Code Quality Standards

- Line length: 100 characters
- Linter: ruff (select: E, F, I, N, W, UP, B, RUF, C4)
- Type checking: mypy (strict mode)
- Security: bandit
- Secret detection: detect-secrets with baseline

## Commit Conventions

- Use conventional commits: `feat:`, `fix:`, `chore:`, `docs:`, `test:`, `refactor:`
- Keep commits atomic — one logical change per commit
- Run quality checks before committing

## Scope Boundaries

- Do not modify files outside `src/navi_bootstrap/` and `tests/` without explicit approval
- Do not bump `requires-python` or change dependency version constraints without discussion
- Document pre-existing violations in DEBT.md rather than fixing them silently
