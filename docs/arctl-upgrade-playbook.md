# arctl DevOps Bootstrap Playbook

Detailed record of what was done to upgrade arctl's DevOps posture as an upstream contribution. Written from context to capture the full decision chain for future scripting.

## Phase 1: Reconnaissance

### 1.1 Audit the source project (arctl)

Explored the target repo to understand what exists and what's missing:

- **Build system**: setuptools via `pyproject.toml`, Python 3.9+, core dep is numpy
- **Existing CI**: bare-bones `.github/workflows/tests.yml` — 3 Python versions (3.9-3.11), unpinned actions (`@v4`, `@v5`), no lint/security/permissions, single `test` job using `pip install -e .` and `unittest discover`
- **Existing docs**: LICENSE (MIT), CONTRIBUTING.md, README.md, docs/ directory with ARCHITECTURE.md, TESTING.md, QUICKSTART.md
- **Missing entirely**: pre-commit hooks, linter config, type checker config, security scanning, CodeQL, Scorecard, Dependabot, issue templates, PR template, lockfile
- **Code style declared but not enforced**: CONTRIBUTING.md says PEP 8, Google docstrings, type hints, conventional commits — but no tooling backs it up

### 1.2 Audit the reference project (navi-os)

Explored navi-os to extract the patterns we wanted to port:

- **Pre-commit**: `.pre-commit-config.yaml` with ruff, bandit, detect-secrets, SPDX headers, file hygiene hooks
- **CI/CD**: 7 workflows (test matrix, lint, security, Semgrep SAST, CodeQL, Scorecard, fuzzing, release)
- **Security**: SECURITY.md, Bandit with `.bandit` config, detect-secrets with baseline, pip-audit, Semgrep, CodeQL, OpenSSF Scorecard, ClusterFuzzLite
- **Templates**: structured issue forms (bug, feature), PR template, config.yml disabling blank issues
- **Dependency management**: Dependabot with grouped updates, pinned action SHAs, Docker digest pins
- **Code quality**: ruff (lint + format, line-length 100), strict mypy, coverage gates
- **Key patterns**: all actions SHA-pinned, harden-runner on every job, least-privilege permissions, `persist-credentials: false`, uv as package manager

## Phase 2: Scoping Decisions

### What we included (option B from brainstorming)

1. Pre-commit hooks (ruff, bandit, detect-secrets, file hygiene)
2. CI workflows (test matrix, lint, security, CodeQL, Scorecard)
3. Dependabot config
4. Code quality config in pyproject.toml (ruff, mypy)
5. GitHub templates (issue forms, PR template)
6. Dev dependency group for CI tools
7. uv.lock for supply chain reproducibility

### What we excluded (and why)

| Excluded | Reason |
|----------|--------|
| SECURITY.md | Governance doc — maintainer's voice |
| CODE_OF_CONDUCT.md | Governance doc — maintainer's voice |
| CODEOWNERS | Governance doc — maintainer's voice |
| FUNDING.yml | Governance doc — maintainer's voice |
| SPDX license headers | License policy — their call, MIT is self-evident |
| Semgrep SAST | Too heavy for a small library, CodeQL covers it |
| ClusterFuzzLite | No fuzz targets exist in arctl |
| Quality gates/scripts | Too opinionated for an upstream contribution |
| Docker configs | arctl is a library, not a service |
| Coverage enforcement | Let the maintainer decide thresholds |
| Source code changes | Explicitly out of scope |
| Doc/README/CONTRIBUTING changes | Explicitly out of scope |

### Key design decisions

1. **uv in CI only (not full migration)**: CI uses `uv sync` for speed and lockfile; `pip install -e .` still works. Avoids forcing a developer experience change.
2. **No GIF exclusion on large file check**: existing GIFs are in history; the hook only gates future commits.
3. **mypy not in pre-commit**: runs in CI with `--ignore-missing-imports` for numpy stubs. Pre-commit mypy causes too many false positives.
4. **Bandit python marker**: `bandit>=1.9.3; python_version >= '3.10'` because bandit dropped 3.9 support but arctl still declares `requires-python = ">=3.9"`. Dev tools only run on 3.12 in CI anyway.
5. **scorecard `publish_results: true`**: enables public OSSF results. No badge automation — that's the maintainer's repo layout.

## Phase 3: Implementation

### 3.1 Setup

```bash
# From the target repo root
# 1. Add .worktrees/ to .gitignore and commit
echo ".worktrees/" >> .gitignore
git add .gitignore
git commit -m "chore: add .worktrees/ to .gitignore"

# 2. Create worktree on feature branch
git worktree add .worktrees/devops-security -b feature/devops-security-upgrade

# 3. Install project and verify baseline
cd .worktrees/devops-security
pip install -e .
python run_tests.py  # confirm all tests pass before any changes
```

### 3.2 File creation order

Each step was a separate commit during development, squashed to one at the end.

#### Step 1: Pre-commit hooks

**Create `.pre-commit-config.yaml`:**

