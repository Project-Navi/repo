# nboot Template Pack Design

Date: 2026-02-25

## Overview

navi-bootstrap (`nboot`) is a curated playbook and template pack for bootstrapping Python projects into navi-os-grade DevOps, security, and code quality posture. The consumer is an AI agent that reads the playbook as its runbook, does mechanical work autonomously, and surfaces scope decisions, governance calls, and judgment calls to the human. The output is a goodwill PR to an upstream project.

navi-os (`/home/ndspence/GitHub/navi-os`) is the gold standard reference architecture — not just for DevOps and security posture, but for audit methodology, superset analysis, debt tracking, and hooks/best practices.

## Architecture

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

- **Base pack**: bootstraps the target repo into a compatible state for elective packs to run.
- **Elective packs**: each addresses a specific dimension. User picks which to apply.
- **Audit pack**: generates project-specific findings. Not required before quality-gates/code-hygiene, but makes them better.

### Language Support

Python first. TypeScript second. Go/Rust further down the line. Templates are language-specific; the pack structure and manifest schema are language-agnostic.

## Repo Structure

```
navi-bootstrap/
├── docs/
│   ├── arctl-upgrade-playbook.md     # historical reference (origin story)
│   └── plans/                        # design docs
├── packs/
│   ├── base/
│   │   ├── manifest.yml
│   │   ├── checklist.md
│   │   └── templates/
│   ├── security-scanning/
│   │   ├── manifest.yml
│   │   ├── checklist.md
│   │   └── templates/
│   ├── quality-gates/
│   ├── code-hygiene/
│   ├── github-templates/
│   ├── review-system/
│   ├── release-pipeline/
│   └── audit/
├── schema/
│   └── manifest-schema.yml           # validates all manifest.yml files
├── CLAUDE.md                         # agent guidance for nboot itself
└── README.md
```

- Package name: `navi-bootstrap`, CLI entry point: `nboot`
- Existing playbook stays as historical reference, not deleted
- Each pack is self-contained under `packs/`
- A shared schema validates manifest structure
- No Python automation code yet — template pack phase first, CLI automation later

## Manifest Schema

Each pack's `manifest.yml` declares:

```yaml
name: base
description: >
  Bootstrap target repo into a compatible state for elective packs.

version: "0.1.0"

# What the agent needs to know before running this pack
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

# Packs that must run before this one
dependencies: []

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

# Action SHAs to resolve at render time via gh api
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

# How the agent verifies this pack worked
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

# What the agent must surface to the human for judgment
decisions:
  - question: "Which navi-os patterns apply to this project's domain?"
    context: "Not all security/quality patterns fit every project size and type."
  - question: "Are there pre-existing lint violations to document?"
    context: "Run ruff/mypy before committing. Document findings, don't fix them."
  - question: "Should dev tool python_version markers be used?"
    context: "If project supports older Python than dev tools require."
```

### Key manifest fields

- **`templates` with `mode`**: most files are created fresh. `mode: append` for files like `pyproject.toml` where only tool config sections are added.
- **`action_shas`**: declares which GitHub Action SHAs need resolving via `gh api` before rendering. SHAs are never trusted from memory or hardcoded.
- **`validation`**: concrete pass/fail checks so the agent knows if the pack landed correctly.
- **`decisions`**: explicit list of judgment calls the agent must surface to the human, not silently resolve.
- **`inputs`**: the agent gathers these from the target repo (or asks the human) before rendering.

## Checklist Format

Each pack's `checklist.md` is the agent-facing runbook — step-by-step instructions with explicit surfacing markers.

```markdown
# Base Pack — Agent Checklist

## Prerequisites
- [ ] Target repo path confirmed and accessible
- [ ] Target repo has passing test suite (run before any changes)
- [ ] All manifest inputs resolved (from repo inspection or human)

## Phase 1: Reconnaissance
- [ ] Read target pyproject.toml — extract requires-python, dependencies, optional-deps
- [ ] Read target test structure — framework (unittest/pytest), location, count
- [ ] Read existing CI if any — document what exists before replacing
- [ ] Read existing .github/ — note any templates, workflows, configs
- [ ] SURFACE TO HUMAN: Summary of what exists and what will be added/replaced

## Phase 2: Render Templates
- [ ] Resolve all action SHAs via gh api — never use cached/remembered SHAs
- [ ] Render each template from manifest in order
- [ ] For mode: append templates, verify no duplicate sections in target file
- [ ] Generate uv.lock via uv lock
- [ ] Generate .secrets.baseline via detect-secrets scan

## Phase 3: Validate
- [ ] Run each validation check from manifest
- [ ] SURFACE TO HUMAN: Any pre-existing lint/type violations (document, don't fix)
- [ ] SURFACE TO HUMAN: Any validation failures with proposed resolution

## Phase 4: Finalize
- [ ] Squash to single commit with conventional commit message
- [ ] SURFACE TO HUMAN: Commit message for approval
- [ ] Fork, push, open PR (if fork_account provided)

## Decision Points
These MUST be presented to the human — never auto-resolve:
- [ ] Scope: which elective packs to include?
- [ ] Pre-existing violations: document or fix?
- [ ] Dev tool version markers: use markers or bump requires-python?
- [ ] PR description: maintainer-facing notes about what was added
```

Key principles:
- **SURFACE TO HUMAN** markers are explicit — the agent cannot skip them.
- Phases mirror the original playbook's structure (Recon, Implement, Validate, Finish).
- Each checkbox is a concrete action, not a vague instruction.
- Decision points collected at bottom as summary and also inline where they arise.

## Template Conventions

### Variable naming

- `{{ project_name }}` — the package directory name
- `{{ python_min_version }}` — e.g. `3.9`
- `{{ python_test_versions }}` — e.g. `["3.9", "3.10", "3.11", "3.12"]`
- `{{ optional_deps }}` — list of modules needing mypy overrides
- `{{ action_shas.<action_name> }}` — resolved at render time, never hardcoded
- `{{ action_versions.<action_name> }}` — human-readable version comment

### SHA handling in templates

```yaml
- uses: actions/checkout@{{ action_shas.actions_checkout }}  # {{ action_versions.actions_checkout }}
```

### Append mode markers

For templates with `mode: append`, marker comments identify what was added:

```toml
# --- nboot: base ---
[dependency-groups]
dev = [
    "ruff>={{ tool_versions.ruff }}",
]

[tool.ruff]
line-length = 100
target-version = "py{{ python_min_version | replace('.', '') }}"
# --- end nboot: base ---
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
