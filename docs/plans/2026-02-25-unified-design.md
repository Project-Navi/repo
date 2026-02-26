# nboot Unified Design

Date: 2026-02-25

## Overview

navi-bootstrap (`nboot`) is a Jinja2-powered rendering engine and curated template pack system for bootstrapping projects into navi-os-grade posture across DevOps, security, code quality, and governance.

Two modes of operation:

- **Greenfield**: generate a new project from a spec (`nboot init`, `nboot render`)
- **Apply**: upgrade an existing project via targeted packs (`nboot apply`)

The consumer for apply mode is an AI agent that does mechanical work autonomously and surfaces judgment calls to the human. The output is a goodwill PR to an upstream project.

**Package:** `navi-bootstrap`
**CLI:** `nboot`
**Language:** Python first, TypeScript second, Go/Rust later

### Reference Architecture

navi-os (`/home/ndspence/GitHub/navi-os`) is the gold standard — for DevOps, security posture, audit methodology, superset analysis, debt tracking, code hygiene rules, and best practices.

### Lineage

nboot distills lessons from two predecessor projects:

- **Neural Forge Bootstrapper** (`/home/ndspence/GitHub/Neural-Forge-Bootstrapper`) — a 16,000-line deterministic project generator with governance packs, FCPA 7-phase audit, and PBJRAG analysis. nboot carries forward the spec-driven render pattern, template pack concept, and governance pack upgrade model. It cuts the PBJRAG/DSC analysis, autoheal pipeline, webui, LLM client, canvas validator, and agent analyzer.
- **arctl upgrade playbook** (`docs/arctl-upgrade-playbook.md`) — a narrative record of bootstrapping DevOps infrastructure onto an existing Python project. nboot carries forward the adversarial audit methodology, SHA verification discipline, scope decision framework, and the agent-as-operator workflow. It evolves from narrative to structured manifests and templates.

## Architecture

### Two Layers

```
┌─────────────────────────────────────────────┐
│  Agent Workflow Layer                       │
│  (recon, decisions, validation, PR)         │
│  Reads: decisions, validation, dependencies │
│  Not in engine — the agent IS this layer    │
├─────────────────────────────────────────────┤
│  Engine Layer (~500-600 lines)              │
│  (resolve, validate, plan, render, hooks)   │
│  Reads: conditions, loops, templates, hooks │
│  Deterministic: same spec + pack = same out │
└─────────────────────────────────────────────┘
```

The engine is dumb and stable. All project-specific opinions live in the spec and the template pack. The manifest schema holds fields for both layers — the engine processes its fields and ignores the rest.

### Layered Pack System

```
base (required, runs first)
  ├── security-scanning (independent)
  ├── github-templates (independent)
  ├── release-pipeline (independent)
  ├── review-system (independent)
  ├── audit (independent, but informs the next two)
  │     ├── quality-gates (benefits from audit findings)
  │     └── code-hygiene (benefits from audit findings)
```

Pack dependencies are manifest metadata. The agent sequences the calls. The engine renders one pack at a time.

## Core Concepts

Three primitives:

- **Spec** (`project.json`) — the blueprint. Describes the project: name, structure, modules, dependencies, features, entry points. In greenfield mode, the human writes it (or `init` generates a default). In apply mode, the agent constructs it from repo inspection. Validated against a JSON Schema.
- **Template Pack** — a directory of Jinja2 templates plus a `manifest.yaml` declaring conditions, loops, modes, hooks, and agent-workflow metadata.
- **Engine** — validates the spec, reads the manifest, resolves SHAs, walks the template pack, renders through Jinja2, runs validation and hooks. Deterministic: same spec + same pack = same output, every time.

## Spec Schema

### Greenfield spec

```json
{
  "name": "my-api",
  "version": "0.1.0",
  "description": "A REST API for things",
  "license": "MIT",
  "language": "python",
  "python_version": "3.12",

  "author": {
    "name": "Nelson",
    "email": "nelson@example.com"
  },

  "structure": {
    "src_dir": "src/my_api",
    "test_dir": "tests",
    "docs_dir": "docs"
  },

  "modules": [
    { "name": "api", "description": "REST endpoints" },
    { "name": "models", "description": "Data models" },
    { "name": "core", "description": "Business logic" }
  ],

  "entry_points": {
    "cli": "my_api.cli:main",
    "module": "my_api"
  },

  "dependencies": {
    "runtime": ["click", "fastapi", "uvicorn"],
    "dev": ["pytest", "pylint", "pytest-cov"]
  },

  "features": {
    "ci": true,
    "docker": false,
    "pre_commit": true,
    "docs": true
  }
}
```

