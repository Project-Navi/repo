"""Prompt chain loader — reads Grippy's markdown prompt files and composes them."""

from __future__ import annotations

from pathlib import Path

# Composition order per system-core.md and grippy-integration-notes.md:
# CONSTITUTION + PERSONA + system-core + [mode prompt] + scoring-rubric + output-schema

IDENTITY_FILES = ["CONSTITUTION.md", "PERSONA.md"]

MODE_CHAINS: dict[str, list[str]] = {
    "pr_review": ["system-core.md", "pr-review.md", "scoring-rubric.md", "output-schema.md"],
    "security_audit": [
        "system-core.md",
        "security-audit.md",
        "scoring-rubric.md",
        "output-schema.md",
    ],
    "governance_check": [
        "system-core.md",
        "governance-check.md",
        "scoring-rubric.md",
        "output-schema.md",
    ],
    "surprise_audit": [
        "system-core.md",
        "surprise-audit.md",
        "scoring-rubric.md",
        "output-schema.md",
    ],
}


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
    """Load the mode-specific instruction chain.

    Returns a list of strings (one per prompt file) for Agno's instructions parameter.
    """
    if mode not in MODE_CHAINS:
        msg = f"Unknown review mode: {mode}. Available: {list(MODE_CHAINS.keys())}"
        raise ValueError(msg)
    return [load_prompt_file(prompts_dir, f) for f in MODE_CHAINS[mode]]
