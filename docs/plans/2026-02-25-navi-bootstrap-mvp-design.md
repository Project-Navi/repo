# navi-bootstrap MVP Design

## Overview

`navi-bootstrap` is a Jinja2-powered rendering engine that takes a detailed project spec and a template pack, and deterministically produces a project. It is the 10% MVP distilled from the Neural Forge Bootstrapper codebase.

**Package:** `navi-bootstrap`
**CLI:** `nboot`
**Language:** Python (POC phase), TypeScript (phase 2), Go/Rust (phase 3)

## Core Concepts

Three primitives:

- **Spec** (`project.json`) — The blueprint. Describes everything about the project: name, structure, modules, dependencies, features, entry points. Validated against a JSON Schema.
- **Template Pack** — A directory of Jinja2 templates mirroring the output structure, plus a `manifest.yaml` declaring conditional files, renaming rules, and post-render hooks.
- **Engine** — Validates the spec, reads the manifest, walks the template pack, renders through Jinja2, applies post-render hooks. Deterministic: same spec + same pack = same output, every time.

The engine is generic and stable. All project-specific opinions live in the spec and the template pack. You never touch the engine to support a new kind of project — you write a new pack.

## Spec Schema

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

Key decisions:

- `modules` is a list, not a tree — flat and predictable. Nesting is a template pack concern.
- `features` is a flat boolean map — the manifest uses these to decide what to render.
- `structure` makes directory names explicit rather than inferred — no magic naming conventions.
- The schema is extensible — template packs can expect additional fields and the JSON Schema validates accordingly.

## Template Pack & Manifest

A template pack is a directory:

```
packs/python-base/
├── manifest.yaml
├── {{spec.structure.src_dir}}/
│   ├── __init__.py.j2
│   └── {{module.name}}.py.j2
├── {{spec.structure.test_dir}}/
│   └── test_{{module.name}}.py.j2
├── pyproject.toml.j2
├── README.md.j2
├── .github/
│   └── workflows/
│       └── ci.yml.j2
├── Dockerfile.j2
└── .pre-commit-config.yaml.j2
```

The `manifest.yaml`:

```yaml
name: python-base
description: Python project with modern packaging
version: "1.0"

conditions:
  ".github/workflows/ci.yml.j2": "spec.features.ci"
  "Dockerfile.j2": "spec.features.docker"
  ".pre-commit-config.yaml.j2": "spec.features.pre_commit"

loops:
  "{{spec.structure.src_dir}}/{{module.name}}.py.j2":
    over: "spec.modules"
    as: "module"
  "{{spec.structure.test_dir}}/test_{{module.name}}.py.j2":
    over: "spec.modules"
    as: "module"

strip_suffix: ".j2"

hooks:
  - "git init"
  - "git add ."
```

Key decisions:

- **Conditions** are dotpath expressions evaluated against the spec — no custom DSL, just truthiness checks on spec values.
- **Loops** declare which files are rendered per-item from a spec list. The loop variable becomes available in both the path and the template content.
- **Hooks** are plain shell commands, ordered, run sequentially in the output directory. Optional.
- **Directory names can be templates** — `{{spec.structure.src_dir}}` in the path gets resolved during rendering.
- No inheritance, no layering, no pack-to-pack dependencies. One pack, self-contained.

## Engine Architecture

Four stages, run sequentially:

```
spec.json + pack/ → [Validate] → [Plan] → [Render] → [Hooks] → output/
```

**Stage 1: Validate**
- Load spec JSON, validate against schema
- Load `manifest.yaml`, validate its structure
- Fail fast with clear errors if either is invalid

**Stage 2: Plan**
- Walk the template pack directory
- For each `.j2` file: check conditions from manifest, skip if falsy
- For looped files: expand the file list (one entry per item in the loop source)
- For all other `.j2` files: include once
- Result: an ordered list of `(template_path, output_path, context)` tuples
- Non-`.j2` files are copied as-is (static assets, images, etc.)

**Stage 3: Render**
- Set up Jinja2 environment with the template pack as the loader root
- For each entry in the plan: render template with spec + loop variables as context, write to output path
- Strip `.j2` suffix, resolve template expressions in directory/file names
- Create directories as needed
- Fail if output directory already exists (no silent overwrites)

**Stage 4: Hooks**
- Run each hook command sequentially in the output directory via subprocess
- Capture stdout/stderr, report failures but don't roll back

## Module Layout

```
src/navi_bootstrap/
├── cli.py              # Click CLI: init + render + validate
├── engine.py           # Plan + Render stages (~150 lines)
├── manifest.py         # Manifest loading + validation (~80 lines)
├── spec.py             # Spec loading + schema validation (~60 lines)
└── hooks.py            # Post-render hook runner (~40 lines)
```

Estimated ~400-500 lines total.

## CLI Interface

```bash
# Quick start — generates a default spec, renders with built-in pack
nboot init --name my-api --language python

# Full spec-driven — you control everything
nboot render --spec project.json --pack ./packs/python-base --out ./my-api

# Validation only
nboot validate --spec project.json --pack ./packs/python-base
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

### `nboot validate`
- `--spec` (required) — validates spec against schema
- `--pack` (optional) — also validates manifest if provided

## What Gets Cut

Everything from the original 6,600-line codebase except the core idea:

- FCPA audit system (7-phase analysis, lifecycle decisions)
- PBJRAG / DSC 9-dimensional analysis
- Canvas validator
- Agent analyzer / agent generator
- Auto-documenter
- Autoheal pipeline
- Web UI
- LLM client / Ollama integration
- Governance pack versioning and upgrade paths
- State tracking (`.nf_toolkit.json`)

Lessons carried forward (not code):

- Spec-driven generation — refined into spec + manifest
- Template pack concept — simplified, self-contained, no inheritance
- Click CLI pattern — two clean commands instead of eight
- Schema validation on inputs — kept for both spec and manifest

## New Repository

Fresh repo: `navi-bootstrap`. Clean history, clean package. The old Neural Forge Bootstrapper repo stays as archaeology.