### Apply-mode spec (agent-constructed from recon)

```json
{
  "name": "arctl",
  "version": "1.2.0",
  "language": "python",
  "python_version": "3.9",

  "structure": {
    "src_dir": "arctl",
    "test_dir": "tests",
    "docs_dir": "docs"
  },

  "dependencies": {
    "runtime": ["numpy"],
    "optional": {
      "verification": ["sentence-transformers"],
      "viz": ["matplotlib"]
    },
    "dev": []
  },

  "features": {
    "ci": true,
    "pre_commit": false,
    "docker": false
  },

  "recon": {
    "test_framework": "unittest",
    "test_count": 42,
    "python_test_versions": ["3.9", "3.10", "3.11", "3.12"],
    "existing_ci": ["tests.yml"],
    "existing_tools": {
      "ruff": false,
      "mypy": false,
      "bandit": false,
      "pre_commit": false,
      "dependabot": false
    },
    "has_pyproject_toml": true,
    "has_github_dir": true
  }
}
```

Key decisions:

- Same schema for both modes. The `recon` section is optional — present in apply mode, absent in greenfield.
- `modules` is a list, not a tree. Flat and predictable.
- `features` is a flat boolean map. The manifest uses these to decide what to render.
- `structure` makes directory names explicit — no magic naming conventions.
- The schema is extensible — template packs can expect additional fields and the JSON Schema validates accordingly.
- In apply mode, the agent inspects the target repo to populate the spec. The manifest's `inputs.required` tells the agent what to extract. The agent fills in the recon, merges with human overrides, and that's the spec.

## Template Pack & Manifest

A template pack is a directory:

```
packs/base/
├── manifest.yaml
└── templates/
    ├── pre-commit-config.yaml.j2
    ├── secrets-baseline.json.j2
    ├── pyproject-tools.toml.j2
    ├── dependabot.yml.j2
    ├── CLAUDE.md.j2
    ├── DEBT.md.j2
    └── workflows/
        └── tests.yml.j2
```

### Manifest schema

```yaml
name: base
description: >
  Bootstrap target repo into a compatible state for elective packs.

version: "0.1.0"

# --- Engine fields (processed by the engine) ---

# Conditional file rendering (dotpath expressions against the spec)
conditions:
  "workflows/tests.yml.j2": "spec.features.ci"

# Per-item file expansion from spec lists
loops: {}

# Templates to render, in order
templates:
  - src: pre-commit-config.yaml.j2
    dest: .pre-commit-config.yaml
  - src: secrets-baseline.json.j2
    dest: .secrets.baseline
  - src: pyproject-tools.toml.j2
    dest: pyproject.toml
    mode: append
  - src: dependabot.yml.j2
    dest: .github/dependabot.yml
  - src: workflows/tests.yml.j2
    dest: .github/workflows/tests.yml
  - src: CLAUDE.md.j2
    dest: CLAUDE.md
  - src: DEBT.md.j2
    dest: DEBT.md

strip_suffix: ".j2"

hooks:
  - "uv lock"
  - "detect-secrets scan > .secrets.baseline"

# --- Agent-workflow fields (read by the agent, ignored by engine) ---

# Packs that must run before this one
dependencies: []

# What the agent needs to gather before rendering
inputs:
  required:
    - name: project_name
      description: Python package name (the directory ruff/bandit/mypy scan)
      example: "arctl"
    - name: python_min_version
      description: From requires-python in pyproject.toml
      example: "3.9"
    - name: target_repo_path
      description: Absolute path to local clone of target repo
  optional:
    - name: optional_deps
      description: List of optional dependencies needing mypy overrides
      example: ["numpy", "torch", "sentence_transformers"]
    - name: fork_account
      description: GitHub username/org for fork-based PRs

# Action SHAs resolved at render time via gh api (Stage 0)
action_shas:
  - name: actions_checkout
    repo: actions/checkout
    tag: v4.2.2
  - name: harden_runner
    repo: step-security/harden-runner
    tag: v2.10.4
  - name: actions_setup_python
    repo: actions/setup-python
    tag: v5.4.0

# Post-render validation checks (Stage 4)
validation:
  - description: Pre-commit installs and runs clean
    command: pre-commit run --all-files
    expect: exit_code_0_or_warnings
  - description: uv.lock generates without errors
    command: uv lock
    expect: exit_code_0
  - description: Test suite still passes
    command: python -m pytest tests/ -v
    expect: exit_code_0
  - description: All action SHAs resolve
    method: sha_verification

# Judgment calls the agent must surface to the human
decisions:
  - question: "Which navi-os patterns apply to this project's domain?"
    context: "Not all security/quality patterns fit every project size and type."
  - question: "Are there pre-existing lint violations to document?"
    context: "Run ruff/mypy before committing. Document findings, don't fix them."
  - question: "Should dev tool python_version markers be used?"
    context: "If project supports older Python than dev tools require."
```

