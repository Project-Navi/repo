"""Tests for H2: spec.name as default output dir must reject unsafe names."""

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
def simple_pack(tmp_path: Path) -> Path:
    """Minimal pack for testing CLI behavior."""
    pack_dir = tmp_path / "pack"
    pack_dir.mkdir()
    templates_dir = pack_dir / "templates"
    templates_dir.mkdir()
    manifest = {
        "name": "h2-test-pack",
        "version": "0.1.0",
        "templates": [{"src": "readme.md.j2", "dest": "README.md"}],
    }
    (pack_dir / "manifest.yaml").write_text(yaml.dump(manifest))
    (templates_dir / "readme.md.j2").write_text("# {{ spec.name }}\n")
    return pack_dir


def _spec_file(tmp_path: Path, name: str) -> Path:
    """Write a spec with the given name and return its path."""
    spec = {"name": name, "language": "python", "python_version": "3.12", "features": {}}
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(spec))
    return path


class TestRenderRejectsUnsafeNames:
    """render command rejects dangerous spec.name when --out is not provided."""

    @pytest.mark.parametrize(
        "name",
        [
            ".",  # sanitized to "" (empty)
            "..",  # sanitized to "" (empty)
            "foo/bar",  # forward slash preserved
            "foo\\bar",  # backslash preserved
            "name/../../etc",  # sanitized to "name/etc" (still has slash)
        ],
    )
    def test_rejects_unsafe_names_without_out(
        self, runner: CliRunner, simple_pack: Path, tmp_path: Path, name: str
    ) -> None:
        spec_file = _spec_file(tmp_path, name)
        result = runner.invoke(
            cli,
            ["render", "--spec", str(spec_file), "--pack", str(simple_pack), "--skip-resolve"],
        )
        assert result.exit_code != 0
        assert "--out" in result.output

    @pytest.mark.parametrize(
        "name",
        [
            ".",
            "..",
            "foo/bar",
        ],
    )
    def test_unsafe_name_works_with_explicit_out(
        self, runner: CliRunner, simple_pack: Path, tmp_path: Path, name: str
    ) -> None:
        """Explicit --out bypasses the name check."""
        spec_file = _spec_file(tmp_path, name)
        out_dir = tmp_path / "safe-output"
        result = runner.invoke(
            cli,
            [
                "render",
                "--spec",
                str(spec_file),
                "--pack",
                str(simple_pack),
                "--out",
                str(out_dir),
                "--skip-resolve",
            ],
        )
        assert result.exit_code == 0
        assert (out_dir / "README.md").exists()

    def test_safe_name_works_without_out(
        self,
        runner: CliRunner,
        simple_pack: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        spec_file = _spec_file(tmp_path, "my-project")
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(
            cli,
            [
                "render",
                "--spec",
                str(spec_file),
                "--pack",
                str(simple_pack),
                "--skip-resolve",
            ],
        )
        assert result.exit_code == 0
        assert (tmp_path / "my-project" / "README.md").exists()
