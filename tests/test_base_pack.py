"""Integration tests for the base template pack."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from navi_bootstrap.engine import plan, render
from navi_bootstrap.manifest import load_manifest

PACK_DIR = Path(__file__).parent.parent / "packs" / "base"


@pytest.fixture
def base_spec() -> dict[str, Any]:
    """A spec that exercises the base pack fully."""
    return {
        "name": "arctl",
        "version": "1.2.0",
        "language": "python",
        "python_version": "3.9",
        "structure": {
            "src_dir": "arctl",
            "test_dir": "tests",
        },
        "dependencies": {
            "runtime": ["numpy"],
            "optional": {
                "verification": ["sentence-transformers"],
                "viz": ["matplotlib"],
            },
            "dev": [],
        },
        "features": {
            "ci": True,
            "pre_commit": True,
        },
        "recon": {
            "test_framework": "pytest",
            "test_count": 42,
            "python_test_versions": ["3.9", "3.10", "3.11", "3.12"],
            "existing_tools": {
                "ruff": False,
                "mypy": False,
                "bandit": False,
            },
        },
    }


@pytest.fixture
def fake_shas() -> dict[str, str]:
    return {
        "actions_checkout": "a" * 40,
        "harden_runner": "b" * 40,
        "actions_setup_python": "c" * 40,
    }


@pytest.fixture
def fake_versions() -> dict[str, str]:
    return {
        "actions_checkout": "v4.2.2",
        "harden_runner": "v2.10.4",
        "actions_setup_python": "v5.4.0",
    }


class TestBasePackManifest:
    def test_manifest_is_valid(self) -> None:
        manifest = load_manifest(PACK_DIR / "manifest.yaml")
        assert manifest["name"] == "base"

    def test_manifest_has_required_templates(self) -> None:
        manifest = load_manifest(PACK_DIR / "manifest.yaml")
        srcs = [t["src"] for t in manifest["templates"]]
        assert "pre-commit-config.yaml.j2" in srcs
        assert "dependabot.yml.j2" in srcs
        assert "CLAUDE.md.j2" in srcs
        assert "DEBT.md.j2" in srcs

    def test_manifest_has_action_shas(self) -> None:
        manifest = load_manifest(PACK_DIR / "manifest.yaml")
        names = [a["name"] for a in manifest.get("action_shas", [])]
        assert "actions_checkout" in names
        assert "harden_runner" in names


class TestBasePackRender:
    def test_renders_all_expected_files(
        self,
        base_spec: dict[str, Any],
        fake_shas: dict[str, str],
        fake_versions: dict[str, str],
        tmp_path: Path,
    ) -> None:
        manifest = load_manifest(PACK_DIR / "manifest.yaml")
        templates_dir = PACK_DIR / "templates"
        render_plan = plan(manifest, base_spec, templates_dir)
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        written = render(
            render_plan,
            base_spec,
            templates_dir,
            output_dir,
            mode="apply",
            action_shas=fake_shas,
            action_versions=fake_versions,
        )
        assert len(written) > 0

        # Check key files exist
        assert (output_dir / ".pre-commit-config.yaml").exists()
        assert (output_dir / ".github" / "dependabot.yml").exists()
        assert (output_dir / "CLAUDE.md").exists()
        assert (output_dir / "DEBT.md").exists()
        assert (output_dir / ".github" / "workflows" / "tests.yml").exists()

    def test_ci_workflow_uses_shas(
        self,
        base_spec: dict[str, Any],
        fake_shas: dict[str, str],
        fake_versions: dict[str, str],
        tmp_path: Path,
    ) -> None:
        manifest = load_manifest(PACK_DIR / "manifest.yaml")
        templates_dir = PACK_DIR / "templates"
        render_plan = plan(manifest, base_spec, templates_dir)
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        render(
            render_plan,
            base_spec,
            templates_dir,
            output_dir,
            mode="apply",
            action_shas=fake_shas,
            action_versions=fake_versions,
        )
        ci_content = (output_dir / ".github" / "workflows" / "tests.yml").read_text()
        assert fake_shas["actions_checkout"] in ci_content
        assert fake_shas["harden_runner"] in ci_content
        assert fake_shas["actions_setup_python"] in ci_content

    def test_pyproject_append_has_markers(
        self,
        base_spec: dict[str, Any],
        fake_shas: dict[str, str],
        fake_versions: dict[str, str],
        tmp_path: Path,
    ) -> None:
        manifest = load_manifest(PACK_DIR / "manifest.yaml")
        templates_dir = PACK_DIR / "templates"
        render_plan = plan(manifest, base_spec, templates_dir)
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        (output_dir / "pyproject.toml").write_text('[project]\nname = "arctl"\n')
        render(
            render_plan,
            base_spec,
            templates_dir,
            output_dir,
            mode="apply",
            action_shas=fake_shas,
            action_versions=fake_versions,
        )
        content = (output_dir / "pyproject.toml").read_text()
        assert "# --- nboot: base ---" in content
        assert "[tool.ruff]" in content
        assert "py39" in content  # target-version derived from python_version

    def test_ci_skipped_when_feature_false(
        self,
        base_spec: dict[str, Any],
        fake_shas: dict[str, str],
        fake_versions: dict[str, str],
        tmp_path: Path,
    ) -> None:
        base_spec["features"]["ci"] = False
        manifest = load_manifest(PACK_DIR / "manifest.yaml")
        templates_dir = PACK_DIR / "templates"
        render_plan = plan(manifest, base_spec, templates_dir)
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        render(
            render_plan,
            base_spec,
            templates_dir,
            output_dir,
            mode="apply",
            action_shas=fake_shas,
            action_versions=fake_versions,
        )
        assert not (output_dir / ".github" / "workflows" / "tests.yml").exists()

    def test_precommit_skipped_when_feature_false(
        self,
        base_spec: dict[str, Any],
        fake_shas: dict[str, str],
        fake_versions: dict[str, str],
        tmp_path: Path,
    ) -> None:
        base_spec["features"]["pre_commit"] = False
        manifest = load_manifest(PACK_DIR / "manifest.yaml")
        templates_dir = PACK_DIR / "templates"
        render_plan = plan(manifest, base_spec, templates_dir)
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        render(
            render_plan,
            base_spec,
            templates_dir,
            output_dir,
            mode="apply",
            action_shas=fake_shas,
            action_versions=fake_versions,
        )
        assert not (output_dir / ".pre-commit-config.yaml").exists()

    def test_claude_md_contains_project_info(
        self,
        base_spec: dict[str, Any],
        fake_shas: dict[str, str],
        fake_versions: dict[str, str],
        tmp_path: Path,
    ) -> None:
        manifest = load_manifest(PACK_DIR / "manifest.yaml")
        templates_dir = PACK_DIR / "templates"
        render_plan = plan(manifest, base_spec, templates_dir)
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        render(
            render_plan,
            base_spec,
            templates_dir,
            output_dir,
            mode="apply",
            action_shas=fake_shas,
            action_versions=fake_versions,
        )
        claude_content = (output_dir / "CLAUDE.md").read_text()
        assert "arctl" in claude_content
        assert "3.9" in claude_content
        assert "uv run pytest" in claude_content

    def test_mypy_overrides_for_optional_deps(
        self,
        base_spec: dict[str, Any],
        fake_shas: dict[str, str],
        fake_versions: dict[str, str],
        tmp_path: Path,
    ) -> None:
        manifest = load_manifest(PACK_DIR / "manifest.yaml")
        templates_dir = PACK_DIR / "templates"
        render_plan = plan(manifest, base_spec, templates_dir)
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        (output_dir / "pyproject.toml").write_text('[project]\nname = "arctl"\n')
        render(
            render_plan,
            base_spec,
            templates_dir,
            output_dir,
            mode="apply",
            action_shas=fake_shas,
            action_versions=fake_versions,
        )
        content = (output_dir / "pyproject.toml").read_text()
        assert "sentence_transformers" in content
        assert "ignore_missing_imports = true" in content

    def test_ci_uses_test_versions_from_recon(
        self,
        base_spec: dict[str, Any],
        fake_shas: dict[str, str],
        fake_versions: dict[str, str],
        tmp_path: Path,
    ) -> None:
        manifest = load_manifest(PACK_DIR / "manifest.yaml")
        templates_dir = PACK_DIR / "templates"
        render_plan = plan(manifest, base_spec, templates_dir)
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        render(
            render_plan,
            base_spec,
            templates_dir,
            output_dir,
            mode="apply",
            action_shas=fake_shas,
            action_versions=fake_versions,
        )
        ci_content = (output_dir / ".github" / "workflows" / "tests.yml").read_text()
        assert '"3.9"' in ci_content
        assert '"3.10"' in ci_content
        assert '"3.11"' in ci_content
        assert '"3.12"' in ci_content
