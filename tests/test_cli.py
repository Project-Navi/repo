"""Tests for the nboot CLI."""

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
def full_pack(tmp_path: Path) -> Path:
    """A complete pack for CLI integration tests."""
    pack_dir = tmp_path / "pack"
    pack_dir.mkdir()
    templates_dir = pack_dir / "templates"
    templates_dir.mkdir()

    manifest = {
        "name": "cli-test-pack",
        "version": "0.1.0",
        "templates": [
            {"src": "readme.md.j2", "dest": "README.md"},
        ],
        "conditions": {},
        "loops": {},
        "hooks": [],
    }
    (pack_dir / "manifest.yaml").write_text(yaml.dump(manifest))
    (templates_dir / "readme.md.j2").write_text(
        "# {{ spec.name }}\n\n{{ spec.description }}\n"
    )
    return pack_dir


@pytest.fixture
def spec_file(tmp_path: Path) -> Path:
    spec = {
        "name": "my-project",
        "language": "python",
        "description": "A test project",
        "python_version": "3.12",
        "features": {},
    }
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(spec))
    return path


class TestValidateCommand:
    def test_validate_valid_spec(self, runner: CliRunner, spec_file: Path) -> None:
        result = runner.invoke(cli, ["validate", "--spec", str(spec_file)])
        assert result.exit_code == 0
        assert "valid" in result.output.lower()

    def test_validate_invalid_spec(self, runner: CliRunner, tmp_path: Path) -> None:
        bad_spec = tmp_path / "bad.json"
        bad_spec.write_text(json.dumps({"not": "valid"}))
        result = runner.invoke(cli, ["validate", "--spec", str(bad_spec)])
        assert result.exit_code != 0

    def test_validate_with_pack(
        self, runner: CliRunner, spec_file: Path, full_pack: Path
    ) -> None:
        result = runner.invoke(
            cli, ["validate", "--spec", str(spec_file), "--pack", str(full_pack)]
        )
        assert result.exit_code == 0


class TestRenderCommand:
    def test_render_creates_output(
        self, runner: CliRunner, spec_file: Path, full_pack: Path, tmp_path: Path
    ) -> None:
        out_dir = tmp_path / "output"
        result = runner.invoke(
            cli,
            [
                "render",
                "--spec", str(spec_file),
                "--pack", str(full_pack),
                "--out", str(out_dir),
                "--skip-resolve",
            ],
        )
        assert result.exit_code == 0, result.output
        assert (out_dir / "README.md").exists()
        assert "my-project" in (out_dir / "README.md").read_text()

    def test_render_dry_run(
        self, runner: CliRunner, spec_file: Path, full_pack: Path, tmp_path: Path
    ) -> None:
        out_dir = tmp_path / "output"
        result = runner.invoke(
            cli,
            [
                "render",
                "--spec", str(spec_file),
                "--pack", str(full_pack),
                "--out", str(out_dir),
                "--dry-run",
            ],
        )
        assert result.exit_code == 0
        assert not out_dir.exists() or not (out_dir / "README.md").exists()

    def test_render_fails_if_file_exists(
        self, runner: CliRunner, spec_file: Path, full_pack: Path, tmp_path: Path
    ) -> None:
        out_dir = tmp_path / "output"
        out_dir.mkdir()
        (out_dir / "README.md").write_text("existing")
        result = runner.invoke(
            cli,
            [
                "render",
                "--spec", str(spec_file),
                "--pack", str(full_pack),
                "--out", str(out_dir),
                "--skip-resolve",
            ],
        )
        assert result.exit_code != 0


class TestApplyCommand:
    def test_apply_creates_files(
        self, runner: CliRunner, spec_file: Path, full_pack: Path, tmp_path: Path
    ) -> None:
        target_dir = tmp_path / "target"
        target_dir.mkdir()
        result = runner.invoke(
            cli,
            [
                "apply",
                "--spec", str(spec_file),
                "--pack", str(full_pack),
                "--target", str(target_dir),
                "--skip-resolve",
            ],
        )
        assert result.exit_code == 0, result.output
        assert (target_dir / "README.md").exists()

    def test_apply_dry_run(
        self, runner: CliRunner, spec_file: Path, full_pack: Path, tmp_path: Path
    ) -> None:
        target_dir = tmp_path / "target"
        target_dir.mkdir()
        result = runner.invoke(
            cli,
            [
                "apply",
                "--spec", str(spec_file),
                "--pack", str(full_pack),
                "--target", str(target_dir),
                "--dry-run",
            ],
        )
        assert result.exit_code == 0
        assert not (target_dir / "README.md").exists()
