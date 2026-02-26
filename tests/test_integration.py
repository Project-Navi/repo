"""End-to-end integration test: init → apply → diff → verify clean.

Proves the pipeline composes. No existing test runs the full user journey
through sanitize → plan → render → validate as a single flow.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from navi_bootstrap.cli import cli


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def realistic_project(tmp_path: Path) -> Path:
    """A realistic Python project that nboot init can inspect."""
    project = tmp_path / "my-project"
    project.mkdir()

    # pyproject.toml
    (project / "pyproject.toml").write_text(
        "[project]\n"
        'name = "my-project"\n'
        'version = "0.1.0"\n'
        'requires-python = ">=3.12"\n'
        "\n"
        "[dependency-groups]\n"
        'dev = ["pytest>=8.0.0", "ruff>=0.9.0"]\n'
    )

    # Source
    src = project / "src" / "my_project"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("")
    (src / "core.py").write_text("def hello() -> str:\n    return 'hello'\n")

    # Tests
    tests = project / "tests"
    tests.mkdir()
    (tests / "__init__.py").write_text("")
    (tests / "test_core.py").write_text(
        "def test_hello():\n    from my_project.core import hello\n    assert hello() == 'hello'\n"
    )

    # Pre-commit config
    (project / ".pre-commit-config.yaml").write_text("repos: []\n")

    # Git repo (needed for init's git remote detection)
    subprocess.run(["git", "init"], cwd=project, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"], cwd=project, capture_output=True
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=project, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=project, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=project, capture_output=True)

    return project


@pytest.fixture
def base_pack() -> Path:
    """Path to the actual base pack in this repo."""
    pack = Path(__file__).parent.parent / "packs" / "base"
    assert pack.exists(), f"Base pack not found at {pack}"
    return pack


class TestFullPipeline:
    """init → apply → diff: the complete user journey."""

    def test_init_produces_valid_spec(self, runner: CliRunner, realistic_project: Path) -> None:
        """nboot init on a realistic project produces a valid spec."""
        result = runner.invoke(
            cli,
            ["init", "--target", str(realistic_project), "--yes"],
        )
        assert result.exit_code == 0, result.output

        spec_path = realistic_project / "nboot-spec.json"
        assert spec_path.exists()

        spec = json.loads(spec_path.read_text())
        assert spec["name"] == "my-project"
        assert spec["language"] == "python"
        assert spec["python_version"] == "3.12"
        assert spec["structure"]["src_dir"] == "src/my_project"
        assert spec["structure"]["test_dir"] == "tests"

    def test_apply_base_pack_to_inited_project(
        self, runner: CliRunner, realistic_project: Path, base_pack: Path
    ) -> None:
        """init → apply: base pack renders without error onto an inited project."""
        # Step 1: init
        result = runner.invoke(
            cli,
            ["init", "--target", str(realistic_project), "--yes"],
        )
        assert result.exit_code == 0, f"init failed: {result.output}"

        spec_path = realistic_project / "nboot-spec.json"

        # Step 2: apply base pack
        result = runner.invoke(
            cli,
            [
                "apply",
                "--spec",
                str(spec_path),
                "--pack",
                str(base_pack),
                "--target",
                str(realistic_project),
                "--skip-resolve",
            ],
        )
        assert result.exit_code == 0, f"apply failed: {result.output}"
        assert "Applied" in result.output

        # Verify key files were created
        assert (realistic_project / "CLAUDE.md").exists()
        assert (realistic_project / "DEBT.md").exists()

    def test_diff_clean_after_apply(
        self, runner: CliRunner, realistic_project: Path, base_pack: Path
    ) -> None:
        """init → apply → diff: diff should show no changes after a fresh apply."""
        # Step 1: init
        result = runner.invoke(
            cli,
            ["init", "--target", str(realistic_project), "--yes"],
        )
        assert result.exit_code == 0, f"init failed: {result.output}"

        spec_path = realistic_project / "nboot-spec.json"

        # Step 2: apply base pack
        result = runner.invoke(
            cli,
            [
                "apply",
                "--spec",
                str(spec_path),
                "--pack",
                str(base_pack),
                "--target",
                str(realistic_project),
                "--skip-resolve",
            ],
        )
        assert result.exit_code == 0, f"apply failed: {result.output}"

        # Step 3: diff — should be clean (exit 0)
        result = runner.invoke(
            cli,
            [
                "diff",
                "--spec",
                str(spec_path),
                "--pack",
                str(base_pack),
                "--target",
                str(realistic_project),
                "--skip-resolve",
            ],
        )
        assert result.exit_code == 0, f"diff found changes after fresh apply:\n{result.output}"
        assert "No changes" in result.output

    def test_diff_detects_manual_edit(
        self, runner: CliRunner, realistic_project: Path, base_pack: Path
    ) -> None:
        """init → apply → edit → diff: diff detects manual modifications."""
        # Steps 1-2: init + apply
        runner.invoke(cli, ["init", "--target", str(realistic_project), "--yes"])
        spec_path = realistic_project / "nboot-spec.json"
        runner.invoke(
            cli,
            [
                "apply",
                "--spec",
                str(spec_path),
                "--pack",
                str(base_pack),
                "--target",
                str(realistic_project),
                "--skip-resolve",
            ],
        )

        # Step 3: manually edit a rendered file
        claude_md = realistic_project / "CLAUDE.md"
        assert claude_md.exists()
        claude_md.write_text("# I manually changed this\n")

        # Step 4: diff — should detect the change (exit 1)
        result = runner.invoke(
            cli,
            [
                "diff",
                "--spec",
                str(spec_path),
                "--pack",
                str(base_pack),
                "--target",
                str(realistic_project),
                "--skip-resolve",
            ],
        )
        assert result.exit_code == 1, f"diff should have found changes:\n{result.output}"
        assert "CLAUDE.md" in result.output

    def test_rendered_files_contain_spec_values(
        self, runner: CliRunner, realistic_project: Path, base_pack: Path
    ) -> None:
        """Rendered files contain correct spec values (not template variables)."""
        runner.invoke(cli, ["init", "--target", str(realistic_project), "--yes"])
        spec_path = realistic_project / "nboot-spec.json"
        runner.invoke(
            cli,
            [
                "apply",
                "--spec",
                str(spec_path),
                "--pack",
                str(base_pack),
                "--target",
                str(realistic_project),
                "--skip-resolve",
            ],
        )

        # CLAUDE.md should reference the actual project name and paths
        claude_md = (realistic_project / "CLAUDE.md").read_text()
        assert "my-project" in claude_md
        assert "src/my_project" in claude_md
        assert "tests/" in claude_md
        assert "3.12" in claude_md

        # Should NOT contain unrendered Jinja
        assert "{{" not in claude_md
        assert "}}" not in claude_md
        assert "{%" not in claude_md

    def test_skipped_hooks_message_without_trust(
        self, runner: CliRunner, realistic_project: Path, base_pack: Path
    ) -> None:
        """apply without --trust prints skipped hooks message if pack has hooks."""
        runner.invoke(cli, ["init", "--target", str(realistic_project), "--yes"])
        spec_path = realistic_project / "nboot-spec.json"

        # Check if base pack has hooks
        manifest = yaml.safe_load((base_pack / "manifest.yaml").read_text())
        hooks = manifest.get("hooks", [])

        result = runner.invoke(
            cli,
            [
                "apply",
                "--spec",
                str(spec_path),
                "--pack",
                str(base_pack),
                "--target",
                str(realistic_project),
                "--skip-resolve",
            ],
        )
        assert result.exit_code == 0

        if hooks:
            assert "--trust" in result.output
        # If no hooks, no trust message needed — that's correct behavior too


class TestSanitizePlanRenderComposition:
    """Test that sanitize → plan → render composes without breaking features."""

    def test_spec_with_jinja_in_name_is_safe(
        self, runner: CliRunner, tmp_path: Path, base_pack: Path
    ) -> None:
        """A spec with {{ in the name gets sanitized before reaching templates."""
        spec = {
            "name": "{{ malicious }}",
            "language": "python",
            "python_version": "3.12",
            "features": {},
        }
        spec_path = tmp_path / "spec.json"
        spec_path.write_text(json.dumps(spec))

        target = tmp_path / "target"
        target.mkdir()

        result = runner.invoke(
            cli,
            [
                "apply",
                "--spec",
                str(spec_path),
                "--pack",
                str(base_pack),
                "--target",
                str(target),
                "--skip-resolve",
            ],
        )
        assert result.exit_code == 0

        # The name should be sanitized in output, not rendered as a template
        claude_md = (target / "CLAUDE.md").read_text()
        assert "malicious" not in claude_md or "\\{\\{" in claude_md
