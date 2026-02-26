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

PACKS_DIR = Path(__file__).parent.parent / "packs"


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


# ---------------------------------------------------------------------------
# Helpers for multi-pack tests
# ---------------------------------------------------------------------------


def _make_spec(tmp_path: Path, *, ci: bool = True) -> Path:
    """Write a realistic spec and return its path."""
    spec = {
        "name": "integration-test",
        "language": "python",
        "python_version": "3.12",
        "structure": {"src_dir": "src/integration_test", "test_dir": "tests"},
        "features": {"ci": ci, "dependabot": True, "pre_commit": True},
        "github": {"org": "test-org", "repo": "integration-test"},
    }
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(spec))
    return path


def _apply_pack(runner: CliRunner, spec_path: Path, pack_name: str, target: Path) -> None:
    """Apply a named pack and assert success."""
    pack = PACKS_DIR / pack_name
    result = runner.invoke(
        cli,
        [
            "apply",
            "--spec",
            str(spec_path),
            "--pack",
            str(pack),
            "--target",
            str(target),
            "--skip-resolve",
        ],
    )
    assert result.exit_code == 0, f"apply {pack_name} failed: {result.output}"


class TestMultiPackComposition:
    """Apply base + elective packs in sequence — the real user journey."""

    def test_base_then_elective_applies_cleanly(self, runner: CliRunner, tmp_path: Path) -> None:
        """base → github-templates: sequential apply without conflict."""
        target = tmp_path / "project"
        target.mkdir()
        spec_path = _make_spec(tmp_path)

        _apply_pack(runner, spec_path, "base", target)
        _apply_pack(runner, spec_path, "github-templates", target)

        # Base files exist
        assert (target / "CLAUDE.md").exists()
        # Elective files exist
        assert (target / ".github" / "ISSUE_TEMPLATE" / "bug_report.yml").exists()
        assert (target / ".github" / "PULL_REQUEST_TEMPLATE.md").exists()

    def test_base_then_multiple_electives(self, runner: CliRunner, tmp_path: Path) -> None:
        """base → security-scanning → review-system: three packs compose."""
        target = tmp_path / "project"
        target.mkdir()
        spec_path = _make_spec(tmp_path, ci=True)

        _apply_pack(runner, spec_path, "base", target)
        _apply_pack(runner, spec_path, "security-scanning", target)
        _apply_pack(runner, spec_path, "review-system", target)

        # All three pack outputs coexist
        assert (target / "CLAUDE.md").exists()
        assert (target / ".github" / "workflows" / "codeql.yml").exists()
        assert (target / ".grippy.yaml").exists()

    def test_diff_clean_after_multi_pack_apply(self, runner: CliRunner, tmp_path: Path) -> None:
        """base → github-templates → diff each: no drift after apply."""
        target = tmp_path / "project"
        target.mkdir()
        spec_path = _make_spec(tmp_path)

        _apply_pack(runner, spec_path, "base", target)
        _apply_pack(runner, spec_path, "github-templates", target)

        # Diff base — should be clean
        result = runner.invoke(
            cli,
            [
                "diff",
                "--spec",
                str(spec_path),
                "--pack",
                str(PACKS_DIR / "base"),
                "--target",
                str(target),
                "--skip-resolve",
            ],
        )
        assert result.exit_code == 0, f"base diff found drift:\n{result.output}"

        # Diff github-templates — should be clean
        result = runner.invoke(
            cli,
            [
                "diff",
                "--spec",
                str(spec_path),
                "--pack",
                str(PACKS_DIR / "github-templates"),
                "--target",
                str(target),
                "--skip-resolve",
            ],
        )
        assert result.exit_code == 0, f"github-templates diff found drift:\n{result.output}"

    def test_elective_without_base_still_works(self, runner: CliRunner, tmp_path: Path) -> None:
        """Elective packs don't hard-fail without base — they just render their own files."""
        target = tmp_path / "project"
        target.mkdir()
        spec_path = _make_spec(tmp_path)

        _apply_pack(runner, spec_path, "code-hygiene", target)
        assert (target / "CONTRIBUTING.md").exists()

    def test_all_packs_apply_without_recon(self, runner: CliRunner, tmp_path: Path) -> None:
        """Every pack handles missing spec.recon gracefully."""
        spec_path = _make_spec(tmp_path, ci=True)
        all_packs = [
            "base",
            "code-hygiene",
            "github-templates",
            "quality-gates",
            "release-pipeline",
            "review-system",
            "security-scanning",
        ]
        for pack_name in all_packs:
            target = tmp_path / f"project-{pack_name}"
            target.mkdir()
            _apply_pack(runner, spec_path, pack_name, target)


