# ruff: noqa: RUF003
"""Adversarial tests: Full pipeline — hostile spec through render.

Hostile spec → sanitize → plan → render → clean output + warnings.
The pipeline must ALWAYS produce output. No exceptions.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pytest
import yaml

from navi_bootstrap.engine import plan, render_to_files
from navi_bootstrap.sanitize import sanitize_manifest, sanitize_spec


@pytest.fixture
def hostile_pack(tmp_path: Path) -> Path:
    """Create a minimal pack for rendering hostile specs through."""
    pack_dir = tmp_path / "pack"
    pack_dir.mkdir()
    templates_dir = pack_dir / "templates"
    templates_dir.mkdir()

    manifest = {
        "name": "test-pack",
        "version": "0.1.0",
        "description": "Test pack for adversarial pipeline",
        "templates": [
            {"src": "output.txt.j2", "dest": "output.txt"},
        ],
        "conditions": {},
        "loops": {},
        "hooks": [],
    }
    (pack_dir / "manifest.yaml").write_text(yaml.dump(manifest))
    (templates_dir / "output.txt.j2").write_text(
        "Project: {{ spec.name }}\nDesc: {{ spec.description | default('none') }}\n"
    )
    return pack_dir


class TestFullPipelineHostileSpec:
    """Hostile spec values flow through the full pipeline safely."""

    def test_cyrillic_name_renders_clean(
        self,
        hostile_pack: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        spec: dict[str, Any] = {
            "name": "n\u0430vi",  # Cyrillic а
            "language": "python",
            "description": "clean",
        }
        with caplog.at_level(logging.WARNING, logger="navi_bootstrap.sanitize"):
            spec = sanitize_spec(spec)

        manifest = yaml.safe_load((hostile_pack / "manifest.yaml").read_text())
        templates_dir = hostile_pack / "templates"
        render_plan = plan(manifest, spec, templates_dir)
        rendered = render_to_files(render_plan, spec, templates_dir)

        assert len(rendered) == 1
        assert "navi" in rendered[0].content
        assert "\u0430" not in rendered[0].content  # No Cyrillic in output

    def test_template_injection_neutralized_in_render(
        self,
        hostile_pack: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        spec: dict[str, Any] = {
            "name": "test",
            "language": "python",
            "description": "{{ config.SECRET_KEY }}",
        }
        with caplog.at_level(logging.WARNING, logger="navi_bootstrap.sanitize"):
            spec = sanitize_spec(spec)

        manifest = yaml.safe_load((hostile_pack / "manifest.yaml").read_text())
        templates_dir = hostile_pack / "templates"
        render_plan = plan(manifest, spec, templates_dir)
        rendered = render_to_files(render_plan, spec, templates_dir)

        assert len(rendered) == 1
        # The injected template was escaped, not evaluated — appears as literal text
        # with escaped delimiters, NOT as an evaluated Jinja2 expression
        assert "{{" not in rendered[0].content
        assert "}}" not in rendered[0].content

    def test_hostile_spec_fixture_full_pipeline(
        self,
        hostile_spec: dict,
        hostile_pack: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """The full hostile_spec fixture survives the pipeline."""
        with caplog.at_level(logging.WARNING, logger="navi_bootstrap.sanitize"):
            clean_spec = sanitize_spec(hostile_spec)

        manifest = yaml.safe_load((hostile_pack / "manifest.yaml").read_text())
        templates_dir = hostile_pack / "templates"
        render_plan = plan(manifest, clean_spec, templates_dir)
        rendered = render_to_files(render_plan, clean_spec, templates_dir)

        # Pipeline produced output (never errors)
        assert len(rendered) == 1
        assert rendered[0].content  # Non-empty output

        # Warnings were emitted (hostile input detected)
        assert caplog.text  # At least some warnings

    def test_hostile_manifest_dest_sanitized(
        self,
        hostile_manifest: dict,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Manifest with traversal dests is cleaned."""
        with caplog.at_level(logging.WARNING, logger="navi_bootstrap.sanitize"):
            clean_manifest = sanitize_manifest(hostile_manifest)

        for template_entry in clean_manifest["templates"]:
            dest = template_entry["dest"]
            assert ".." not in dest
            assert not dest.startswith("/")
            assert "\x00" not in dest


class TestHostileSpecFixture:
    """The hostile-spec.json fixture can be loaded and sanitized."""

    def test_fixture_file_loads(self) -> None:
        fixture_path = Path(__file__).parent / "fixtures" / "hostile-spec.json"
        spec = json.loads(fixture_path.read_text())
        assert spec["name"]  # Has a name field
        assert spec["language"]  # Has a language field

    def test_fixture_file_sanitizes_clean(self, caplog: pytest.LogCaptureFixture) -> None:
        fixture_path = Path(__file__).parent / "fixtures" / "hostile-spec.json"
        spec = json.loads(fixture_path.read_text())
        with caplog.at_level(logging.WARNING, logger="navi_bootstrap.sanitize"):
            result = sanitize_spec(spec)

        # Clean output produced
        assert result["name"]
        assert "\x00" not in json.dumps(result)

        # Warnings emitted (the fixture is hostile)
        assert caplog.text
