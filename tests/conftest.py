"""Shared test fixtures for nboot."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Create a minimal project directory for testing."""
    return tmp_path / "project"


@pytest.fixture
def minimal_spec() -> dict[str, Any]:
    """Minimal valid spec."""
    return {
        "name": "test-project",
        "language": "python",
        "python_version": "3.12",
        "structure": {"src_dir": "src/test_project", "test_dir": "tests"},
        "features": {"ci": True, "pre_commit": True},
    }


@pytest.fixture
def minimal_spec_file(tmp_path: Path, minimal_spec: dict[str, Any]) -> Path:
    """Write minimal spec to a file and return path."""
    spec_file = tmp_path / "project.json"
    spec_file.write_text(json.dumps(minimal_spec))
    return spec_file


@pytest.fixture
def minimal_manifest_dir(tmp_path: Path) -> Path:
    """Create a minimal template pack directory with manifest and one template."""
    pack_dir = tmp_path / "pack"
    pack_dir.mkdir()
    templates_dir = pack_dir / "templates"
    templates_dir.mkdir()

    manifest = {
        "name": "test-pack",
        "version": "0.1.0",
        "description": "Test pack",
        "templates": [
            {"src": "hello.txt.j2", "dest": "hello.txt"},
        ],
        "conditions": {},
        "loops": {},
        "hooks": [],
    }

    (pack_dir / "manifest.yaml").write_text(yaml.dump(manifest))
    (templates_dir / "hello.txt.j2").write_text("Hello {{ spec.name }}!\n")

    return pack_dir