class TestConditionalTemplates:
    """Templates with conditions evaluate correctly against spec values."""

    def test_security_scanning_with_ci_enabled(self, runner: CliRunner, tmp_path: Path) -> None:
        """security-scanning templates render when spec.features.ci is true."""
        target = tmp_path / "project"
        target.mkdir()
        spec_path = _make_spec(tmp_path, ci=True)

        _apply_pack(runner, spec_path, "base", target)
        _apply_pack(runner, spec_path, "security-scanning", target)

        assert (target / ".github" / "workflows" / "codeql.yml").exists()
        assert (target / ".github" / "workflows" / "scorecard.yml").exists()

    def test_security_scanning_with_ci_disabled(self, runner: CliRunner, tmp_path: Path) -> None:
        """security-scanning templates are skipped when spec.features.ci is false."""
        target = tmp_path / "project"
        target.mkdir()
        spec_path = _make_spec(tmp_path, ci=False)

        _apply_pack(runner, spec_path, "base", target)
        _apply_pack(runner, spec_path, "security-scanning", target)

        # Conditional templates should NOT be rendered
        assert not (target / ".github" / "workflows" / "codeql.yml").exists()
        assert not (target / ".github" / "workflows" / "scorecard.yml").exists()


class TestGreenfieldRender:
    """render (greenfield) pipeline with real packs."""

    def test_render_base_pack_creates_project(self, runner: CliRunner, tmp_path: Path) -> None:
        """render creates a new project directory from the base pack."""
        spec_path = _make_spec(tmp_path)
        out_dir = tmp_path / "new-project"

        result = runner.invoke(
            cli,
            [
                "render",
                "--spec",
                str(spec_path),
                "--pack",
                str(PACKS_DIR / "base"),
                "--out",
                str(out_dir),
                "--skip-resolve",
            ],
        )
        assert result.exit_code == 0, f"render failed: {result.output}"
        assert (out_dir / "CLAUDE.md").exists()
        assert (out_dir / ".pre-commit-config.yaml").exists()

        # Verify content has real values
        claude_md = (out_dir / "CLAUDE.md").read_text()
        assert "integration-test" in claude_md
        assert "{{" not in claude_md

    def test_render_then_diff_is_clean(self, runner: CliRunner, tmp_path: Path) -> None:
        """render → diff: freshly rendered project shows no drift."""
        spec_path = _make_spec(tmp_path)
        out_dir = tmp_path / "new-project"

        runner.invoke(
            cli,
            [
                "render",
                "--spec",
                str(spec_path),
                "--pack",
                str(PACKS_DIR / "base"),
                "--out",
                str(out_dir),
                "--skip-resolve",
            ],
        )

        result = runner.invoke(
            cli,
            [
                "diff",
                "--spec",
                str(spec_path),
                "--pack",
                str(PACKS_DIR / "base"),
                "--target",
                str(out_dir),
                "--skip-resolve",
            ],
        )
        assert result.exit_code == 0, f"diff found drift after render:\n{result.output}"


class TestValidationComposition:
    """Validation execution with --trust against real packs."""

    def test_apply_with_trust_runs_validations(self, runner: CliRunner, tmp_path: Path) -> None:
        """Packs with validations run them when --trust is passed."""
        target = tmp_path / "project"
        target.mkdir()
        spec_path = _make_spec(tmp_path)

        # Apply base first
        _apply_pack(runner, spec_path, "base", target)

        # Apply github-templates with --trust (has yaml validations)
        pack = PACKS_DIR / "github-templates"
        result = runner.invoke(
            cli,
            [
                "apply",
                "--spec",
                str(spec_path),
                "--pack",
                str(pack),
                "--target",
                str(target),
                "--skip-resolve",
                "--trust",
            ],
        )
        assert result.exit_code == 0, f"apply with trust failed: {result.output}"

        # Should show validation results
        manifest = yaml.safe_load((pack / "manifest.yaml").read_text())
        if manifest.get("validation"):
            assert "PASS" in result.output or "SKIP" in result.output


# ---------------------------------------------------------------------------
# Wave 1: Critical composition boundaries
# ---------------------------------------------------------------------------


def _diff_pack(runner: CliRunner, spec_path: Path, pack_name: str, target: Path) -> int:
    """Run diff on a named pack and return exit code."""
    pack = PACKS_DIR / pack_name
    result = runner.invoke(
        cli,
        [
            "diff",
            "--spec",
            str(spec_path),
            "--pack",
            str(pack),
            "--target",
            str(target),
            "--skip-resolve",
        ],
    )
    return result.exit_code


