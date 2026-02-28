# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Project Navi

"""Tests for .secrets.baseline generation in base pack.

GPT external review found: base pack pre-commit requires .secrets.baseline
but the pack doesn't generate it. Target repos will fail pre-commit.
"""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from navi_bootstrap.cli import cli

PACKS_DIR = Path(__file__).parent.parent / "packs"


class TestSecretsBaseline:
    """Base pack must generate .secrets.baseline for detect-secrets pre-commit hook."""

    def test_base_pack_generates_secrets_baseline(self, tmp_path: Path) -> None:
        """Apply base pack → .secrets.baseline must exist."""
        spec = {
            "name": "test-project",
            "language": "python",
            "python_version": "3.12",
            "structure": {"src_dir": "src/test_project", "test_dir": "tests"},
            "features": {"ci": True, "pre_commit": True},
        }
        spec_path = tmp_path / "spec.json"
        spec_path.write_text(json.dumps(spec))

        target = tmp_path / "project"
        target.mkdir()

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "apply",
                "--spec",
                str(spec_path),
                "--pack",
                str(PACKS_DIR / "base"),
                "--target",
                str(target),
                "--skip-resolve",
            ],
        )
        assert result.exit_code == 0, f"apply failed: {result.output}"
        assert (target / ".secrets.baseline").exists()

    def test_secrets_baseline_is_valid_json(self, tmp_path: Path) -> None:
        """Generated .secrets.baseline must be valid JSON with required keys."""
        spec = {
            "name": "test-project",
            "language": "python",
            "python_version": "3.12",
            "structure": {"src_dir": "src/test_project", "test_dir": "tests"},
            "features": {"ci": True, "pre_commit": True},
        }
        spec_path = tmp_path / "spec.json"
        spec_path.write_text(json.dumps(spec))

        target = tmp_path / "project"
        target.mkdir()

        runner = CliRunner()
        runner.invoke(
            cli,
            [
                "apply",
                "--spec",
                str(spec_path),
                "--pack",
                str(PACKS_DIR / "base"),
                "--target",
                str(target),
                "--skip-resolve",
            ],
        )

        baseline = json.loads((target / ".secrets.baseline").read_text())
        assert "version" in baseline
        assert "plugins_used" in baseline
        assert "results" in baseline
        assert isinstance(baseline["results"], dict)
        assert len(baseline["results"]) == 0  # empty baseline — no pre-existing secrets
