# repo

A repo called `repo` that bootstraps repos. The CLI is `nboot`. The irony is the feature.

Spec-driven rendering engine and template packs for bootstrapping projects to production-grade posture. CI, security scanning, code review, release pipelines, quality gates — defined once as template packs, applied to any project with a single command.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

```bash
# Apply packs to an existing project
nboot apply --spec project.json --pack ./packs/base --target ./my-project

# Render a new project from scratch
nboot render --spec project.json --pack ./packs/base --out ./my-project

# Validate a spec without rendering
nboot validate --spec project.json --pack ./packs/base
```

## Quick Start

```bash
# Install
uv sync

# Apply the base pack to your project
nboot apply --spec my-spec.json --pack ./packs/base --target /path/to/project

# Dry run first if you want to see what changes
nboot apply --spec my-spec.json --pack ./packs/base --target /path/to/project --dry-run
```

The spec describes your project. The pack describes what to generate. The engine connects them deterministically: same spec + same pack = same output, every time.

## Packs

Seven template packs, layered with explicit dependencies:

```
base (required, runs first)
├── security-scanning
├── github-templates
├── review-system
├── quality-gates
├── code-hygiene
└── release-pipeline
```

All elective packs depend on `base`. The agent sequences them; the engine renders one at a time.

| Pack | Templates | What it ships |
|------|-----------|---------------|
| **base** | 6 | CI workflows (test + lint + security), pre-commit config, dependabot, pyproject tool config, CLAUDE.md, DEBT.md |
| **security-scanning** | 2 | CodeQL analysis, OpenSSF Scorecard |
| **github-templates** | 4 | Bug report form, feature request form, issue config, PR template |
| **review-system** | 2 | Code review workflow instructions, security review instructions |
| **quality-gates** | 2 | Quality metrics baseline (JSON), test parity map |
| **code-hygiene** | 1 | CONTRIBUTING.md with project-specific conventions |
| **release-pipeline** | 3 | SLSA L3 reusable build workflow, release dispatcher, git-cliff changelog config |

Packs never modify source code, never make governance decisions, and never fix pre-existing violations — they document them.

## Grippy

Grippy is navi-bootstrap's AI code reviewer — a prompt-only framework (21 markdown files, zero code) that runs on local hardware via [Agno](https://github.com/agno-agi/agno).

- **Local-first.** Runs on Devstral via LM Studio or Ollama. Your code never leaves your network.
- **Structured output.** Every review produces Pydantic-validated JSON: findings with severity, confidence, evidence, and suggestions. 14 nested models, enum-constrained fields, no freeform text to parse.
- **Validated.** Devstral Q4 (24b) passed structured output validation on first attempt against a real 250-line, 6-file diff with the full 7-file prompt chain.

```python
from grippy.agent import create_reviewer, format_pr_context

reviewer = create_reviewer(
    base_url="http://localhost:1234/v1",
    prompts_dir="/path/to/grippy/prompts",
)

result = reviewer.run(format_pr_context(
    title="feat: add user auth",
    author="dev",
    branch="feature/auth -> main",
    diff=diff_content,
))
```

Cloud models (Claude, GPT) are a config swap — change `base_url` and `model_id`. The architecture doesn't change.

## Architecture

Six-stage pipeline. Stateless and deterministic through stage 3.

```
spec.json + pack/
  -> [Stage 0: Resolve]   action SHAs via gh api
  -> [Stage 1: Validate]  spec + manifest against schemas
  -> [Stage 2: Plan]      evaluate conditions, expand loops, build render list
  -> [Stage 3: Render]    Jinja2 render to memory
  -> [Stage 4: Validate]  run post-render checks
  -> [Stage 5: Hooks]     post-render shell commands
  -> output/
```

Stages 0-3 are pure functions — spec and pack in, rendered files out, no side effects. This is by design: a future TypeScript rewrite runs stages 0-3 on Cloudflare Workers, with an ultra-lightweight local client handling stages 4-5.

The engine is ~600 lines across 7 modules. All project-specific opinions live in the spec and the template pack, never in the engine.

```
src/navi_bootstrap/
├── cli.py        # Click CLI: init, render, apply, validate
├── engine.py     # Plan + Render (stages 2-3)
├── manifest.py   # Manifest loading + validation
├── spec.py       # Spec loading + JSON Schema validation
├── resolve.py    # Stage 0: action SHA resolution
├── validate.py   # Stage 4: post-render validation
└── hooks.py      # Stage 5: hook runner
```

## Development

```bash
uv sync                                          # Install dependencies
uv run pytest tests/ -v                          # Run tests (162 passing)
uv run ruff check src/navi_bootstrap/ tests/     # Lint
uv run ruff format src/navi_bootstrap/ tests/    # Format
uv run mypy src/navi_bootstrap/                  # Type check
uv run bandit -r src/navi_bootstrap -ll          # Security scan
pre-commit run --all-files                       # All hooks
```

Conventional commits: `feat:`, `fix:`, `chore:`, `docs:`, `test:`, `refactor:`.

## Origin

This project was designed and built by two Claude Code instances (alpha and bravo) and a human (Nelson), coordinating through a shared markdown file instead of Slack. The full conversation trail — architectural trade-offs, context deaths, recoveries, disagreements, and handoffs — is preserved at [`.comms/thread.md`](.comms/thread.md). It's not a retrospective. It's the actual build log.

---

*I built this because I'm lazy — which, I'm told, is the adoptive parent of invention.*

## License

[MIT](LICENSE) — Copyright (c) 2026 Project Navi