class TestReapplyIdempotency:
    """Applying the same pack twice must not corrupt state."""

    def test_double_apply_base_diff_clean(self, runner: CliRunner, tmp_path: Path) -> None:
        """base applied twice → diff is still clean."""
        target = tmp_path / "project"
        target.mkdir()
        spec_path = _make_spec(tmp_path)

        _apply_pack(runner, spec_path, "base", target)
        _apply_pack(runner, spec_path, "base", target)

        assert _diff_pack(runner, spec_path, "base", target) == 0

    def test_double_apply_preserves_append_markers(self, runner: CliRunner, tmp_path: Path) -> None:
        """Append-mode file has exactly one marker block after double apply."""
        target = tmp_path / "project"
        target.mkdir()
        # Need a pyproject.toml for append mode to target
        (target / "pyproject.toml").write_text('[project]\nname = "test"\nversion = "0.1.0"\n')
        spec_path = _make_spec(tmp_path)

        _apply_pack(runner, spec_path, "base", target)
        _apply_pack(runner, spec_path, "base", target)

        content = (target / "pyproject.toml").read_text()
        marker_count = content.count("# --- nboot: base ---")
        assert marker_count == 1, f"Expected 1 marker block, found {marker_count}:\n{content}"

    def test_double_apply_elective_diff_clean(self, runner: CliRunner, tmp_path: Path) -> None:
        """Elective pack applied twice → diff still clean."""
        target = tmp_path / "project"
        target.mkdir()
        spec_path = _make_spec(tmp_path)

        _apply_pack(runner, spec_path, "github-templates", target)
        _apply_pack(runner, spec_path, "github-templates", target)

        assert _diff_pack(runner, spec_path, "github-templates", target) == 0


class TestDiffUnappliedPack:
    """Diff on packs that haven't been applied shows all files as new."""

    def test_diff_on_empty_target_shows_changes(self, runner: CliRunner, tmp_path: Path) -> None:
        """Diffing a pack against an empty dir reports all files as changes."""
        target = tmp_path / "project"
        target.mkdir()
        spec_path = _make_spec(tmp_path)

        pack = PACKS_DIR / "github-templates"
        result = runner.invoke(
            cli,
            [
                "diff",
                "--spec",
                str(spec_path),
                "--pack",
                str(pack),
                "--target",
                str(target),
                "--skip-resolve",
            ],
        )
        assert result.exit_code == 1  # changes detected
        assert "(new)" in result.output
        assert "would change" in result.output

    def test_diff_base_on_empty_target(self, runner: CliRunner, tmp_path: Path) -> None:
        """Base pack diff against empty dir shows all base files as new."""
        target = tmp_path / "project"
        target.mkdir()
        spec_path = _make_spec(tmp_path)

        result = runner.invoke(
            cli,
            [
                "diff",
                "--spec",
                str(spec_path),
                "--pack",
                str(PACKS_DIR / "base"),
                "--target",
                str(target),
                "--skip-resolve",
            ],
        )
        assert result.exit_code == 1
        assert "CLAUDE.md" in result.output


class TestAllPacksSequential:
    """Apply all 7 packs to a single target in dependency order."""

    def test_all_packs_compose_and_diff_clean(self, runner: CliRunner, tmp_path: Path) -> None:
        """base then all 6 electives → diff each is clean."""
        target = tmp_path / "project"
        target.mkdir()
        # Need pyproject.toml for base append mode
        (target / "pyproject.toml").write_text('[project]\nname = "test"\nversion = "0.1.0"\n')
        spec_path = _make_spec(tmp_path, ci=True)

        pack_order = [
            "base",
            "code-hygiene",
            "github-templates",
            "quality-gates",
            "release-pipeline",
            "review-system",
            "security-scanning",
        ]

        # Apply all in order
        for pack_name in pack_order:
            _apply_pack(runner, spec_path, pack_name, target)

        # Diff each — all should be clean
        for pack_name in pack_order:
            exit_code = _diff_pack(runner, spec_path, pack_name, target)
            assert exit_code == 0, f"Drift detected in {pack_name} after full apply"

    def test_all_packs_file_count(self, runner: CliRunner, tmp_path: Path) -> None:
        """All 7 packs produce at least 15 distinct files."""
        target = tmp_path / "project"
        target.mkdir()
        (target / "pyproject.toml").write_text('[project]\nname = "test"\nversion = "0.1.0"\n')
        spec_path = _make_spec(tmp_path, ci=True)

        pack_order = [
            "base",
            "code-hygiene",
            "github-templates",
            "quality-gates",
            "release-pipeline",
            "review-system",
            "security-scanning",
        ]

        for pack_name in pack_order:
            _apply_pack(runner, spec_path, pack_name, target)

        # Count rendered files (excluding pyproject.toml which was pre-existing)
        all_files = list(target.rglob("*"))
        file_count = sum(1 for f in all_files if f.is_file())
        assert file_count >= 15, f"Expected >=15 files, got {file_count}"