```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
        args: ['--unsafe']
      - id: check-added-large-files
        args: ['--maxkb=1024']
      - id: check-merge-conflict

  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.9.2
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/PyCQA/bandit
    rev: 1.9.3
    hooks:
      - id: bandit
        args: [-r, <source_package>/, -ll, -q]
        pass_filenames: false

  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.5.0
    hooks:
      - id: detect-secrets
        args: ['--baseline', '.secrets.baseline']
```

**Create `.secrets.baseline`:** JSON file with detect-secrets v1.5.0 schema. Must include ALL default plugins (26 total). The original implementation missed 3 plugins (`GitLabTokenDetector`, `IPPublicDetector`, `SendGridDetector`) — caught by adversarial audit.

#### Step 2: Code quality config

**Append to `pyproject.toml`:**

```toml
[dependency-groups]
dev = [
    "ruff>=0.9.2",
    "bandit>=1.9.3; python_version >= '3.10'",
    "mypy>=1.0",
    "pytest>=6.0",
]

[tool.ruff]
line-length = 100
target-version = "py39"  # match requires-python

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP", "B", "RUF", "C4"]
ignore = ["E501"]  # formatter handles line length

[tool.ruff.format]
line-length = 100

[tool.mypy]
python_version = "3.9"  # match requires-python
disallow_untyped_defs = true
disallow_incomplete_defs = true
warn_redundant_casts = true
warn_unused_ignores = true
strict_equality = true

# Add overrides for every optional dependency that lacks type stubs
[[tool.mypy.overrides]]
module = "numpy.*"
ignore_missing_imports = true

# ... repeat for each optional dep (torch, sentence_transformers, etc.)

[[tool.mypy.overrides]]
module = "tests.*"
disallow_untyped_defs = false
```

**Critical lesson:** the `[dependency-groups] dev` section is essential. Without it, `uv sync --all-extras` installs runtime deps but NOT dev tools (ruff, bandit, mypy, pytest). The CI lint job will fail silently because the tools aren't available. This was caught by adversarial audit.

**Critical lesson:** if the project's `requires-python` is older than what dev tools support (e.g., bandit needs 3.10+ but project supports 3.9+), use a python_version marker on the dev dependency. Don't bump the project's requires-python — that's the maintainer's call.

#### Step 3: Main CI workflow

**Replace `.github/workflows/tests.yml`** with three parallel jobs:

1. **test**: Python version matrix (match project's supported range + newer), uv for install, pytest
2. **lint**: Single Python version (3.12), ruff check, ruff format --check, bandit, mypy
3. **security**: Single Python version (3.12), `uvx pip-audit==<pinned_version>`

**Hardening checklist for every workflow:**
- [ ] Top-level `permissions: {}` (or `read-all` for Scorecard)
- [ ] Job-level `permissions: contents: read` (add specific grants as needed)
- [ ] `step-security/harden-runner` as FIRST step of every job, `egress-policy: audit`
- [ ] `actions/checkout` with `persist-credentials: false`
- [ ] ALL action refs pinned to full 40-char commit SHAs with version comment
- [ ] `concurrency` group to avoid duplicate runs
- [ ] `timeout-minutes` on every job

#### Step 4: CodeQL workflow

**Create `.github/workflows/codeql.yml`:**
- Triggers: push to main, PR to main, weekly schedule
- Python language only, security-extended queries
- Same hardening checklist as above

#### Step 5: OpenSSF Scorecard workflow

**Create `.github/workflows/scorecard.yml`:**
- Triggers: push to main, weekly schedule, workflow_dispatch
- `permissions: read-all` at top (Scorecard's documented pattern)
- Job needs: `security-events: write`, `id-token: write`, `contents: read`, `actions: read`
- `cancel-in-progress: false` (don't cancel mid-scan)
- `persist-credentials: false` on checkout
- SARIF upload to Security tab

#### Step 6: Dependabot

**Create `.github/dependabot.yml`:**
- pip ecosystem: weekly, grouped by production minor/patch
- github-actions ecosystem: weekly, all grouped
- Commit prefixes matching project's conventional commits (`deps`, `ci`)
- Don't add a `development-dependencies` group unless the project actually has dev-type deps that Dependabot would classify as such

#### Step 7: GitHub templates

**Create `.github/ISSUE_TEMPLATE/`:**
- `config.yml`: disable blank issues, link to security advisories
- `bug_report.yml`: structured form with project-specific category dropdown
- `feature_request.yml`: structured form with contribution willingness

**Create `.github/PULL_REQUEST_TEMPLATE.md`:**
- Type of change checkboxes
- Checklist referencing project's actual test/lint commands
- Related issues section

#### Step 8: Generate lockfile

```bash
uv lock  # generates uv.lock from pyproject.toml
git add uv.lock
```

## Phase 4: Adversarial Audit

This was the most valuable phase. Three parallel audits:

### 4.1 Workflow injection audit

Checked every `${{ }}` expression in `run:` blocks for injection vectors. Found:
- `${{ matrix.python-version }}` in `run:` — safe (author-controlled)
- `${{ github.head_ref }}` in concurrency groups — safe (metadata, not shell)
- No `pull_request_target` triggers (good)

### 4.2 SHA verification audit

**This caught the most critical bugs.** The implementation subagent hallucinated plausible-looking SHAs that were close to real ones but didn't actually exist:

| Action | Hallucinated SHA | Real SHA | Chars matching |
|--------|-----------------|----------|---------------|
| `step-security/harden-runner` | `...01c0a04d8d7ad2a3e514d8` | `...01f0f96f84700a4088b9f0` | 20/40 |
| `ossf/scorecard-action` | `...0d5cf5e36ddca94b2` (claimed v2.4.4) | `...0d5cf5e36ddca8cde` (real v2.4.2) | 36/40 |

**Lesson: ALWAYS verify action SHAs against the actual repo using `gh api`:**

```bash
# For lightweight tags (direct commit reference)
gh api repos/OWNER/REPO/git/refs/tags/vX.Y.Z --jq '.object.sha'

# For annotated tags (need to dereference tag object → commit)
TAG_SHA=$(gh api repos/OWNER/REPO/git/refs/tags/vX.Y.Z --jq '.object.sha')
gh api repos/OWNER/REPO/git/tags/$TAG_SHA --jq '.object.sha'
```

### 4.3 Config correctness audit

Found:
- **Missing dev dependencies**: ruff/bandit/mypy not declared anywhere — CI lint job DOA
- **Missing detect-secrets plugins**: 3 of 26 default plugins omitted
- **Dead Dependabot group**: `development-dependencies` group matched nothing
- **Missing `persist-credentials: false`** on checkout in tests.yml and codeql.yml
- **Unpinned `uvx pip-audit`**: resolved from PyPI at runtime with no version lock
- **Missing trailing newline**: pyproject.toml failed POSIX convention (own pre-commit hook would flag it)
- **No uv.lock**: dependencies resolved fresh every CI run (supply chain risk)
- **Pre-existing lint violations**: unused imports, old-style typing, missing annotations — documented as pre-existing, not fixed

### 4.4 Bandit scan

Ran bandit against the source in a clean Python 3.10 venv:
```bash
uv venv /tmp/audit-env --python 3.10
uv pip install --python /tmp/audit-env/bin/python -e . bandit
/tmp/audit-env/bin/bandit -r <source_package>/ -ll
# Result: 725 lines scanned, 0 findings
```

## Phase 5: Finishing

### 5.1 Squash commits

```bash
# Soft reset to branch point — keeps all changes staged
git reset --soft $(git merge-base HEAD main)
git commit -m "ci: add DevOps infrastructure, security tooling, and GitHub templates

<detailed description of all changes and maintainer notes>"
```

### 5.2 Fork, push, and PR

```bash
# Create fork on your account
gh repo fork UPSTREAM_OWNER/REPO --clone=false

# Add fork as remote
git remote add fork https://github.com/YOUR_ACCOUNT/REPO.git

# Push feature branch
git push -u fork feature/devops-security-upgrade

# Open PR from fork to upstream
gh pr create \
  --repo UPSTREAM_OWNER/REPO \
  --head YOUR_ACCOUNT:feature/devops-security-upgrade \
  --base main \
  --title "ci: add DevOps infrastructure, security tooling, and GitHub templates" \
  --body "<PR body with summary, maintainer notes, test plan>"
```

### 5.3 Cleanup

```bash
cd /path/to/original/repo
git worktree remove .worktrees/devops-security --force
```

## Scripting Notes for Future Bootstrapper

### Inputs needed

1. **Target repo path** (local clone)
2. **Reference repo path** (navi-os or similar, for pattern extraction)
3. **Fork account** (GitHub username/org)
4. **Source package name** (e.g., `arctl/` — the directory bandit/ruff scan)
5. **Python minimum version** (from `requires-python`)
6. **Optional dependencies** (for mypy overrides)

### What can be deterministic

- File creation (pre-commit, secrets baseline, workflows, templates, dependabot)
- pyproject.toml tool config (parameterized by python version and package name)
- SHA lookups via `gh api`
- uv.lock generation
- Validation (YAML/TOML/JSON parsing, test suite)

### What needs human judgment

- Scope decisions (which navi-os patterns apply to the target)
- Bandit skip rules (does the target use raw SQL? has custom security patterns?)
- mypy override list (depends on optional deps)
- Template categories (must match the project's module structure)
- Whether to bump requires-python or use markers for dev tools
- PR description (maintainer notes about pre-existing issues)

### Critical automation gates

1. **SHA verification**: MUST query GitHub API for every action SHA. Never trust LLM-generated SHAs.
2. **Dev dependency resolution**: MUST run `uv lock` and handle resolution failures (python version conflicts).
3. **Baseline test run**: MUST run full test suite before AND after changes.
4. **Pre-existing lint check**: SHOULD run ruff/mypy against source to document what the maintainer will see, but NOT fix it.
