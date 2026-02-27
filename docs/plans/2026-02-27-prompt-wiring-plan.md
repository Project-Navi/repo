# Grippy Prompt Wiring Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Wire 10 of 12 unwired prompt files into Grippy's instruction chain so the LLM receives full personality, quality gate, and formatting instructions.

**Architecture:** Introduce `SHARED_PROMPTS` (8 always-on files) and `CHAIN_SUFFIX` (scoring-rubric + output-schema). Refactor `MODE_CHAINS` to contain only mode-specific prefix (system-core + mode prompt). `load_instructions()` composes all three layers. Add 2 new modes (cli, github_app).

**Tech Stack:** Python 3.12+, pytest, Agno Agent framework, ruff, mypy

**Design doc:** `docs/plans/2026-02-27-prompt-wiring-design.md`

---

### Task 1: Write failing tests for new prompt chain structure

**Files:**
- Modify: `tests/test_grippy_prompts.py`

**Step 1: Write the failing tests**

Add these tests to `tests/test_grippy_prompts.py`. They test the new data structures and composition logic that don't exist yet.

At the top of the file, add the new imports alongside the existing ones:

```python
from grippy.prompts import (
    CHAIN_SUFFIX,
    IDENTITY_FILES,
    MODE_CHAINS,
    SHARED_PROMPTS,
    load_identity,
    load_instructions,
    load_prompt_file,
)
```

Update the `full_chain_dir` fixture to create mock files for ALL parts of the chain (not just MODE_CHAINS):

```python
@pytest.fixture
def full_chain_dir(identity_dir: Path) -> Path:
    """Populate prompts_dir with all files needed for any mode chain."""
    # Mode-specific files
    all_mode_files: set[str] = set()
    for chain in MODE_CHAINS.values():
        all_mode_files.update(chain)
    for filename in all_mode_files:
        (identity_dir / filename).write_text(f"# {filename}\nContent here.\n", encoding="utf-8")
    # Shared prompts
    for filename in SHARED_PROMPTS:
        (identity_dir / filename).write_text(f"# {filename}\nShared content.\n", encoding="utf-8")
    # Chain suffix
    for filename in CHAIN_SUFFIX:
        if not (identity_dir / filename).exists():
            (identity_dir / filename).write_text(
                f"# {filename}\nSuffix content.\n", encoding="utf-8"
            )
    return identity_dir
```

Add new test class after the existing `TestModeChains`:

```python
class TestSharedPrompts:
    """Tests for SHARED_PROMPTS and CHAIN_SUFFIX constants."""

    def test_shared_prompts_has_eight_files(self) -> None:
        assert len(SHARED_PROMPTS) == 8

    def test_chain_suffix_is_scoring_then_output(self) -> None:
        assert CHAIN_SUFFIX == ["scoring-rubric.md", "output-schema.md"]

    def test_shared_prompts_not_in_mode_chains(self) -> None:
        """Shared prompts should not appear in any MODE_CHAINS value."""
        for mode, chain in MODE_CHAINS.items():
            for shared in SHARED_PROMPTS:
                assert shared not in chain, (
                    f"{shared} appears in MODE_CHAINS[{mode!r}] — should be in SHARED_PROMPTS only"
                )

    def test_chain_suffix_not_in_mode_chains(self) -> None:
        """CHAIN_SUFFIX files should not appear in any MODE_CHAINS value."""
        for mode, chain in MODE_CHAINS.items():
            for suffix in CHAIN_SUFFIX:
                assert suffix not in chain, (
                    f"{suffix} appears in MODE_CHAINS[{mode!r}] — should be in CHAIN_SUFFIX only"
                )

    def test_all_shared_prompt_files_exist(self) -> None:
        """Every file in SHARED_PROMPTS must exist in prompts_data/."""
        prompts_dir = Path(__file__).resolve().parent.parent / "src" / "grippy" / "prompts_data"
        for filename in SHARED_PROMPTS:
            path = prompts_dir / filename
            assert path.exists(), f"SHARED_PROMPTS file missing: {path}"

    def test_all_chain_suffix_files_exist(self) -> None:
        """Every file in CHAIN_SUFFIX must exist in prompts_data/."""
        prompts_dir = Path(__file__).resolve().parent.parent / "src" / "grippy" / "prompts_data"
        for filename in CHAIN_SUFFIX:
            path = prompts_dir / filename
            assert path.exists(), f"CHAIN_SUFFIX file missing: {path}"
```

