# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Project Navi

"""CLI integration tests for nboot diff command."""

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
def diff_pack(tmp_path: Path) -> Path:
    """Pack with one template for diff testing."""
    pack_dir = tmp_path / "pack"
    pack_dir.mkdir()
    templates_dir = pack_dir / "templates"
    templates_dir.mkdir()

    manifest = {
        "name": "diff-test-pack",
        "version": "0.1.0",
        "templates": [
            {"src": "readme.md.j2", "dest": "README.md"},
        ],
        "conditions": {},
        "loops": {},
        "hooks": [],
    }
    (pack_dir / "manifest.yaml").write_text(yaml.dump(manifest))
    (templates_dir / "readme.md.j2").write_text("# {{ spec.name }}\n\n{{ spec.description }}\n")
    return pack_dir


@pytest.fixture
def diff_spec_file(tmp_path: Path) -> Path:
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


class TestDiffCommand:
    def test_diff_shows_new_file(
        self, runner: CliRunner, diff_spec_file: Path, diff_pack: Path, tmp_path: Path
    ) -> None:
        target_dir = tmp_path / "target"
        target_dir.mkdir()

        result = runner.invoke(
            cli,
            [
                "diff",
                "--spec",
                str(diff_spec_file),
                "--pack",
                str(diff_pack),
                "--target",
                str(target_dir),
                "--skip-resolve",
            ],
        )
        assert result.exit_code == 1  # changes found
        assert "README.md" in result.output
        assert "+# my-project" in result.output

    def test_diff_no_changes_exit_zero(
        self, runner: CliRunner, diff_spec_file: Path, diff_pack: Path, tmp_path: Path
    ) -> None:
        target_dir = tmp_path / "target"
        target_dir.mkdir()
        # Write the exact content the template would produce
        (target_dir / "README.md").write_text("# my-project\n\nA test project\n")

        result = runner.invoke(
            cli,
            [
                "diff",
                "--spec",
                str(diff_spec_file),
                "--pack",
                str(diff_pack),
                "--target",
                str(target_dir),
                "--skip-resolve",
            ],
        )
        assert result.exit_code == 0
        assert "No changes" in result.output

    def test_diff_shows_changed_file(
        self, runner: CliRunner, diff_spec_file: Path, diff_pack: Path, tmp_path: Path
    ) -> None:
        target_dir = tmp_path / "target"
        target_dir.mkdir()
        (target_dir / "README.md").write_text("# old-name\n\nOld description\n")

        result = runner.invoke(
            cli,
            [
                "diff",
                "--spec",
                str(diff_spec_file),
                "--pack",
                str(diff_pack),
                "--target",
                str(target_dir),
                "--skip-resolve",
            ],
        )
        assert result.exit_code == 1
        assert "-# old-name" in result.output
        assert "+# my-project" in result.output

    def test_diff_summary_line(
        self, runner: CliRunner, diff_spec_file: Path, diff_pack: Path, tmp_path: Path
    ) -> None:
        target_dir = tmp_path / "target"
        target_dir.mkdir()

        result = runner.invoke(
            cli,
            [
                "diff",
                "--spec",
                str(diff_spec_file),
                "--pack",
                str(diff_pack),
                "--target",
                str(target_dir),
                "--skip-resolve",
            ],
        )
        assert result.exit_code == 1
        # Should show a summary of how many files would change
        assert "1 file" in result.output
