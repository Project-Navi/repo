# navi-bootstrap

[![Tests](https://github.com/Project-Navi/repo/actions/workflows/tests.yml/badge.svg)](https://github.com/Project-Navi/repo/actions/workflows/tests.yml)
[![Grippy Review](https://github.com/Project-Navi/repo/actions/workflows/grippy-review.yml/badge.svg)](https://github.com/Project-Navi/repo/actions/workflows/grippy-review.yml)
[![CodeQL](https://github.com/Project-Navi/repo/actions/workflows/codeql.yml/badge.svg)](https://github.com/Project-Navi/repo/actions/workflows/codeql.yml)
[![OpenSSF Scorecard](https://github.com/Project-Navi/repo/actions/workflows/scorecard.yml/badge.svg)](https://github.com/Project-Navi/repo/actions/workflows/scorecard.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)

Two engines in one repo. **nboot** bootstraps projects to production-grade posture with spec-driven template packs. **Grippy** reviews your code with a knowledge graph that remembers what it already told you.

---

## nboot — Bootstrap Engine

Spec-driven rendering engine and template packs. CI, security scanning, code review, release pipelines, quality gates — defined once as template packs, applied to any project with a single command.

```bash
# Generate a spec by inspecting your project
nboot init --target ./my-project

# Preview what a pack would change
nboot diff --spec nboot-spec.json --pack ./packs/base --target ./my-project

# Apply packs to an existing project
nboot apply --spec nboot-spec.json --pack ./packs/base --target ./my-project

# Render a new project from scratch
nboot render --spec nboot-spec.json --pack ./packs/base --out ./my-project
```

The spec describes your project. The pack describes what to generate. The engine connects them deterministically: same spec + same pack = same output, every time.

### Packs

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

### Architecture

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

The engine is ~800 lines across 10 modules. All project-specific opinions live in the spec and the template pack, never in the engine.

```
src/navi_bootstrap/
├── cli.py        # Click CLI: init, render, apply, diff, validate
├── engine.py     # Plan + Render (stages 2-3), sandboxed dest paths
├── manifest.py   # Manifest loading + validation
├── spec.py       # Spec loading + JSON Schema validation
├── resolve.py    # Stage 0: action SHA resolution
├── validate.py   # Stage 4: post-render validation
├── hooks.py      # Stage 5: hook runner
├── sanitize.py   # Input sanitization (homoglyphs, traversal, injection)
├── init.py       # Project inspection → spec generation
└── diff.py       # Drift detection (render-to-memory + unified diff)
```

---

## Grippy — AI Code Reviewer

Grippy is an Agno-based AI code review agent with structured output, knowledge graph persistence, and GitHub PR integration. It runs on every push to a PR, posts findings as inline review comments, tracks finding lifecycle across rounds, and auto-resolves threads when issues are fixed.

- **Structured output.** Every review produces Pydantic-validated JSON: findings with severity, confidence, evidence, and suggestions. 14 nested models, enum-constrained fields, no freeform text to parse.
- **Knowledge graph.** Findings, files, categories, and reviews stored as typed nodes with directed edges in SQLite + LanceDB. Finding fingerprints enable cross-round resolution tracking.
- **Dual deployment.** OpenAI (GPT-5.2) for CI on GitHub-hosted runners, or local models (Devstral, Qwen, etc.) via LM Studio/Ollama for air-gapped environments.
- **PR integration.** Inline review comments on diff lines, summary dashboard with score and delta, fork PR fallback to issue comments, thread auto-resolution via GraphQL.

```
src/grippy/
├── agent.py        # create_reviewer() — Agno agent with transport selection
├── schema.py       # GrippyReview — 14 nested Pydantic models
├── graph.py        # Node, Edge, ReviewGraph — typed knowledge graph
├── persistence.py  # GrippyStore — SQLite edges + LanceDB vectors
├── review.py       # CI entry point — orchestrates review, posting, storage
├── retry.py        # run_review() — validation retry with ReviewParseError
├── prompts.py      # Prompt assembly from prompts_data/ markdown files
└── prompts_data/   # 22 files — persona, constitution, review modes, tone
```

### Usage

```python
from grippy.agent import create_reviewer, format_pr_context

# OpenAI (reads OPENAI_API_KEY from environment)
reviewer = create_reviewer(model_id="gpt-5.2")

# Local LLM (LM Studio, Ollama, or any OpenAI-compatible endpoint)
reviewer = create_reviewer(
    model_id="devstral-small-2-24b-instruct-2512",
    base_url="http://localhost:1234/v1",
    api_key="lm-studio",
)

result = reviewer.run(format_pr_context(
    title="feat: add user auth",
    author="dev",
    branch="feature/auth -> main",
    diff=diff_content,
))
```

### CI Configuration

| Variable | Description | Default |
|---|---|---|
| `GRIPPY_TRANSPORT` | `"openai"` or `"local"` — explicit model routing | Inferred from `OPENAI_API_KEY` |
| `OPENAI_API_KEY` | OpenAI API key (required for `transport=openai`) | — |
| `GRIPPY_BASE_URL` | OpenAI-compatible API endpoint | `http://localhost:1234/v1` |
| `GRIPPY_MODEL_ID` | Model identifier | `devstral-small-2-24b-instruct-2512` |
| `GRIPPY_EMBEDDING_MODEL` | Embedding model for knowledge graph | `text-embedding-qwen3-embedding-4b` |
| `GRIPPY_DATA_DIR` | Persistent directory for graph DB + LanceDB | `./grippy-data` |
| `GRIPPY_TIMEOUT` | Review timeout in seconds (0 = no timeout) | `300` |

| Deployment | Key Variables |
|---|---|
| **OpenAI** (GitHub-hosted) | `GRIPPY_TRANSPORT=openai`, `OPENAI_API_KEY`, `GRIPPY_MODEL_ID=gpt-5.2` |
| **Local** (self-hosted runner) | `GRIPPY_BASE_URL=http://<host>:1234/v1`, `GRIPPY_MODEL_ID=<model>`, `GRIPPY_EMBEDDING_MODEL=<embed-model>` |

The architecture is identical in both modes — only the model transport changes. Defaults are local-first; CI sets OpenAI values explicitly.

---

## Development

```bash
uv sync                                                             # Install dependencies
uv run pytest tests/ -v                                             # Run all tests (~490)
uv run ruff check src/navi_bootstrap/ src/grippy/ tests/            # Lint
uv run ruff format src/navi_bootstrap/ src/grippy/ tests/           # Format
uv run mypy src/navi_bootstrap/ src/grippy/                         # Type check
uv run bandit -r src/navi_bootstrap -ll                             # Security scan
pre-commit run --all-files                                          # All hooks
```

Conventional commits: `feat:`, `fix:`, `chore:`, `docs:`, `test:`, `refactor:`.

## Origin

This project was designed and built by two Claude Code instances and a human, coordinating through shared markdown files instead of Slack.

---

*I built this because I'm lazy — which, I'm told, is the adoptive parent of invention.*

## License

[MIT](LICENSE) — Copyright (c) 2026 Project Navi