Add new test class for composition order:

```python
class TestCompositionOrder:
    """Tests that load_instructions() composes layers correctly."""

    def test_chain_starts_with_system_core(self, full_chain_dir: Path) -> None:
        result = load_instructions(full_chain_dir, mode="pr_review")
        assert "# system-core.md" in result[0]

    def test_chain_ends_with_output_schema(self, full_chain_dir: Path) -> None:
        result = load_instructions(full_chain_dir, mode="pr_review")
        assert "# output-schema.md" in result[-1]

    def test_scoring_rubric_is_second_to_last(self, full_chain_dir: Path) -> None:
        result = load_instructions(full_chain_dir, mode="pr_review")
        assert "# scoring-rubric.md" in result[-2]

    def test_chain_length_is_mode_plus_shared_plus_suffix(self, full_chain_dir: Path) -> None:
        for mode in MODE_CHAINS:
            result = load_instructions(full_chain_dir, mode=mode)
            expected = len(MODE_CHAINS[mode]) + len(SHARED_PROMPTS) + len(CHAIN_SUFFIX)
            assert len(result) == expected, (
                f"Mode {mode!r}: expected {expected} instructions, got {len(result)}"
            )

    def test_shared_prompts_appear_in_every_mode(self, full_chain_dir: Path) -> None:
        for mode in MODE_CHAINS:
            result = load_instructions(full_chain_dir, mode=mode)
            joined = "\n".join(result)
            for filename in SHARED_PROMPTS:
                assert f"# {filename}" in joined, (
                    f"SHARED_PROMPTS file {filename} missing from mode {mode!r}"
                )

    def test_mode_prompt_appears_second(self, full_chain_dir: Path) -> None:
        """The mode-specific prompt is the second instruction."""
        result = load_instructions(full_chain_dir, mode="pr_review")
        assert "# pr-review.md" in result[1]
```

Update existing tests to match new structure:

In `TestLoadInstructions`:
- Change `test_pr_review_mode` assertion from `len(MODE_CHAINS["pr_review"])` to
  `len(MODE_CHAINS["pr_review"]) + len(SHARED_PROMPTS) + len(CHAIN_SUFFIX)`:

```python
def test_pr_review_mode(self, full_chain_dir: Path) -> None:
    result = load_instructions(full_chain_dir, mode="pr_review")
    assert isinstance(result, list)
    expected = len(MODE_CHAINS["pr_review"]) + len(SHARED_PROMPTS) + len(CHAIN_SUFFIX)
    assert len(result) == expected
```

In `TestModeChains`:
- Change `test_all_four_modes_exist` to include new modes:

```python
def test_all_modes_exist(self) -> None:
    expected = {
        "pr_review", "security_audit", "governance_check",
        "surprise_audit", "cli", "github_app",
    }
    assert set(MODE_CHAINS.keys()) == expected
```

