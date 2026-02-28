"""Tests for manifest loading and validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from navi_bootstrap.manifest import ManifestError, load_manifest, validate_manifest


@pytest.fixture
def valid_manifest() -> dict[str, Any]:
    return {
        "name": "test-pack",
        "version": "0.1.0",
        "templates": [{"src": "hello.j2", "dest": "hello.txt"}],
    }


class TestValidateManifest:
    def test_valid_manifest(self, valid_manifest: dict[str, Any]) -> None:
        validate_manifest(valid_manifest)  # should not raise

    def test_missing_name_raises(self) -> None:
        with pytest.raises(ManifestError, match="name"):
            validate_manifest({"version": "0.1.0", "templates": []})

    def test_missing_templates_raises(self) -> None:
        with pytest.raises(ManifestError, match="templates"):
            validate_manifest({"name": "test", "version": "0.1.0"})

    def test_template_missing_src_raises(self) -> None:
        with pytest.raises(ManifestError):
            validate_manifest(
                {
                    "name": "test",
                    "version": "0.1.0",
                    "templates": [{"dest": "out.txt"}],
                }
            )

    def test_invalid_mode_raises(self) -> None:
        with pytest.raises(ManifestError):
            validate_manifest(
                {
                    "name": "test",
                    "version": "0.1.0",
                    "templates": [{"src": "a.j2", "dest": "a.txt", "mode": "overwrite"}],
                }
            )

    def test_agent_fields_accepted(self, valid_manifest: dict[str, Any]) -> None:
        valid_manifest["dependencies"] = ["base"]
        valid_manifest["action_shas"] = [
            {"name": "checkout", "repo": "actions/checkout", "tag": "v4"}
        ]
        valid_manifest["decisions"] = [{"question": "test?", "context": "ctx"}]
        validate_manifest(valid_manifest)  # should not raise

    def test_conditions_accepted(self, valid_manifest: dict[str, Any]) -> None:
        valid_manifest["conditions"] = {"ci.yml.j2": "spec.features.ci"}
        validate_manifest(valid_manifest)  # should not raise

    def test_loops_accepted(self, valid_manifest: dict[str, Any]) -> None:
        valid_manifest["loops"] = {"module.py.j2": {"over": "spec.modules", "as": "module"}}
        validate_manifest(valid_manifest)  # should not raise


class TestLoadManifest:
    def test_load_from_file(self, tmp_path: Path, valid_manifest: dict[str, Any]) -> None:
        manifest_file = tmp_path / "manifest.yaml"
        manifest_file.write_text(yaml.dump(valid_manifest))
        loaded = load_manifest(manifest_file)
        assert loaded["name"] == "test-pack"

    def test_load_nonexistent_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ManifestError, match="not found"):
            load_manifest(tmp_path / "missing.yaml")

    def test_load_invalid_yaml_raises(self, tmp_path: Path) -> None:
        bad_file = tmp_path / "bad.yaml"
        bad_file.write_text(": : : not yaml [[[")
        with pytest.raises(ManifestError, match="parse"):
            load_manifest(bad_file)

    def test_load_validates_content(self, tmp_path: Path) -> None:
        manifest_file = tmp_path / "manifest.yaml"
        manifest_file.write_text(yaml.dump({"name": "test"}))
        with pytest.raises(ManifestError):
            load_manifest(manifest_file)
