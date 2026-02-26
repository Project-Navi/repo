"""Tests for Grippy prompt chain loaders."""

from __future__ import annotations

from pathlib import Path

import pytest

from grippy.prompts import (
    IDENTITY_FILES,
    MODE_CHAINS,
    load_identity,
    load_instructions,
    load_prompt_file,
)

# --- Fixtures ---


@pytest.fixture
def prompts_dir(tmp_path: Path) -> Path:
    """Create a temp directory with minimal prompt files for testing."""
    d = tmp_path / "prompts"
    d.mkdir()
    return d


@pytest.fixture
def identity_dir(prompts_dir: Path) -> Path:
    """Populate prompts_dir with CONSTITUTION.md and PERSONA.md."""
    (prompts_dir / "CONSTITUTION.md").write_text("You are Grippy.\n", encoding="utf-8")
    (prompts_dir / "PERSONA.md").write_text("Grudging code inspector.\n", encoding="utf-8")
    return prompts_dir


@pytest.fixture
def full_chain_dir(identity_dir: Path) -> Path:
    """Populate prompts_dir with all files needed for pr_review mode chain."""
    for filename in MODE_CHAINS["pr_review"]:
        (identity_dir / filename).write_text(f"# {filename}\nContent here.\n", encoding="utf-8")
    return identity_dir


# --- load_prompt_file ---


class TestLoadPromptFile:
    def test_loads_existing_file(self, prompts_dir: Path) -> None:
        (prompts_dir / "test.md").write_text("hello world", encoding="utf-8")
        result = load_prompt_file(prompts_dir, "test.md")
        assert result == "hello world"

    def test_preserves_content(self, prompts_dir: Path) -> None:
        content = "# Title\n\nParagraph with **bold** and `code`.\n"
        (prompts_dir / "rich.md").write_text(content, encoding="utf-8")
        result = load_prompt_file(prompts_dir, "rich.md")
        assert result == content

    def test_missing_file_raises(self, prompts_dir: Path) -> None:
        with pytest.raises(FileNotFoundError, match="not found"):
            load_prompt_file(prompts_dir, "nonexistent.md")


# --- load_identity ---


class TestLoadIdentity:
    def test_joins_constitution_and_persona(self, identity_dir: Path) -> None:
        result = load_identity(identity_dir)
        assert "You are Grippy." in result
        assert "Grudging code inspector." in result

    def test_double_newline_separator(self, identity_dir: Path) -> None:
        result = load_identity(identity_dir)
        # Files are "You are Grippy.\n" and "Grudging code inspector.\n"
        # Joined with "\n\n" -> "You are Grippy.\n\n\nGrudging code inspector.\n"
        assert "\n\n" in result
        assert result == "You are Grippy.\n\n\nGrudging code inspector.\n"

    def test_missing_constitution_raises(self, prompts_dir: Path) -> None:
        (prompts_dir / "PERSONA.md").write_text("persona", encoding="utf-8")
        with pytest.raises(FileNotFoundError):
            load_identity(prompts_dir)

    def test_missing_persona_raises(self, prompts_dir: Path) -> None:
        (prompts_dir / "CONSTITUTION.md").write_text("constitution", encoding="utf-8")
        with pytest.raises(FileNotFoundError):
            load_identity(prompts_dir)


# --- load_instructions ---


class TestLoadInstructions:
    def test_pr_review_mode(self, full_chain_dir: Path) -> None:
        result = load_instructions(full_chain_dir, mode="pr_review")
        assert isinstance(result, list)
        assert len(result) == len(MODE_CHAINS["pr_review"])

    def test_instructions_content_matches_files(self, full_chain_dir: Path) -> None:
        result = load_instructions(full_chain_dir, mode="pr_review")
        for i, filename in enumerate(MODE_CHAINS["pr_review"]):
            assert f"# {filename}" in result[i]

    def test_unknown_mode_raises(self, full_chain_dir: Path) -> None:
        with pytest.raises(ValueError, match="Unknown review mode"):
            load_instructions(full_chain_dir, mode="nonexistent_mode")

    def test_unknown_mode_lists_available(self, full_chain_dir: Path) -> None:
        with pytest.raises(ValueError, match="pr_review"):
            load_instructions(full_chain_dir, mode="bad")

    def test_default_mode_is_pr_review(self, full_chain_dir: Path) -> None:
        result = load_instructions(full_chain_dir)
        assert len(result) == len(MODE_CHAINS["pr_review"])


# --- MODE_CHAINS structure ---


class TestModeChains:
    def test_all_four_modes_exist(self) -> None:
        expected = {"pr_review", "security_audit", "governance_check", "surprise_audit"}
        assert set(MODE_CHAINS.keys()) == expected

    def test_all_chains_start_with_system_core(self) -> None:
        for mode, chain in MODE_CHAINS.items():
            assert chain[0] == "system-core.md", f"{mode} chain doesn't start with system-core.md"

    def test_all_chains_end_with_output_schema(self) -> None:
        for mode, chain in MODE_CHAINS.items():
            assert chain[-1] == "output-schema.md", (
                f"{mode} chain doesn't end with output-schema.md"
            )

    def test_identity_files_are_constitution_and_persona(self) -> None:
        assert IDENTITY_FILES == ["CONSTITUTION.md", "PERSONA.md"]
