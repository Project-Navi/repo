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
    prompts_data/   # 22 markdown files — persona, constitution, review modes, tone calibration
packs/              # 7 template packs — base, code-hygiene, github-templates, quality-gates, release-pipeline, review-system, security-scanning
tests/              # 32+ test files including adversarial/ suite
docs/               # Boot prompts, design docs, implementation plans
.comms/             # Multi-agent communication thread (append-only)
.github/workflows/  # CI: tests, Grippy review, CodeQL, scorecard, release
```

## Grippy Architecture

Grippy is an AI code review agent built on the Agno framework. Key components:

- **`agent.py`** — `create_reviewer()` with transport selection (`openai` or `local`), Agno agent orchestration
- **`schema.py`** — `GrippyReview` (14 nested Pydantic models): findings, score, verdict, personality
- **`graph.py`** — Knowledge graph: `Node`, `Edge`, `ReviewGraph`, `review_to_graph()` with typed edge/node enums
- **`persistence.py`** — `GrippyStore`: SQLite for edges/metadata + LanceDB for vector embeddings
- **`review.py`** — CI entry point: `main()` orchestrates review, comment posting, graph storage
- **`retry.py`** — `run_review()` with validation retry and `ReviewParseError`
- **`prompts.py`** — System/user prompt assembly from `prompts_data/` markdown files

**Transport modes:** `openai` (GitHub-hosted CI, uses `OPENAI_API_KEY`) or `local` (LM Studio over Tailscale). Resolved via `GRIPPY_TRANSPORT` env var or inferred from available API keys.

**Storage:** Raw `lancedb.connect()` for vectors (we own the schema), `sqlite3` for graph edges and node metadata. Agno `Knowledge` class deliberately not used (document-oriented RAG, doesn't fit structured node storage).

**Config:** `.grippy.yaml` at repo root — review modes, score thresholds, personality triggers.

## Development Commands

```bash
# Install dependencies
uv sync

# Run all tests (~490)
uv run pytest tests/ -v

# Run tests with coverage (both packages)
uv run pytest tests/ -v --cov=src/navi_bootstrap --cov=src/grippy --cov-report=term-missing

# Lint (both packages)
uv run ruff check src/navi_bootstrap/ src/grippy/ tests/

# Format (both packages)
uv run ruff format src/navi_bootstrap/ src/grippy/ tests/

# Type check (both packages)
uv run mypy src/navi_bootstrap/ src/grippy/

# Security scan (navi_bootstrap only — grippy covered by CodeQL; bandit FPs on parameterized SQL)
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
- **grippy-review.yml** — Grippy AI code review on every PR (OpenAI on GitHub-hosted runners)
- **codeql.yml** — GitHub CodeQL security scanning
- **scorecard.yml** — OSSF scorecard
- **Branch protection:** `main` requires PRs + passing Grippy Code Review check

## Collaboration Model

This repo uses a multi-agent development model:

- **Alpha** — engine architect, meta-scribe, owns action packaging + deployment
- **Bravo** — implementation lead, owns Grippy agent evolution
- **Nelson** — human, project owner

### Communication

- **Thread:** `.comms/thread.md` — append only, never edit prior messages. Convention: `[date] **sender**: message` between `---` delimiters. Archived sessions in `thread-archive-*.md`.
- **Boot prompts:** `docs/alpha-boot-prompt.md`, `docs/bravo-boot-prompt.md` — read on reboot to restore context.
- **Design docs:** `docs/plans/` — the knowledge transfer mechanism, not conversation history.
- **Dispatches must name exactly one owner** — learned from early duplicate work.

## Commit Conventions

- Use conventional commits: `feat:`, `fix:`, `chore:`, `docs:`, `test:`, `refactor:`
- Keep commits atomic — one logical change per commit
- Run quality checks before committing

## Scope Boundaries

- Do not modify files outside `src/`, `tests/`, `packs/`, and `docs/` without explicit approval
- Do not bump `requires-python` or change dependency version constraints without discussion
- Do not modify `.github/workflows/` without discussion — CI changes affect branch protection
- Document pre-existing violations in DEBT.md rather than fixing them silently