### Key manifest design decisions

- **Engine fields vs agent fields**: clean separation. The engine processes `conditions`, `loops`, `templates`, `hooks`, `strip_suffix`, `mode`. The agent reads `decisions`, `validation`, `dependencies`, `action_shas`, `inputs`. The manifest holds both; the engine ignores what isn't its concern.
- **`mode: append`**: the engine appends rendered content with marker comments (`# --- nboot: pack-name ---` / `# --- end nboot: pack-name ---`). If markers already exist, replace that block. No TOML/YAML-aware merging. Predictable behavior: manual edits inside markers are overwritten on re-apply.
- **`action_shas`**: a pre-render resolution step (Stage 0). The engine calls `gh api` for each entry and injects the resolved SHAs into the template context. Never hardcoded, never trusted from memory.
- **`validation`**: post-render checks (extended Stage 4). Like hooks, but with pass/fail expectations. The engine runs the commands and reports results.
- **`decisions`**: manifest metadata the engine passes through untouched. The agent reads the list and handles human interaction.
- **No checklist files**: the manifest is the single source of truth. The agent derives its execution plan from the structured manifest data. A freeform markdown checklist would risk drifting from the manifest.

## Engine Architecture

Six stages, run sequentially:

```
spec.json + pack/
  → [Stage 0: Resolve]   — action_shas via gh api → inject into context
  → [Stage 1: Validate]  — spec against JSON Schema, manifest against schema
  → [Stage 2: Plan]      — walk templates, evaluate conditions/loops, build render list
  → [Stage 3: Render]    — Jinja2 render, write/append to output
  → [Stage 4: Validate]  — run validation commands, report pass/fail
  → [Stage 5: Hooks]     — post-render shell commands
  → output/ (new or existing)
```

### Stage 0: Resolve

- For each entry in `action_shas`: call `gh api repos/{repo}/git/refs/tags/{tag}` to get the commit SHA
- Handle both lightweight and annotated tags (dereference tag objects)
- Inject resolved SHAs into template context as `action_shas.<name>` and version strings as `action_versions.<name>`
- Fail fast if any SHA cannot be resolved

### Stage 1: Validate

- Load spec JSON, validate against JSON Schema
- Load `manifest.yaml`, validate its structure against the manifest schema
- Fail fast with clear errors if either is invalid

### Stage 2: Plan

- Walk the template pack directory
- For each `.j2` file: check conditions from manifest, skip if falsy
- For looped files: expand the file list (one entry per item in the loop source)
- For all other `.j2` files: include once
- Result: an ordered list of `(template_path, output_path, context)` tuples
- Non-`.j2` files are copied as-is (static assets, images, etc.)

### Stage 3: Render

- Set up Jinja2 environment with the template pack as the loader root
- For each entry in the plan: render template with spec + resolved SHAs + loop variables as context
- Strip `.j2` suffix, resolve template expressions in directory/file names
- Create directories as needed
- **Greenfield mode** (`render`): fail if output directory already exists
- **Apply mode** (`apply`): operate on existing directory. For `mode: append` files, use marker-block insertion/replacement. For other files, create new or fail if file already exists (no silent overwrites of non-marker files)

### Stage 4: Validate

- Run each validation command from the manifest
- Report pass/fail with command output
- Do not roll back on failure — report and let the agent/human decide

### Stage 5: Hooks

- Run each hook command sequentially in the output directory via subprocess
- Capture stdout/stderr, report failures but don't roll back

## Module Layout

