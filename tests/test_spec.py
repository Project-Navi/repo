"""Tests for spec loading and validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from navi_bootstrap.spec import SpecError, load_spec, validate_spec


class TestValidateSpec:
    def test_valid_minimal_spec(self, minimal_spec: dict[str, Any]) -> None:
        validate_spec(minimal_spec)  # should not raise

    def test_missing_name_raises(self) -> None:
        with pytest.raises(SpecError, match="name"):
            validate_spec({"language": "python"})

    def test_missing_language_raises(self) -> None:
        with pytest.raises(SpecError, match="language"):
            validate_spec({"name": "test"})

    def test_invalid_language_raises(self) -> None:
        with pytest.raises(SpecError):
            validate_spec({"name": "test", "language": "cobol"})

    def test_extra_fields_allowed(self, minimal_spec: dict[str, Any]) -> None:
        minimal_spec["custom_field"] = "custom_value"
        validate_spec(minimal_spec)  # should not raise

    def test_features_must_be_booleans(self, minimal_spec: dict[str, Any]) -> None:
        minimal_spec["features"] = {"ci": "yes"}
        with pytest.raises(SpecError):
            validate_spec(minimal_spec)

    def test_recon_section_accepted(self, minimal_spec: dict[str, Any]) -> None:
        minimal_spec["recon"] = {"test_framework": "pytest", "test_count": 42}
        validate_spec(minimal_spec)  # should not raise

    @pytest.mark.parametrize(
        "spdx_id", ["MIT", "Apache-2.0", "GPL-3.0-only", "BSD-3-Clause", "0BSD"]
    )
    def test_valid_spdx_license_accepted(self, minimal_spec: dict[str, Any], spdx_id: str) -> None:
        minimal_spec["license"] = spdx_id
        validate_spec(minimal_spec)  # should not raise

    @pytest.mark.parametrize(
        "bad_license",
        ["MIT License", " MIT", "", "MIT\x00", "MIT\u200b"],
    )
    def test_invalid_license_string_rejected(
        self, minimal_spec: dict[str, Any], bad_license: str
    ) -> None:
        minimal_spec["license"] = bad_license
        with pytest.raises(SpecError):
            validate_spec(minimal_spec)


class TestLoadSpec:
    def test_load_from_file(self, tmp_path: Path, minimal_spec: dict[str, Any]) -> None:
        spec_file = tmp_path / "spec.json"
        spec_file.write_text(json.dumps(minimal_spec))
        loaded = load_spec(spec_file)
        assert loaded["name"] == "test-project"

    def test_load_nonexistent_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(SpecError, match="not found"):
            load_spec(tmp_path / "missing.json")

    def test_load_invalid_json_raises(self, tmp_path: Path) -> None:
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("{not json")
        with pytest.raises(SpecError, match="parse"):
            load_spec(bad_file)

    def test_load_validates_content(self, tmp_path: Path) -> None:
        spec_file = tmp_path / "spec.json"
        spec_file.write_text(json.dumps({"language": "python"}))
        with pytest.raises(SpecError):
            load_spec(spec_file)