- Change `test_all_chains_start_with_system_core` — still valid, MODE_CHAINS still starts with system-core.
- Remove `test_all_chains_end_with_output_schema` — MODE_CHAINS no longer contains output-schema (it's in CHAIN_SUFFIX now). Replace with:

```python
def test_no_chain_contains_suffix_files(self) -> None:
    for mode, chain in MODE_CHAINS.items():
        assert "output-schema.md" not in chain, f"{mode} contains output-schema.md"
        assert "scoring-rubric.md" not in chain, f"{mode} contains scoring-rubric.md"
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_grippy_prompts.py -v`
Expected: ImportError on `CHAIN_SUFFIX` and `SHARED_PROMPTS` (they don't exist yet)

**Step 3: Commit failing tests**

```bash
git add tests/test_grippy_prompts.py
git commit -m "test: add failing tests for prompt chain restructure"
```

---

### Task 2: Implement prompts.py restructure

**Files:**
- Modify: `src/grippy/prompts.py`

**Step 1: Rewrite prompts.py**

Replace the entire `MODE_CHAINS` block and update `load_instructions()`:

```python
"""Prompt chain loader — reads Grippy's markdown prompt files and composes them."""

from __future__ import annotations

from pathlib import Path

# Composition order per prompt-wiring-design.md:
# IDENTITY:      CONSTITUTION + PERSONA (Agno description)
# INSTRUCTIONS:  MODE_CHAINS[mode] + SHARED_PROMPTS + CHAIN_SUFFIX (Agno instructions)

IDENTITY_FILES = ["CONSTITUTION.md", "PERSONA.md"]

# Mode-specific prefix: system-core + mode prompt
MODE_CHAINS: dict[str, list[str]] = {
    "pr_review": ["system-core.md", "pr-review.md"],
    "security_audit": ["system-core.md", "security-audit.md"],
    "governance_check": ["system-core.md", "governance-check.md"],
    "surprise_audit": ["system-core.md", "surprise-audit.md"],
    "cli": ["system-core.md", "cli-mode.md"],
    "github_app": ["system-core.md", "github-app.md"],
}

# Always-on personality + quality gate prompts (all modes)
SHARED_PROMPTS: list[str] = [
    "tone-calibration.md",
    "confidence-filter.md",
    "escalation.md",
    "context-builder.md",
    "catchphrases.md",
    "disguises.md",
    "ascii-art.md",
    "all-clear.md",
]

# Anchored at the end: scoring rubric then output schema
CHAIN_SUFFIX: list[str] = ["scoring-rubric.md", "output-schema.md"]


def load_prompt_file(prompts_dir: Path, filename: str) -> str:
    """Load a single prompt file, stripping the YAML front-matter header."""
    path = prompts_dir / filename
    if not path.exists():
        msg = f"Prompt file not found: {path}"
        raise FileNotFoundError(msg)
    return path.read_text(encoding="utf-8")


def load_identity(prompts_dir: Path) -> str:
    """Load CONSTITUTION + PERSONA — the identity layer (description)."""
    parts = [load_prompt_file(prompts_dir, f) for f in IDENTITY_FILES]
    return "\n\n".join(parts)


def load_instructions(prompts_dir: Path, mode: str = "pr_review") -> list[str]:
    """Load the composed instruction chain for a review mode.

    Composes: MODE_CHAINS[mode] + SHARED_PROMPTS + CHAIN_SUFFIX.

    Returns a list of strings (one per prompt file) for Agno's instructions parameter.
    """
    if mode not in MODE_CHAINS:
        msg = f"Unknown review mode: {mode}. Available: {list(MODE_CHAINS.keys())}"
        raise ValueError(msg)
    chain = MODE_CHAINS[mode] + SHARED_PROMPTS + CHAIN_SUFFIX
    return [load_prompt_file(prompts_dir, f) for f in chain]
```

**Step 2: Run the prompt tests**

Run: `uv run pytest tests/test_grippy_prompts.py -v`
Expected: All tests PASS

**Step 3: Commit implementation**

```bash
git add src/grippy/prompts.py
git commit -m "feat: wire 10 prompt files into instruction chain with shared layer"
```

---

### Task 3: Update agent evolution tests for new modes

**Files:**
- Modify: `tests/test_grippy_agent_evolution.py`

**Step 1: Write the failing test for new modes**

In `TestCreateReviewerBackwardCompat.test_all_modes_work`, add the new modes to the tuple:

```python
def test_all_modes_work(self) -> None:
    """All six review modes produce valid agents."""
    for mode in (
        "pr_review", "security_audit", "governance_check",
        "surprise_audit", "cli", "github_app",
    ):
        agent = create_reviewer(prompts_dir=PROMPTS_DIR, mode=mode)
        assert agent.name == "grippy"
```

**Step 2: Run test to verify it passes**

Run: `uv run pytest tests/test_grippy_agent_evolution.py::TestCreateReviewerBackwardCompat::test_all_modes_work -v`
Expected: PASS (prompts.py already has the new modes from Task 2)

**Step 3: Commit**

```bash
git add tests/test_grippy_agent_evolution.py
git commit -m "test: add cli and github_app modes to agent evolution tests"
```

---

### Task 4: Run full test suite + quality checks

**Files:** None (verification only)

**Step 1: Run all tests**

Run: `uv run pytest tests/ -v`
Expected: 632+ passed, 1 skipped, 0 failures

**Step 2: Run ruff check**

Run: `uv run ruff check src/grippy/prompts.py tests/test_grippy_prompts.py tests/test_grippy_agent_evolution.py`
Expected: No issues

**Step 3: Run ruff format check**

Run: `uv run ruff format --check src/grippy/prompts.py tests/test_grippy_prompts.py tests/test_grippy_agent_evolution.py`
Expected: No reformatting needed

**Step 4: Run mypy**

Run: `uv run mypy src/grippy/prompts.py`
Expected: Success, no errors

**Step 5: Commit any lint/format fixes if needed**

```bash
# Only if Step 2/3/4 required changes
git add -u
git commit -m "chore: lint and format fixes for prompt wiring"
```

---

### Task 5: Update comms thread

**Files:**
- Modify: `.comms/thread.md`

**Step 1: Append session 16 entry**

Append to `.comms/thread.md`:

```markdown
---
[2026-02-27] **alpha**: **Session 16 — Full prompt chain wired. Grippy has a brain.**

### What happened

1. **PR #13 CI diagnosis** — Tests were cancelled (not failed) during Nelson's GitHub Enterprise upgrade. 632 tests pass locally. CI needs re-run.
2. **Prompt wiring design** — Brainstormed and designed the shared-layer architecture. Design doc at `docs/plans/2026-02-27-prompt-wiring-design.md`.
3. **Prompt wiring implementation** — Wired 10 of 12 unwired prompts:
   - 8 always-on SHARED_PROMPTS (tone-calibration, confidence-filter, escalation, context-builder, catchphrases, disguises, ascii-art, all-clear)
   - 2 new modes (cli, github_app)
   - 2 excluded (sdk-easter-egg = separate project, README = docs)
4. **Tests updated** — New composition order tests, shared prompt validation, 6-mode coverage.

### Architecture

```
INSTRUCTIONS = MODE_CHAINS[mode] + SHARED_PROMPTS + CHAIN_SUFFIX
```

- MODE_CHAINS: system-core + mode prompt (6 modes)
- SHARED_PROMPTS: 8 personality/quality files
- CHAIN_SUFFIX: scoring-rubric + output-schema (anchored last)

### Prompt classification

| Wiring | Count | Files |
|--------|-------|-------|
| SHARED_PROMPTS | 8 | tone-calibration, confidence-filter, escalation, context-builder, catchphrases, disguises, ascii-art, all-clear |
| New modes | 2 | cli-mode (mode="cli"), github-app (mode="github_app") |
| Not wired | 2 | sdk-easter-egg, README |

### Next
1. Push and get CI green on this branch
2. Merge PR #13 (codebase search) — CI needs re-run post-Enterprise upgrade
3. Wire Actions cache for Grippy state persistence
4. Grippy meta-analysis with full prompt chain active
```

**Step 2: Commit**

```bash
git add .comms/thread.md
git commit -m "docs: session 16 thread — prompt wiring complete"
```

---

### Task 6: Push and verify CI

**Files:** None

**Step 1: Push to branch**

```bash
git push origin feat/grippy-codebase-search
```

**Step 2: Check CI status**

Run: `gh pr checks 13`
Expected: All checks pass (tests, lint, Grippy review)

---

## Summary

| Task | Description | Files | Commits |
|------|------------|-------|---------|
| 1 | Failing tests for new structure | test_grippy_prompts.py | `test: add failing tests...` |
| 2 | Implement prompts.py restructure | prompts.py | `feat: wire 10 prompt files...` |
| 3 | Update agent evolution tests | test_grippy_agent_evolution.py | `test: add cli and github_app...` |
| 4 | Full suite verification | — | (lint fix if needed) |
| 5 | Update comms thread | thread.md | `docs: session 16 thread...` |
| 6 | Push and verify CI | — | — |

**Total: 3 files modified, ~4 commits, 10 prompts wired.**