```
src/navi_bootstrap/
├── cli.py              # Click CLI: init, render, apply, validate
├── engine.py           # Plan + Render stages
├── manifest.py         # Manifest loading + validation
├── spec.py             # Spec loading + JSON Schema validation
├── resolve.py          # Stage 0: action SHA resolution via gh api
├── validate.py         # Stage 4: post-render validation runner
└── hooks.py            # Stage 5: post-render hook runner
```

Estimated ~500-600 lines total.

## CLI Interface

```bash
# Quick start — generates a default spec, renders with built-in pack
nboot init --name my-api --language python

# Full spec-driven greenfield — you control everything
nboot render --spec project.json --pack ./packs/python-base --out ./my-api

# Apply pack to existing repo
nboot apply --spec project.json --pack ./packs/base --target ./existing-repo

# Validation only
nboot validate --spec project.json --pack ./packs/base

# Dry run (any mode)
nboot render --spec project.json --pack ./packs/python-base --out ./my-api --dry-run
nboot apply --spec project.json --pack ./packs/base --target ./existing-repo --dry-run
```

### `nboot init`
- `--name` (required) — project name
- `--language` (default: `python`) — picks the built-in pack
- `--out` (optional) — output directory, defaults to `--name`
- Generates a default spec, renders with matching built-in pack

### `nboot render`
- `--spec` (required) — path to spec JSON
- `--pack` (required) — path to template pack directory
- `--out` (optional) — output directory, defaults to `spec.name`
- `--dry-run` (flag) — print the render plan without writing files
- Fails if output directory already exists

### `nboot apply`
- `--spec` (required) — path to spec JSON (agent-constructed or hand-authored)
- `--pack` (required) — path to template pack directory
- `--target` (required) — path to existing project directory
- `--dry-run` (flag) — print the render plan without writing files
- Operates on existing directory. Uses `mode: append` with marker blocks.

### `nboot validate`
- `--spec` (required) — validates spec against JSON Schema
- `--pack` (optional) — also validates manifest if provided

## Template Conventions

### Variable naming

- `{{ spec.name }}` — project name
- `{{ spec.python_version }}` — e.g. `3.9`
- `{{ spec.recon.python_test_versions }}` — e.g. `["3.9", "3.10", "3.11", "3.12"]`
- `{{ spec.dependencies.optional }}` — optional dependency groups
- `{{ action_shas.<action_name> }}` — resolved at render time, never hardcoded
- `{{ action_versions.<action_name> }}` — human-readable version comment

### SHA handling in templates

```yaml
- uses: actions/checkout@{{ action_shas.actions_checkout }}  # {{ action_versions.actions_checkout }}
- uses: step-security/harden-runner@{{ action_shas.harden_runner }}  # {{ action_versions.harden_runner }}
```

### Append mode markers

For templates with `mode: append`, marker comments identify what was added and by which pack:

```toml
# --- nboot: base ---
[dependency-groups]
dev = [
    "ruff>={{ tool_versions.ruff }}",
]

[tool.ruff]
line-length = 100
target-version = "py{{ spec.python_version | replace('.', '') }}"
# --- end nboot: base ---
```

### Template directory names

Directory names in the pack can be template expressions:

```
packs/python-base/
├── {{spec.structure.src_dir}}/
│   ├── __init__.py.j2
│   └── {{module.name}}.py.j2
```

Resolved during Stage 3 (Render) using the spec context.

## Agent Workflow (Apply Mode)

The agent workflow is NOT in the engine. The agent IS this layer.

```
1. Agent reads manifest
   → checks dependencies (runs base first if needed)
   → reads inputs.required
2. Agent inspects target repo (structured recon)
   → reads pyproject.toml, scans .github/, inventories tests
   → builds spec from recon + human overrides
3. Agent surfaces decisions to human
   → reads decisions list from manifest
   → presents each question with context
   → records human responses
4. Agent calls nboot apply
   → engine resolves SHAs, validates, plans, renders, validates results, runs hooks
5. Agent reviews validation results
   → surfaces failures to human with proposed resolution
6. Agent finalizes
   → squash commit, fork, push, open PR
```

### Structured recon schema

The agent's repo inspection is structured, not freeform. The manifest's `inputs.required` tells the agent what to extract:

```yaml
recon:
  package_name: "arctl"              # from pyproject.toml [project].name
  python_min_version: "3.9"          # from requires-python
  test_framework: "pytest"           # detected from conftest.py or pyproject.toml
  test_dir: "tests"                  # detected from pytest config or convention
  test_count: 42                     # from running the test suite
  existing_ci: ["tests.yml"]         # what's already in .github/workflows/
  existing_tools:
    ruff: false
    mypy: false
    bandit: false
    pre_commit: false
    dependabot: false
  dependencies: ["numpy"]            # from pyproject.toml
  optional_dependencies:             # from pyproject.toml
    verification: ["sentence-transformers"]
    viz: ["matplotlib"]
```

The recon output populates the spec's `recon` section. The engine uses it as template context.

## Repo Structure

```
navi-bootstrap/
├── src/
│   └── navi_bootstrap/
│       ├── cli.py
│       ├── engine.py
│       ├── manifest.py
│       ├── spec.py
│       ├── resolve.py
│       ├── validate.py
│       └── hooks.py
├── packs/
│   ├── base/
│   │   ├── manifest.yaml
│   │   └── templates/
│   ├── security-scanning/
│   ├── quality-gates/
│   ├── code-hygiene/
│   ├── github-templates/
│   ├── review-system/
│   ├── release-pipeline/
│   └── audit/
├── schema/
│   ├── spec-schema.json            # JSON Schema for project.json
│   └── manifest-schema.yaml        # validates all manifest.yaml files
├── tests/
├── docs/
│   ├── arctl-upgrade-playbook.md   # historical reference (origin story)
│   └── plans/
├── pyproject.toml
├── CLAUDE.md                       # agent guidance for nboot itself
└── README.md
```

## Pack Inventory

| Pack | Dependencies | Adds to repo | Key decisions surfaced |
|------|-------------|-------------|----------------------|
| **base** | none | pre-commit, CI (test+lint+security jobs), pyproject.toml tool config, dependabot, CLAUDE.md, DEBT.md, uv.lock, .secrets.baseline | Scope, pre-existing violations, version markers |
| **security-scanning** | base | CodeQL workflow, Scorecard workflow, Semgrep workflow, bandit config hardening | Which scanners fit the project size, Scorecard publish_results |
| **quality-gates** | base | quality-gate.json, CI gate-bump job, test parity map | Initial thresholds, which metrics to ratchet, parity baseline |
| **code-hygiene** | base | Code hygiene rules in CLAUDE.md/CONTRIBUTING.md | Which rules apply, project-specific adaptations |
| **github-templates** | base | Issue forms (bug, feature), PR template, config.yml | Category dropdowns (project-specific), blank issue policy |
| **review-system** | base | .github/instructions/, review guidelines in CLAUDE.md | Dual-reviewer split, review focus areas |
| **release-pipeline** | base | Release workflow, SBOM generation, Sigstore signing | SLSA level, SBOM format, release trigger |
| **audit** | base | Superset analysis findings doc, prioritized remediation list | Finding severity thresholds, scope of audit |

## Scope Boundaries

What packs never do:
- Never modify source code (application logic, tests)
- Never make governance decisions (SECURITY.md, CODE_OF_CONDUCT, CODEOWNERS, FUNDING)
- Never fix pre-existing lint/type violations (document only)
- Never bump requires-python or change the project's dependency constraints

## What Gets Cut (from Neural Forge)

Everything from the original 16,000-line codebase except the core idea:

- FCPA audit system (7-phase analysis, lifecycle decisions) — lessons inform the audit pack, code does not carry forward
- PBJRAG / DSC 9-dimensional analysis
- Canvas validator
- Agent analyzer / agent generator
- Auto-documenter
- Autoheal pipeline
- Web UI
- LLM client / Ollama integration
- Governance pack versioning and upgrade paths (v1.0-v1.6)
- State tracking (`.nf_toolkit.json`)

Lessons carried forward (not code):

- Spec-driven generation → refined into spec + manifest + engine
- Template pack concept → simplified, self-contained
- Governance pack upgrades → evolved into layered pack system with dependencies
- Resource probing + manifest verification → engine validates pack completeness
- `write_file` with overwrite flag → evolved into `mode: append` with marker blocks
- FCPA structured data models → inform the recon schema and audit pack output format
- SHA verification discipline → Stage 0 resolves all SHAs via `gh api`

## Build Order

1. **Engine first** (~500-600 lines) — the contract that packs depend on. Add `mode: append` from day one.
2. **Base pack second** — the first real product. CI, pre-commit, CLAUDE.md, DEBT.md, dependabot, uv.lock.
3. **Elective packs third** — each one is independent work.
