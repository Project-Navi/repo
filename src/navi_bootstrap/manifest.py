# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Project Navi

"""Manifest loading and validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import jsonschema
import yaml

SCHEMA_PATH = Path(__file__).parent.parent.parent / "schema" / "manifest-schema.yaml"


class ManifestError(Exception):
    """Raised when a manifest is invalid or cannot be loaded."""


def _load_schema() -> dict[str, Any]:
    """Load the YAML schema for manifest validation."""
    return yaml.safe_load(SCHEMA_PATH.read_text())


def validate_manifest(manifest: dict[str, Any]) -> None:
    """Validate a manifest dict against the schema. Raises ManifestError on failure."""
    schema = _load_schema()
    try:
        jsonschema.validate(instance=manifest, schema=schema)
    except jsonschema.ValidationError as e:
        raise ManifestError(f"Manifest validation failed: {e.message}") from e


def load_manifest(path: Path) -> dict[str, Any]:
    """Load and validate a manifest from a YAML file. Returns the manifest dict."""
    if not path.exists():
        raise ManifestError(f"Manifest file not found: {path}")
    try:
        manifest = yaml.safe_load(path.read_text())
    except yaml.YAMLError as e:
        raise ManifestError(f"Failed to parse manifest YAML: {e}") from e
    if not isinstance(manifest, dict):
        raise ManifestError("Manifest must be a YAML mapping")
    validate_manifest(manifest)
    return manifest