class TestGreenfieldVsApply:
    """Greenfield render and apply produce consistent output."""

    def test_create_mode_files_match(self, runner: CliRunner, tmp_path: Path) -> None:
        """Create-mode files are identical in greenfield and apply."""
        spec_path = _make_spec(tmp_path)

        # Greenfield render
        render_dir = tmp_path / "rendered"
        runner.invoke(
            cli,
            [
                "render",
                "--spec",
                str(spec_path),
                "--pack",
                str(PACKS_DIR / "base"),
                "--out",
                str(render_dir),
                "--skip-resolve",
            ],
        )

        # Apply to existing dir
        apply_dir = tmp_path / "applied"
        apply_dir.mkdir()
        (apply_dir / "pyproject.toml").write_text('[project]\nname = "test"\nversion = "0.1.0"\n')
        _apply_pack(runner, spec_path, "base", apply_dir)

        # Compare create-mode files (not append-mode like pyproject.toml)
        for name in ["CLAUDE.md", "DEBT.md", ".github/dependabot.yml"]:
            render_file = render_dir / name
            apply_file = apply_dir / name
            if render_file.exists() and apply_file.exists():
                assert render_file.read_text() == apply_file.read_text(), f"Mismatch in {name}"

    def test_greenfield_rejects_existing_file(self, runner: CliRunner, tmp_path: Path) -> None:
        """Greenfield mode fails when target already has a file."""
        spec_path = _make_spec(tmp_path)
        out_dir = tmp_path / "project"
        out_dir.mkdir()
        (out_dir / "CLAUDE.md").write_text("# existing\n")

        result = runner.invoke(
            cli,
            [
                "render",
                "--spec",
                str(spec_path),
                "--pack",
                str(PACKS_DIR / "base"),
                "--out",
                str(out_dir),
                "--skip-resolve",
            ],
        )
        assert result.exit_code != 0
        assert "exists" in result.output.lower()


class TestSpecEdgeCases:
    """Spec edge cases through the full pipeline."""

    def test_minimal_spec_applies(self, runner: CliRunner, tmp_path: Path) -> None:
        """Only name + language — every pack uses defaults gracefully."""
        spec = {"name": "minimal", "language": "python"}
        spec_path = tmp_path / "spec.json"
        spec_path.write_text(json.dumps(spec))

        target = tmp_path / "project"
        target.mkdir()

        pack = PACKS_DIR / "base"
        result = runner.invoke(
            cli,
            [
                "apply",
                "--spec",
                str(spec_path),
                "--pack",
                str(pack),
                "--target",
                str(target),
                "--skip-resolve",
            ],
        )
        assert result.exit_code == 0, f"Minimal spec failed: {result.output}"
        assert (target / "CLAUDE.md").exists()

        # Defaults should appear in rendered content
        claude_md = (target / "CLAUDE.md").read_text()
        assert "minimal" in claude_md
        assert "3.12" in claude_md  # default python_version

    def test_empty_features_skips_conditional_templates(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """features: {} means all conditionals evaluate false."""
        spec = {"name": "bare", "language": "python", "features": {}}
        spec_path = tmp_path / "spec.json"
        spec_path.write_text(json.dumps(spec))

        target = tmp_path / "project"
        target.mkdir()

        _apply_pack(runner, spec_path, "base", target)

        # ci conditional templates should NOT render
        assert not (target / ".github" / "workflows" / "tests.yml").exists()
        # pre_commit conditional template should NOT render
        assert not (target / ".pre-commit-config.yaml").exists()
        # Unconditional files should render
        assert (target / "CLAUDE.md").exists()
        assert (target / "DEBT.md").exists()

    def test_extra_unknown_fields_pass_through(self, runner: CliRunner, tmp_path: Path) -> None:
        """Extra fields in spec are allowed and don't break rendering."""
        spec = {
            "name": "extended",
            "language": "python",
            "custom_field": "hello",
            "nested": {"anything": True},
            "features": {"ci": True, "pre_commit": True},
        }
        spec_path = tmp_path / "spec.json"
        spec_path.write_text(json.dumps(spec))

        target = tmp_path / "project"
        target.mkdir()

        _apply_pack(runner, spec_path, "base", target)
        assert (target / "CLAUDE.md").exists()
        assert _diff_pack(runner, spec_path, "base", target) == 0
