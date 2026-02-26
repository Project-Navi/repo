"""Tests for --trust flag: hooks and validations require explicit opt-in."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from navi_bootstrap.cli import cli


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def pack_with_hooks(tmp_path: Path) -> Path:
    """Pack with hooks that create marker files when executed."""
    pack_dir = tmp_path / "pack"
    pack_dir.mkdir()
    templates_dir = pack_dir / "templates"
    templates_dir.mkdir()

    manifest = {
        "name": "trust-test-pack",
        "version": "0.1.0",
        "templates": [
            {"src": "readme.md.j2", "dest": "README.md"},
        ],
        "hooks": ["touch hook_ran.marker"],
    }
    (pack_dir / "manifest.yaml").write_text(yaml.dump(manifest))
    (templates_dir / "readme.md.j2").write_text("# {{ spec.name }}\n")
    return pack_dir


@pytest.fixture
def pack_with_validations(tmp_path: Path) -> Path:
    """Pack with validations and hooks that create marker files."""
    pack_dir = tmp_path / "pack-val"
    pack_dir.mkdir()
    templates_dir = pack_dir / "templates"
    templates_dir.mkdir()

    manifest = {
        "name": "trust-val-pack",
        "version": "0.1.0",
        "templates": [
            {"src": "readme.md.j2", "dest": "README.md"},
        ],
        "validation": [
            {"description": "check marker", "command": "touch validation_ran.marker"},
        ],
        "hooks": ["touch hook_ran.marker"],
    }
    (pack_dir / "manifest.yaml").write_text(yaml.dump(manifest))
    (templates_dir / "readme.md.j2").write_text("# {{ spec.name }}\n")
    return pack_dir


@pytest.fixture
def spec_file(tmp_path: Path) -> Path:
    spec = {
        "name": "trust-test",
        "language": "python",
        "python_version": "3.12",
        "features": {},
    }
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(spec))
    return path


class TestRenderTrust:
    """render command: hooks require --trust."""

    def test_render_without_trust_skips_hooks(
        self, runner: CliRunner, spec_file: Path, pack_with_hooks: Path, tmp_path: Path
    ) -> None:
        out_dir = tmp_path / "output"
        result = runner.invoke(
            cli,
            [
                "render",
                "--spec",
                str(spec_file),
                "--pack",
                str(pack_with_hooks),
                "--out",
                str(out_dir),
                "--skip-resolve",
            ],
        )
        assert result.exit_code == 0
        # Files should still be rendered
        assert (out_dir / "README.md").exists()
        # Hook should NOT have run
        assert not (out_dir / "hook_ran.marker").exists()

    def test_render_without_trust_prints_skipped_hooks(
        self, runner: CliRunner, spec_file: Path, pack_with_hooks: Path, tmp_path: Path
    ) -> None:
        out_dir = tmp_path / "output"
        result = runner.invoke(
            cli,
            [
                "render",
                "--spec",
                str(spec_file),
                "--pack",
                str(pack_with_hooks),
                "--out",
                str(out_dir),
                "--skip-resolve",
            ],
        )
        assert result.exit_code == 0
        assert "touch hook_ran.marker" in result.output
        assert "--trust" in result.output

    def test_render_with_trust_executes_hooks(
        self, runner: CliRunner, spec_file: Path, pack_with_hooks: Path, tmp_path: Path
    ) -> None:
        out_dir = tmp_path / "output"
        result = runner.invoke(
            cli,
            [
                "render",
                "--spec",
                str(spec_file),
                "--pack",
                str(pack_with_hooks),
                "--out",
                str(out_dir),
                "--skip-resolve",
                "--trust",
            ],
        )
        assert result.exit_code == 0
        assert (out_dir / "hook_ran.marker").exists()

    def test_render_with_trust_shows_hook_status(
        self, runner: CliRunner, spec_file: Path, pack_with_hooks: Path, tmp_path: Path
    ) -> None:
        out_dir = tmp_path / "output"
        result = runner.invoke(
            cli,
            [
                "render",
                "--spec",
                str(spec_file),
                "--pack",
                str(pack_with_hooks),
                "--out",
                str(out_dir),
                "--skip-resolve",
                "--trust",
            ],
        )
        assert result.exit_code == 0
        assert "[OK]" in result.output


class TestApplyTrust:
    """apply command: hooks and validations require --trust."""

    def test_apply_without_trust_skips_both(
        self, runner: CliRunner, spec_file: Path, pack_with_validations: Path, tmp_path: Path
    ) -> None:
        target = tmp_path / "target"
        target.mkdir()
        result = runner.invoke(
            cli,
            [
                "apply",
                "--spec",
                str(spec_file),
                "--pack",
                str(pack_with_validations),
                "--target",
                str(target),
                "--skip-resolve",
            ],
        )
        assert result.exit_code == 0
        assert (target / "README.md").exists()
        assert not (target / "hook_ran.marker").exists()
        assert not (target / "validation_ran.marker").exists()

    def test_apply_without_trust_prints_skipped_commands(
        self, runner: CliRunner, spec_file: Path, pack_with_validations: Path, tmp_path: Path
    ) -> None:
        target = tmp_path / "target"
        target.mkdir()
        result = runner.invoke(
            cli,
            [
                "apply",
                "--spec",
                str(spec_file),
                "--pack",
                str(pack_with_validations),
                "--target",
                str(target),
                "--skip-resolve",
            ],
        )
        assert result.exit_code == 0
        assert "touch hook_ran.marker" in result.output
        assert "touch validation_ran.marker" in result.output
        assert "--trust" in result.output

    def test_apply_with_trust_executes_both(
        self, runner: CliRunner, spec_file: Path, pack_with_validations: Path, tmp_path: Path
    ) -> None:
        target = tmp_path / "target"
        target.mkdir()
        result = runner.invoke(
            cli,
            [
                "apply",
                "--spec",
                str(spec_file),
                "--pack",
                str(pack_with_validations),
                "--target",
                str(target),
                "--skip-resolve",
                "--trust",
            ],
        )
        assert result.exit_code == 0
        assert (target / "hook_ran.marker").exists()
        assert (target / "validation_ran.marker").exists()

    def test_apply_with_trust_shows_validation_status(
        self, runner: CliRunner, spec_file: Path, pack_with_validations: Path, tmp_path: Path
    ) -> None:
        target = tmp_path / "target"
        target.mkdir()
        result = runner.invoke(
            cli,
            [
                "apply",
                "--spec",
                str(spec_file),
                "--pack",
                str(pack_with_validations),
                "--target",
                str(target),
                "--skip-resolve",
                "--trust",
            ],
        )
        assert result.exit_code == 0
        assert "[PASS]" in result.output
        assert "[OK]" in result.output


class TestTrustNoOp:
    """--trust has no effect when manifest has no hooks/validations."""

    def test_render_no_hooks_no_trust_message(
        self, runner: CliRunner, spec_file: Path, tmp_path: Path
    ) -> None:
        pack_dir = tmp_path / "clean-pack"
        pack_dir.mkdir()
        templates_dir = pack_dir / "templates"
        templates_dir.mkdir()
        manifest = {
            "name": "clean-pack",
            "version": "0.1.0",
            "templates": [{"src": "r.j2", "dest": "r.md"}],
        }
        (pack_dir / "manifest.yaml").write_text(yaml.dump(manifest))
        (templates_dir / "r.j2").write_text("# hi\n")

        out_dir = tmp_path / "output"
        result = runner.invoke(
            cli,
            [
                "render",
                "--spec",
                str(spec_file),
                "--pack",
                str(pack_dir),
                "--out",
                str(out_dir),
                "--skip-resolve",
            ],
        )
        assert result.exit_code == 0
        assert "--trust" not in result.output
