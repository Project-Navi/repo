"""Tests for the engine plan and render stages."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from navi_bootstrap.engine import plan, render

# --- Fixtures ---


@pytest.fixture
def pack_with_condition(tmp_path: Path) -> Path:
    """Pack with a conditional template."""
    pack_dir = tmp_path / "pack"
    pack_dir.mkdir()
    templates_dir = pack_dir / "templates"
    templates_dir.mkdir()

    manifest = {
        "name": "test-pack",
        "version": "0.1.0",
        "templates": [
            {"src": "always.txt.j2", "dest": "always.txt"},
            {"src": "conditional.txt.j2", "dest": "conditional.txt"},
        ],
        "conditions": {"conditional.txt.j2": "spec.features.ci"},
        "loops": {},
        "hooks": [],
    }
    (pack_dir / "manifest.yaml").write_text(yaml.dump(manifest))
    (templates_dir / "always.txt.j2").write_text("Always: {{ spec.name }}\n")
    (templates_dir / "conditional.txt.j2").write_text("CI: {{ spec.name }}\n")
    return pack_dir


@pytest.fixture
def pack_with_loop(tmp_path: Path) -> Path:
    """Pack with a looped template."""
    pack_dir = tmp_path / "pack"
    pack_dir.mkdir()
    templates_dir = pack_dir / "templates"
    templates_dir.mkdir()

    manifest = {
        "name": "test-pack",
        "version": "0.1.0",
        "templates": [
            {"src": "module.py.j2", "dest": "src/{{ item.name }}.py"},
        ],
        "conditions": {},
        "loops": {"module.py.j2": {"over": "spec.modules", "as": "item"}},
        "hooks": [],
    }
    (pack_dir / "manifest.yaml").write_text(yaml.dump(manifest))
    (templates_dir / "module.py.j2").write_text(
        '"""{{ item.name }}: {{ item.description }}"""\n'
    )
    return pack_dir


@pytest.fixture
def pack_with_append(tmp_path: Path) -> Path:
    """Pack with an append-mode template."""
    pack_dir = tmp_path / "pack"
    pack_dir.mkdir()
    templates_dir = pack_dir / "templates"
    templates_dir.mkdir()

    manifest = {
        "name": "test-pack",
        "version": "0.1.0",
        "templates": [
            {"src": "config.toml.j2", "dest": "pyproject.toml", "mode": "append"},
        ],
        "conditions": {},
        "loops": {},
        "hooks": [],
    }
    (pack_dir / "manifest.yaml").write_text(yaml.dump(manifest))
    (templates_dir / "config.toml.j2").write_text("[tool.ruff]\nline-length = 100\n")
    return pack_dir


@pytest.fixture
def spec_with_modules() -> dict[str, Any]:
    return {
        "name": "test-project",
        "language": "python",
        "modules": [
            {"name": "api", "description": "REST endpoints"},
            {"name": "models", "description": "Data models"},
        ],
        "features": {"ci": True},
    }


# --- Plan tests ---


class TestPlan:
    def test_plan_includes_unconditional(
        self, pack_with_condition: Path, minimal_spec: dict[str, Any]
    ) -> None:
        manifest = yaml.safe_load((pack_with_condition / "manifest.yaml").read_text())
        result = plan(manifest, minimal_spec, pack_with_condition / "templates")
        dest_paths = [e.dest for e in result.entries]
        assert "always.txt" in dest_paths

    def test_plan_includes_true_condition(
        self, pack_with_condition: Path, minimal_spec: dict[str, Any]
    ) -> None:
        manifest = yaml.safe_load((pack_with_condition / "manifest.yaml").read_text())
        result = plan(manifest, minimal_spec, pack_with_condition / "templates")
        dest_paths = [e.dest for e in result.entries]
        assert "conditional.txt" in dest_paths

    def test_plan_skips_false_condition(
        self, pack_with_condition: Path, minimal_spec: dict[str, Any]
    ) -> None:
        minimal_spec["features"]["ci"] = False
        manifest = yaml.safe_load((pack_with_condition / "manifest.yaml").read_text())
        result = plan(manifest, minimal_spec, pack_with_condition / "templates")
        dest_paths = [e.dest for e in result.entries]
        assert "conditional.txt" not in dest_paths

    def test_plan_expands_loops(
        self, pack_with_loop: Path, spec_with_modules: dict[str, Any]
    ) -> None:
        manifest = yaml.safe_load((pack_with_loop / "manifest.yaml").read_text())
        result = plan(manifest, spec_with_modules, pack_with_loop / "templates")
        dest_paths = [e.dest for e in result.entries]
        assert "src/api.py" in dest_paths
        assert "src/models.py" in dest_paths

    def test_plan_preserves_mode(
        self, pack_with_append: Path, minimal_spec: dict[str, Any]
    ) -> None:
        manifest = yaml.safe_load((pack_with_append / "manifest.yaml").read_text())
        result = plan(manifest, minimal_spec, pack_with_append / "templates")
        assert result.entries[0].mode == "append"


# --- Render tests ---


class TestRender:
    def test_render_creates_files(
        self, minimal_manifest_dir: Path, minimal_spec: dict[str, Any], tmp_path: Path
    ) -> None:
        manifest = yaml.safe_load((minimal_manifest_dir / "manifest.yaml").read_text())
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        render_plan = plan(manifest, minimal_spec, minimal_manifest_dir / "templates")
        render(render_plan, minimal_spec, minimal_manifest_dir / "templates", output_dir)
        assert (output_dir / "hello.txt").exists()
        assert "test-project" in (output_dir / "hello.txt").read_text()

    def test_render_loop_creates_multiple_files(
        self, pack_with_loop: Path, spec_with_modules: dict[str, Any], tmp_path: Path
    ) -> None:
        manifest = yaml.safe_load((pack_with_loop / "manifest.yaml").read_text())
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        render_plan = plan(manifest, spec_with_modules, pack_with_loop / "templates")
        render(render_plan, spec_with_modules, pack_with_loop / "templates", output_dir)
        api_file = output_dir / "src" / "api.py"
        assert api_file.exists()
        assert "REST endpoints" in api_file.read_text()

    def test_render_append_mode_adds_markers(
        self, pack_with_append: Path, minimal_spec: dict[str, Any], tmp_path: Path
    ) -> None:
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        (output_dir / "pyproject.toml").write_text('[project]\nname = "existing"\n')

        manifest = yaml.safe_load((pack_with_append / "manifest.yaml").read_text())
        render_plan = plan(manifest, minimal_spec, pack_with_append / "templates")
        render(render_plan, minimal_spec, pack_with_append / "templates", output_dir)
        content = (output_dir / "pyproject.toml").read_text()
        assert "# --- nboot: test-pack ---" in content
        assert "# --- end nboot: test-pack ---" in content
        assert '[project]\nname = "existing"' in content
        assert "line-length = 100" in content

    def test_render_append_mode_replaces_existing_markers(
        self, pack_with_append: Path, minimal_spec: dict[str, Any], tmp_path: Path
    ) -> None:
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        (output_dir / "pyproject.toml").write_text(
            '[project]\nname = "existing"\n'
            "# --- nboot: test-pack ---\n"
            "old content\n"
            "# --- end nboot: test-pack ---\n"
        )

        manifest = yaml.safe_load((pack_with_append / "manifest.yaml").read_text())
        render_plan = plan(manifest, minimal_spec, pack_with_append / "templates")
        render(render_plan, minimal_spec, pack_with_append / "templates", output_dir)
        content = (output_dir / "pyproject.toml").read_text()
        assert "old content" not in content
        assert "line-length = 100" in content
        assert content.count("# --- nboot: test-pack ---") == 1

    def test_render_greenfield_fails_if_file_exists(
        self, minimal_manifest_dir: Path, minimal_spec: dict[str, Any], tmp_path: Path
    ) -> None:
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        (output_dir / "hello.txt").write_text("already here")

        manifest = yaml.safe_load((minimal_manifest_dir / "manifest.yaml").read_text())
        render_plan = plan(manifest, minimal_spec, minimal_manifest_dir / "templates")
        with pytest.raises(FileExistsError):
            render(
                render_plan,
                minimal_spec,
                minimal_manifest_dir / "templates",
                output_dir,
                mode="greenfield",
            )

    def test_render_apply_creates_new_files(
        self, minimal_manifest_dir: Path, minimal_spec: dict[str, Any], tmp_path: Path
    ) -> None:
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        manifest = yaml.safe_load((minimal_manifest_dir / "manifest.yaml").read_text())
        render_plan = plan(manifest, minimal_spec, minimal_manifest_dir / "templates")
        render(
            render_plan,
            minimal_spec,
            minimal_manifest_dir / "templates",
            output_dir,
            mode="apply",
        )
        assert (output_dir / "hello.txt").exists()
