# nboot Engine + Base Pack Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the nboot rendering engine (~500-600 lines) and the base template pack — the two deliverables that make the system usable.

**Architecture:** Six-stage pipeline (Resolve → Validate → Plan → Render → Validate Results → Hooks) spread across 7 modules. The engine is deterministic: same spec + same pack = same output. Template packs are self-contained directories with a manifest.yaml and Jinja2 templates. Two modes: greenfield (render) and apply (append with marker blocks).

**Tech Stack:** Python 3.12+, Click (CLI), Jinja2 (templates), PyYAML (manifests), jsonschema (spec validation), uv (package management), pytest (testing)

---

## Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `src/navi_bootstrap/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `schema/spec-schema.json`
- Create: `schema/manifest-schema.yaml`

**Step 1: Create pyproject.toml**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "navi-bootstrap"
version = "0.1.0"
description = "Jinja2 rendering engine and template packs for bootstrapping projects to navi-os-grade posture"
readme = "README.md"
license = "MIT"
requires-python = ">=3.12"
authors = [
    { name = "Nelson Spencer" }
]

dependencies = [
    "click>=8.1.0",
    "jinja2>=3.1.0",
    "pyyaml>=6.0",
    "jsonschema>=4.20.0",
]

[project.scripts]
nboot = "navi_bootstrap.cli:cli"

[dependency-groups]
dev = [
    "pytest>=8.0.0",
    "pytest-cov>=5.0.0",
    "ruff>=0.9.0",
    "mypy>=1.8.0",
]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP", "B", "RUF", "C4"]
ignore = ["E501"]

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.mypy]
python_version = "3.12"
warn_unused_configs = true
disallow_untyped_defs = true
check_untyped_defs = true
warn_redundant_casts = true
warn_unused_ignores = true
```

**Step 2: Create package init**

```python
# src/navi_bootstrap/__init__.py
"""navi-bootstrap: Jinja2 rendering engine and template packs."""

__version__ = "0.1.0"
```

**Step 3: Create JSON Schema for spec validation**

`schema/spec-schema.json` — validates the project.json spec. Requires `name` and `language`, everything else optional.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "nboot Project Spec",
  "type": "object",
  "required": ["name", "language"],
  "properties": {
    "name": { "type": "string", "minLength": 1 },
    "version": { "type": "string" },
    "description": { "type": "string" },
    "license": { "type": "string" },
    "language": { "type": "string", "enum": ["python", "typescript", "go", "rust"] },
    "python_version": { "type": "string", "pattern": "^3\\.[0-9]+$" },
    "author": {
      "type": "object",
      "properties": {
        "name": { "type": "string" },
        "email": { "type": "string", "format": "email" }
      }
    },
    "structure": {
      "type": "object",
      "properties": {
        "src_dir": { "type": "string" },
        "test_dir": { "type": "string" },
        "docs_dir": { "type": "string" }
      }
    },
    "modules": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["name"],
        "properties": {
          "name": { "type": "string" },
          "description": { "type": "string" }
        }
      }
    },
    "entry_points": { "type": "object" },
    "dependencies": {
      "type": "object",
      "properties": {
        "runtime": { "type": "array", "items": { "type": "string" } },
        "dev": { "type": "array", "items": { "type": "string" } },
        "optional": { "type": "object" }
      }
    },
    "features": {
      "type": "object",
      "additionalProperties": { "type": "boolean" }
    },
    "recon": { "type": "object" }
  },
  "additionalProperties": true
}
```

**Step 4: Create manifest schema**

`schema/manifest-schema.yaml` — validates pack manifest.yaml files.

```yaml
# Manifest schema for nboot template packs
# Validated by the engine at Stage 1
type: object
required:
  - name
  - version
  - templates
properties:
  name:
    type: string
    minLength: 1
  description:
    type: string
  version:
    type: string
  conditions:
    type: object
    additionalProperties:
      type: string
  loops:
    type: object
    additionalProperties:
      type: object
      required: [over, as]
      properties:
        over:
          type: string
        as:
          type: string
  templates:
    type: array
    items:
      type: object
      required: [src, dest]
      properties:
        src:
          type: string
        dest:
          type: string
        mode:
          type: string
          enum: [create, append]
  strip_suffix:
    type: string
  hooks:
    type: array
    items:
      type: string
  # Agent-workflow fields (engine ignores, but schema allows)
  dependencies:
    type: array
    items:
      type: string
  inputs:
    type: object
  action_shas:
    type: array
    items:
      type: object
      required: [name, repo, tag]
      properties:
        name:
          type: string
        repo:
          type: string
        tag:
          type: string
  validation:
    type: array
  decisions:
    type: array
additionalProperties: true
```

**Step 5: Create test conftest with shared fixtures**

```python
# tests/conftest.py
"""Shared test fixtures for nboot."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest


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

    import yaml
    (pack_dir / "manifest.yaml").write_text(yaml.dump(manifest))
    (templates_dir / "hello.txt.j2").write_text("Hello {{ spec.name }}!\n")

    return pack_dir
```

**Step 6: Create empty tests/__init__.py**

```python
# tests/__init__.py
```

**Step 7: Install the package in dev mode**

Run: `uv sync`

**Step 8: Verify pytest discovers tests**

Run: `uv run pytest --collect-only`
Expected: no errors, 0 tests collected

**Step 9: Commit**

```bash
git add pyproject.toml src/ tests/ schema/
git commit -m "chore: project scaffolding with schemas and test fixtures"
```

---

## Task 2: Spec Module (spec.py)

**Files:**
- Create: `src/navi_bootstrap/spec.py`
- Create: `tests/test_spec.py`

**Step 1: Write failing tests**

```python
# tests/test_spec.py
"""Tests for spec loading and validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from navi_bootstrap.spec import load_spec, validate_spec, SpecError


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
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_spec.py -v`
Expected: ImportError — module does not exist yet

**Step 3: Implement spec.py**

```python
# src/navi_bootstrap/spec.py
"""Spec loading and JSON Schema validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema

SCHEMA_PATH = Path(__file__).parent.parent.parent / "schema" / "spec-schema.json"


class SpecError(Exception):
    """Raised when a spec is invalid or cannot be loaded."""


def _load_schema() -> dict[str, Any]:
    """Load the JSON Schema for spec validation."""
    return json.loads(SCHEMA_PATH.read_text())


def validate_spec(spec: dict[str, Any]) -> None:
    """Validate a spec dict against the JSON Schema. Raises SpecError on failure."""
    schema = _load_schema()
    try:
        jsonschema.validate(instance=spec, schema=schema)
    except jsonschema.ValidationError as e:
        raise SpecError(f"Spec validation failed: {e.message}") from e


def load_spec(path: Path) -> dict[str, Any]:
    """Load and validate a spec from a JSON file. Returns the spec dict."""
    if not path.exists():
        raise SpecError(f"Spec file not found: {path}")
    try:
        spec = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise SpecError(f"Failed to parse spec JSON: {e}") from e
    validate_spec(spec)
    return spec
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_spec.py -v`
Expected: all PASS

**Step 5: Commit**

```bash
git add src/navi_bootstrap/spec.py tests/test_spec.py
git commit -m "feat: add spec loading and JSON Schema validation"
```

---

## Task 3: Manifest Module (manifest.py)

**Files:**
- Create: `src/navi_bootstrap/manifest.py`
- Create: `tests/test_manifest.py`

**Step 1: Write failing tests**

```python
# tests/test_manifest.py
"""Tests for manifest loading and validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from navi_bootstrap.manifest import load_manifest, validate_manifest, ManifestError


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
            validate_manifest({
                "name": "test",
                "version": "0.1.0",
                "templates": [{"dest": "out.txt"}],
            })

    def test_invalid_mode_raises(self) -> None:
        with pytest.raises(ManifestError):
            validate_manifest({
                "name": "test",
                "version": "0.1.0",
                "templates": [{"src": "a.j2", "dest": "a.txt", "mode": "overwrite"}],
            })

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
        valid_manifest["loops"] = {
            "module.py.j2": {"over": "spec.modules", "as": "module"}
        }
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
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_manifest.py -v`
Expected: ImportError

**Step 3: Implement manifest.py**

```python
# src/navi_bootstrap/manifest.py
"""Manifest loading and validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
import jsonschema


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
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_manifest.py -v`
Expected: all PASS

**Step 5: Commit**

```bash
git add src/navi_bootstrap/manifest.py tests/test_manifest.py
git commit -m "feat: add manifest loading and YAML schema validation"
```

---

## Task 4: Resolve Module (resolve.py)

**Files:**
- Create: `src/navi_bootstrap/resolve.py`
- Create: `tests/test_resolve.py`

**Step 1: Write failing tests**

The resolve module calls `gh api` via subprocess. Tests mock subprocess to avoid real API calls.

```python
# tests/test_resolve.py
"""Tests for action SHA resolution."""

from __future__ import annotations

import json
import subprocess
from unittest.mock import patch, MagicMock

import pytest

from navi_bootstrap.resolve import resolve_action_shas, ResolveError


@pytest.fixture
def action_shas_config() -> list[dict[str, str]]:
    return [
        {"name": "actions_checkout", "repo": "actions/checkout", "tag": "v4.2.2"},
        {"name": "harden_runner", "repo": "step-security/harden-runner", "tag": "v2.10.4"},
    ]


def _make_gh_response(sha: str, tag_type: str = "commit") -> str:
    """Build a mock gh api JSON response."""
    if tag_type == "commit":
        return json.dumps({"object": {"type": "commit", "sha": sha}})
    # Annotated tag — needs dereference
    return json.dumps({"object": {"type": "tag", "sha": "intermediate_sha", "url": "..."}})


class TestResolveActionShas:
    @patch("navi_bootstrap.resolve.subprocess.run")
    def test_resolves_lightweight_tags(
        self, mock_run: MagicMock, action_shas_config: list[dict[str, str]]
    ) -> None:
        sha1 = "abc123" * 7  # 42-char fake SHA
        sha2 = "def456" * 7
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=_make_gh_response(sha1[:40])),
            MagicMock(returncode=0, stdout=_make_gh_response(sha2[:40])),
        ]
        shas, versions = resolve_action_shas(action_shas_config)
        assert shas["actions_checkout"] == sha1[:40]
        assert shas["harden_runner"] == sha2[:40]
        assert versions["actions_checkout"] == "v4.2.2"
        assert versions["harden_runner"] == "v2.10.4"

    @patch("navi_bootstrap.resolve.subprocess.run")
    def test_resolves_annotated_tags(
        self, mock_run: MagicMock, action_shas_config: list[dict[str, str]]
    ) -> None:
        real_sha = "aaa111" * 7
        # First call returns annotated tag, second call dereferences
        mock_run.side_effect = [
            MagicMock(
                returncode=0,
                stdout=json.dumps({"object": {"type": "tag", "sha": "intermediate", "url": "u"}}),
            ),
            MagicMock(
                returncode=0,
                stdout=json.dumps({"object": {"type": "commit", "sha": real_sha[:40]}}),
            ),
            MagicMock(
                returncode=0,
                stdout=_make_gh_response(real_sha[:40]),
            ),
        ]
        shas, _ = resolve_action_shas(action_shas_config)
        assert shas["actions_checkout"] == real_sha[:40]

    @patch("navi_bootstrap.resolve.subprocess.run")
    def test_gh_failure_raises(
        self, mock_run: MagicMock, action_shas_config: list[dict[str, str]]
    ) -> None:
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="Not Found"
        )
        with pytest.raises(ResolveError, match="actions/checkout"):
            resolve_action_shas(action_shas_config)

    def test_empty_list_returns_empty(self) -> None:
        shas, versions = resolve_action_shas([])
        assert shas == {}
        assert versions == {}

    @patch("navi_bootstrap.resolve.subprocess.run")
    def test_skip_resolve_flag(
        self, mock_run: MagicMock, action_shas_config: list[dict[str, str]]
    ) -> None:
        shas, versions = resolve_action_shas(action_shas_config, skip=True)
        assert shas["actions_checkout"] == "SKIP_SHA_RESOLUTION"
        assert versions["actions_checkout"] == "v4.2.2"
        mock_run.assert_not_called()
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_resolve.py -v`
Expected: ImportError

**Step 3: Implement resolve.py**

```python
# src/navi_bootstrap/resolve.py
"""Stage 0: Resolve action SHAs via gh api."""

from __future__ import annotations

import json
import subprocess
from typing import Any


class ResolveError(Exception):
    """Raised when SHA resolution fails."""


def _gh_api(endpoint: str) -> dict[str, Any]:
    """Call gh api and return parsed JSON."""
    result = subprocess.run(
        ["gh", "api", endpoint],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ResolveError(f"gh api failed for {endpoint}: {result.stderr}")
    return json.loads(result.stdout)


def _resolve_one(repo: str, tag: str) -> str:
    """Resolve a single action tag to its commit SHA, handling annotated tags."""
    endpoint = f"repos/{repo}/git/refs/tags/{tag}"
    data = _gh_api(endpoint)
    obj = data["object"]

    # Annotated tag — dereference to get the commit
    if obj["type"] == "tag":
        deref_endpoint = f"repos/{repo}/git/tags/{obj['sha']}"
        tag_data = _gh_api(deref_endpoint)
        return tag_data["object"]["sha"]

    return obj["sha"]


def resolve_action_shas(
    action_shas: list[dict[str, str]], *, skip: bool = False
) -> tuple[dict[str, str], dict[str, str]]:
    """Resolve all action SHAs from manifest config.

    Returns (shas, versions) dicts keyed by action name.
    If skip=True, fills SHAs with placeholder strings (for dry-run/offline).
    """
    shas: dict[str, str] = {}
    versions: dict[str, str] = {}

    for entry in action_shas:
        name = entry["name"]
        versions[name] = entry["tag"]

        if skip:
            shas[name] = "SKIP_SHA_RESOLUTION"
        else:
            try:
                shas[name] = _resolve_one(entry["repo"], entry["tag"])
            except (ResolveError, KeyError, json.JSONDecodeError) as e:
                raise ResolveError(
                    f"Failed to resolve SHA for {entry['repo']}@{entry['tag']}: {e}"
                ) from e

    return shas, versions
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_resolve.py -v`
Expected: all PASS

**Step 5: Commit**

```bash
git add src/navi_bootstrap/resolve.py tests/test_resolve.py
git commit -m "feat: add action SHA resolution via gh api"
```

---

## Task 5: Engine Module (engine.py) — Plan + Render

This is the core module. ~150 lines covering Stage 2 (Plan) and Stage 3 (Render).

**Files:**
- Create: `src/navi_bootstrap/engine.py`
- Create: `tests/test_engine.py`

**Step 1: Write failing tests**

```python
# tests/test_engine.py
"""Tests for the engine plan and render stages."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from navi_bootstrap.engine import plan, render, RenderPlan, RenderEntry


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
    (templates_dir / "module.py.j2").write_text('"""{{ item.name }}: {{ item.description }}"""\n')
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
        manifest = yaml.safe_load(
            (pack_with_condition / "manifest.yaml").read_text()
        )
        result = plan(manifest, minimal_spec, pack_with_condition / "templates")
        dest_paths = [e.dest for e in result.entries]
        assert "always.txt" in dest_paths

    def test_plan_includes_true_condition(
        self, pack_with_condition: Path, minimal_spec: dict[str, Any]
    ) -> None:
        manifest = yaml.safe_load(
            (pack_with_condition / "manifest.yaml").read_text()
        )
        result = plan(manifest, minimal_spec, pack_with_condition / "templates")
        dest_paths = [e.dest for e in result.entries]
        assert "conditional.txt" in dest_paths

    def test_plan_skips_false_condition(
        self, pack_with_condition: Path, minimal_spec: dict[str, Any]
    ) -> None:
        minimal_spec["features"]["ci"] = False
        manifest = yaml.safe_load(
            (pack_with_condition / "manifest.yaml").read_text()
        )
        result = plan(manifest, minimal_spec, pack_with_condition / "templates")
        dest_paths = [e.dest for e in result.entries]
        assert "conditional.txt" not in dest_paths

    def test_plan_expands_loops(
        self, pack_with_loop: Path, spec_with_modules: dict[str, Any]
    ) -> None:
        manifest = yaml.safe_load(
            (pack_with_loop / "manifest.yaml").read_text()
        )
        result = plan(manifest, spec_with_modules, pack_with_loop / "templates")
        dest_paths = [e.dest for e in result.entries]
        assert "src/api.py" in dest_paths
        assert "src/models.py" in dest_paths

    def test_plan_preserves_mode(
        self, pack_with_append: Path, minimal_spec: dict[str, Any]
    ) -> None:
        manifest = yaml.safe_load(
            (pack_with_append / "manifest.yaml").read_text()
        )
        result = plan(manifest, minimal_spec, pack_with_append / "templates")
        assert result.entries[0].mode == "append"


# --- Render tests ---

class TestRender:
    def test_render_creates_files(
        self, minimal_manifest_dir: Path, minimal_spec: dict[str, Any], tmp_path: Path
    ) -> None:
        manifest = yaml.safe_load(
            (minimal_manifest_dir / "manifest.yaml").read_text()
        )
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        render_plan = plan(manifest, minimal_spec, minimal_manifest_dir / "templates")
        render(render_plan, minimal_spec, minimal_manifest_dir / "templates", output_dir)
        assert (output_dir / "hello.txt").exists()
        assert "test-project" in (output_dir / "hello.txt").read_text()

    def test_render_loop_creates_multiple_files(
        self, pack_with_loop: Path, spec_with_modules: dict[str, Any], tmp_path: Path
    ) -> None:
        manifest = yaml.safe_load(
            (pack_with_loop / "manifest.yaml").read_text()
        )
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
        # Pre-existing file
        (output_dir / "pyproject.toml").write_text('[project]\nname = "existing"\n')

        manifest = yaml.safe_load(
            (pack_with_append / "manifest.yaml").read_text()
        )
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
        # File with existing markers from a previous run
        (output_dir / "pyproject.toml").write_text(
            '[project]\nname = "existing"\n'
            "# --- nboot: test-pack ---\n"
            "old content\n"
            "# --- end nboot: test-pack ---\n"
        )

        manifest = yaml.safe_load(
            (pack_with_append / "manifest.yaml").read_text()
        )
        render_plan = plan(manifest, minimal_spec, pack_with_append / "templates")
        render(render_plan, minimal_spec, pack_with_append / "templates", output_dir)
        content = (output_dir / "pyproject.toml").read_text()
        assert "old content" not in content
        assert "line-length = 100" in content
        # Only one set of markers
        assert content.count("# --- nboot: test-pack ---") == 1

    def test_render_greenfield_fails_if_file_exists(
        self, minimal_manifest_dir: Path, minimal_spec: dict[str, Any], tmp_path: Path
    ) -> None:
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        (output_dir / "hello.txt").write_text("already here")

        manifest = yaml.safe_load(
            (minimal_manifest_dir / "manifest.yaml").read_text()
        )
        render_plan = plan(manifest, minimal_spec, minimal_manifest_dir / "templates")
        with pytest.raises(FileExistsError):
            render(
                render_plan, minimal_spec, minimal_manifest_dir / "templates",
                output_dir, mode="greenfield",
            )

    def test_render_apply_creates_new_files(
        self, minimal_manifest_dir: Path, minimal_spec: dict[str, Any], tmp_path: Path
    ) -> None:
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        manifest = yaml.safe_load(
            (minimal_manifest_dir / "manifest.yaml").read_text()
        )
        render_plan = plan(manifest, minimal_spec, minimal_manifest_dir / "templates")
        render(
            render_plan, minimal_spec, minimal_manifest_dir / "templates",
            output_dir, mode="apply",
        )
        assert (output_dir / "hello.txt").exists()
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_engine.py -v`
Expected: ImportError

**Step 3: Implement engine.py**

```python
# src/navi_bootstrap/engine.py
"""Stages 2 (Plan) and 3 (Render) of the nboot engine."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import jinja2


@dataclass
class RenderEntry:
    """A single file to render."""
    src: str        # template filename (relative to templates dir)
    dest: str       # output path (relative to output dir)
    mode: str = "create"  # "create" or "append"
    extra_context: dict[str, Any] = field(default_factory=dict)


@dataclass
class RenderPlan:
    """The full list of files to render."""
    entries: list[RenderEntry] = field(default_factory=list)
    pack_name: str = ""


def _resolve_dotpath(obj: Any, path: str) -> Any:
    """Resolve a dotpath like 'spec.features.ci' against a nested dict."""
    parts = path.split(".")
    current = obj
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def _eval_condition(condition_expr: str, spec: dict[str, Any]) -> bool:
    """Evaluate a dotpath condition expression against spec context."""
    # Condition expressions are like "spec.features.ci"
    context = {"spec": spec}
    value = _resolve_dotpath(context, condition_expr)
    return bool(value)


def _render_dest_path(dest_template: str, context: dict[str, Any]) -> str:
    """Render Jinja2 expressions in destination paths."""
    env = jinja2.Environment(undefined=jinja2.StrictUndefined)
    tmpl = env.from_string(dest_template)
    return tmpl.render(**context)


def plan(
    manifest: dict[str, Any],
    spec: dict[str, Any],
    templates_dir: Path,
) -> RenderPlan:
    """Stage 2: Build a render plan from manifest + spec."""
    render_plan = RenderPlan(pack_name=manifest.get("name", "unknown"))
    conditions = manifest.get("conditions", {})
    loops = manifest.get("loops", {})

    for template_entry in manifest.get("templates", []):
        src = template_entry["src"]
        dest = template_entry["dest"]
        mode = template_entry.get("mode", "create")

        # Check conditions
        if src in conditions:
            if not _eval_condition(conditions[src], spec):
                continue

        # Check if this is a looped template
        if src in loops:
            loop_config = loops[src]
            over_path = loop_config["over"]
            as_name = loop_config["as"]
            items = _resolve_dotpath({"spec": spec}, over_path)
            if items is None:
                items = []
            for item in items:
                context = {"spec": spec, as_name: item}
                resolved_dest = _render_dest_path(dest, context)
                render_plan.entries.append(
                    RenderEntry(
                        src=src,
                        dest=resolved_dest,
                        mode=mode,
                        extra_context={as_name: item},
                    )
                )
        else:
            render_plan.entries.append(
                RenderEntry(src=src, dest=dest, mode=mode)
            )

    return render_plan


# Marker block pattern
_MARKER_START = "# --- nboot: {pack_name} ---"
_MARKER_END = "# --- end nboot: {pack_name} ---"
_MARKER_RE = re.compile(
    r"# --- nboot: (?P<pack>\S+) ---\n.*?# --- end nboot: (?P=pack) ---\n?",
    re.DOTALL,
)


def _write_append(output_path: Path, rendered: str, pack_name: str) -> None:
    """Append rendered content with marker blocks, replacing existing markers."""
    marker_start = _MARKER_START.format(pack_name=pack_name)
    marker_end = _MARKER_END.format(pack_name=pack_name)
    block = f"{marker_start}\n{rendered}{marker_end}\n"

    if output_path.exists():
        existing = output_path.read_text()
        # Replace existing marker block if present
        if marker_start in existing:
            new_content = _MARKER_RE.sub("", existing, count=1)
            # Ensure trailing newline before appending
            if new_content and not new_content.endswith("\n"):
                new_content += "\n"
            output_path.write_text(new_content + block)
        else:
            # Append to end
            if existing and not existing.endswith("\n"):
                existing += "\n"
            output_path.write_text(existing + block)
    else:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(block)


def render(
    render_plan: RenderPlan,
    spec: dict[str, Any],
    templates_dir: Path,
    output_dir: Path,
    *,
    mode: str = "apply",
    action_shas: dict[str, str] | None = None,
    action_versions: dict[str, str] | None = None,
) -> list[Path]:
    """Stage 3: Render all templates from the plan.

    mode: "greenfield" (fail if non-append files exist) or "apply" (create/append).
    Returns list of written file paths.
    """
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(templates_dir)),
        undefined=jinja2.StrictUndefined,
        keep_trailing_newline=True,
    )

    context: dict[str, Any] = {
        "spec": spec,
        "action_shas": action_shas or {},
        "action_versions": action_versions or {},
    }

    written: list[Path] = []

    for entry in render_plan.entries:
        template = env.get_template(entry.src)
        render_context = {**context, **entry.extra_context}
        rendered = template.render(**render_context)

        output_path = output_dir / entry.dest

        if entry.mode == "append":
            _write_append(output_path, rendered, render_plan.pack_name)
        else:
            if mode == "greenfield" and output_path.exists():
                raise FileExistsError(
                    f"File already exists (greenfield mode): {output_path}"
                )
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(rendered)

        written.append(output_path)

    return written
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_engine.py -v`
Expected: all PASS

**Step 5: Commit**

```bash
git add src/navi_bootstrap/engine.py tests/test_engine.py
git commit -m "feat: add engine plan and render stages with append mode"
```

---

## Task 6: Validate Module (validate.py)

**Files:**
- Create: `src/navi_bootstrap/validate.py`
- Create: `tests/test_validate.py`

**Step 1: Write failing tests**

```python
# tests/test_validate.py
"""Tests for post-render validation runner."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from navi_bootstrap.validate import run_validations, ValidationResult


@pytest.fixture
def validation_config() -> list[dict[str, str]]:
    return [
        {
            "description": "Check passes",
            "command": "echo ok",
            "expect": "exit_code_0",
        },
        {
            "description": "Check warns",
            "command": "echo warn && exit 1",
            "expect": "exit_code_0_or_warnings",
        },
    ]


class TestRunValidations:
    @patch("navi_bootstrap.validate.subprocess.run")
    def test_passing_validation(
        self, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        results = run_validations(
            [{"description": "test", "command": "echo ok", "expect": "exit_code_0"}],
            tmp_path,
        )
        assert len(results) == 1
        assert results[0].passed

    @patch("navi_bootstrap.validate.subprocess.run")
    def test_failing_validation(
        self, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="fail")
        results = run_validations(
            [{"description": "test", "command": "bad", "expect": "exit_code_0"}],
            tmp_path,
        )
        assert len(results) == 1
        assert not results[0].passed

    @patch("navi_bootstrap.validate.subprocess.run")
    def test_warnings_accepted(
        self, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        mock_run.return_value = MagicMock(returncode=1, stdout="warning", stderr="")
        results = run_validations(
            [{"description": "test", "command": "warn", "expect": "exit_code_0_or_warnings"}],
            tmp_path,
        )
        assert len(results) == 1
        assert results[0].passed

    def test_empty_validations(self, tmp_path: Path) -> None:
        results = run_validations([], tmp_path)
        assert results == []

    @patch("navi_bootstrap.validate.subprocess.run")
    def test_skips_method_based_validations(
        self, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        results = run_validations(
            [{"description": "SHA check", "method": "sha_verification"}],
            tmp_path,
        )
        assert len(results) == 1
        assert results[0].skipped
        mock_run.assert_not_called()
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_validate.py -v`
Expected: ImportError

**Step 3: Implement validate.py**

```python
# src/navi_bootstrap/validate.py
"""Stage 4: Post-render validation runner."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ValidationResult:
    """Result of a single validation check."""
    description: str
    passed: bool
    skipped: bool = False
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0


def run_validations(
    validations: list[dict[str, Any]], working_dir: Path
) -> list[ValidationResult]:
    """Run validation commands and return results."""
    results: list[ValidationResult] = []

    for v in validations:
        description = v.get("description", "unnamed")

        # Skip method-based validations (handled elsewhere)
        if "method" in v and "command" not in v:
            results.append(ValidationResult(
                description=description, passed=False, skipped=True
            ))
            continue

        command = v["command"]
        expect = v.get("expect", "exit_code_0")

        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            cwd=working_dir,
        )

        if expect == "exit_code_0":
            passed = result.returncode == 0
        elif expect == "exit_code_0_or_warnings":
            passed = True  # Accept any exit code for this mode
        else:
            passed = result.returncode == 0

        results.append(ValidationResult(
            description=description,
            passed=passed,
            stdout=result.stdout,
            stderr=result.stderr,
            returncode=result.returncode,
        ))

    return results
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_validate.py -v`
Expected: all PASS

**Step 5: Commit**

```bash
git add src/navi_bootstrap/validate.py tests/test_validate.py
git commit -m "feat: add post-render validation runner"
```

---

## Task 7: Hooks Module (hooks.py)

**Files:**
- Create: `src/navi_bootstrap/hooks.py`
- Create: `tests/test_hooks.py`

**Step 1: Write failing tests**

```python
# tests/test_hooks.py
"""Tests for post-render hook runner."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from navi_bootstrap.hooks import run_hooks, HookResult


class TestRunHooks:
    @patch("navi_bootstrap.hooks.subprocess.run")
    def test_runs_hooks_sequentially(
        self, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        results = run_hooks(["echo hello", "echo world"], tmp_path)
        assert len(results) == 2
        assert all(r.success for r in results)
        assert mock_run.call_count == 2

    @patch("navi_bootstrap.hooks.subprocess.run")
    def test_reports_failures_without_stopping(
        self, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        mock_run.side_effect = [
            MagicMock(returncode=1, stdout="", stderr="fail"),
            MagicMock(returncode=0, stdout="ok", stderr=""),
        ]
        results = run_hooks(["bad", "good"], tmp_path)
        assert not results[0].success
        assert results[1].success

    def test_empty_hooks(self, tmp_path: Path) -> None:
        results = run_hooks([], tmp_path)
        assert results == []

    @patch("navi_bootstrap.hooks.subprocess.run")
    def test_captures_output(
        self, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        mock_run.return_value = MagicMock(
            returncode=0, stdout="some output", stderr="some warning"
        )
        results = run_hooks(["test_cmd"], tmp_path)
        assert results[0].stdout == "some output"
        assert results[0].stderr == "some warning"
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_hooks.py -v`
Expected: ImportError

**Step 3: Implement hooks.py**

```python
# src/navi_bootstrap/hooks.py
"""Stage 5: Post-render hook runner."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class HookResult:
    """Result of a single hook execution."""
    command: str
    success: bool
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0


def run_hooks(hooks: list[str], working_dir: Path) -> list[HookResult]:
    """Run hook commands sequentially. Reports failures but does not stop."""
    results: list[HookResult] = []

    for command in hooks:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            cwd=working_dir,
        )
        results.append(HookResult(
            command=command,
            success=result.returncode == 0,
            stdout=result.stdout,
            stderr=result.stderr,
            returncode=result.returncode,
        ))

    return results
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_hooks.py -v`
Expected: all PASS

**Step 5: Commit**

```bash
git add src/navi_bootstrap/hooks.py tests/test_hooks.py
git commit -m "feat: add post-render hook runner"
```

---

## Task 8: CLI Module (cli.py)

**Files:**
- Create: `src/navi_bootstrap/cli.py`
- Create: `tests/test_cli.py`

**Step 1: Write failing tests**

```python
# tests/test_cli.py
"""Tests for the nboot CLI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from click.testing import CliRunner

from navi_bootstrap.cli import cli


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def full_pack(tmp_path: Path) -> Path:
    """A complete pack for CLI integration tests."""
    pack_dir = tmp_path / "pack"
    pack_dir.mkdir()
    templates_dir = pack_dir / "templates"
    templates_dir.mkdir()

    manifest = {
        "name": "cli-test-pack",
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
def spec_file(tmp_path: Path) -> Path:
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


class TestValidateCommand:
    def test_validate_valid_spec(
        self, runner: CliRunner, spec_file: Path
    ) -> None:
        result = runner.invoke(cli, ["validate", "--spec", str(spec_file)])
        assert result.exit_code == 0
        assert "valid" in result.output.lower()

    def test_validate_invalid_spec(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        bad_spec = tmp_path / "bad.json"
        bad_spec.write_text(json.dumps({"not": "valid"}))
        result = runner.invoke(cli, ["validate", "--spec", str(bad_spec)])
        assert result.exit_code != 0

    def test_validate_with_pack(
        self, runner: CliRunner, spec_file: Path, full_pack: Path
    ) -> None:
        result = runner.invoke(
            cli, ["validate", "--spec", str(spec_file), "--pack", str(full_pack)]
        )
        assert result.exit_code == 0


class TestRenderCommand:
    def test_render_creates_output(
        self, runner: CliRunner, spec_file: Path, full_pack: Path, tmp_path: Path
    ) -> None:
        out_dir = tmp_path / "output"
        result = runner.invoke(
            cli,
            ["render", "--spec", str(spec_file), "--pack", str(full_pack), "--out", str(out_dir)],
        )
        assert result.exit_code == 0
        assert (out_dir / "README.md").exists()
        assert "my-project" in (out_dir / "README.md").read_text()

    def test_render_dry_run(
        self, runner: CliRunner, spec_file: Path, full_pack: Path, tmp_path: Path
    ) -> None:
        out_dir = tmp_path / "output"
        result = runner.invoke(
            cli,
            [
                "render", "--spec", str(spec_file), "--pack", str(full_pack),
                "--out", str(out_dir), "--dry-run",
            ],
        )
        assert result.exit_code == 0
        assert not (out_dir / "README.md").exists()

    def test_render_fails_if_output_exists(
        self, runner: CliRunner, spec_file: Path, full_pack: Path, tmp_path: Path
    ) -> None:
        out_dir = tmp_path / "output"
        out_dir.mkdir()
        (out_dir / "README.md").write_text("existing")
        result = runner.invoke(
            cli,
            ["render", "--spec", str(spec_file), "--pack", str(full_pack), "--out", str(out_dir)],
        )
        assert result.exit_code != 0


class TestApplyCommand:
    def test_apply_creates_files(
        self, runner: CliRunner, spec_file: Path, full_pack: Path, tmp_path: Path
    ) -> None:
        target_dir = tmp_path / "target"
        target_dir.mkdir()
        result = runner.invoke(
            cli,
            ["apply", "--spec", str(spec_file), "--pack", str(full_pack), "--target", str(target_dir)],
        )
        assert result.exit_code == 0
        assert (target_dir / "README.md").exists()

    def test_apply_dry_run(
        self, runner: CliRunner, spec_file: Path, full_pack: Path, tmp_path: Path
    ) -> None:
        target_dir = tmp_path / "target"
        target_dir.mkdir()
        result = runner.invoke(
            cli,
            [
                "apply", "--spec", str(spec_file), "--pack", str(full_pack),
                "--target", str(target_dir), "--dry-run",
            ],
        )
        assert result.exit_code == 0
        assert not (target_dir / "README.md").exists()
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py -v`
Expected: ImportError

**Step 3: Implement cli.py**

```python
# src/navi_bootstrap/cli.py
"""nboot CLI — render and apply template packs."""

from __future__ import annotations

from pathlib import Path

import click

from navi_bootstrap.engine import plan, render
from navi_bootstrap.hooks import run_hooks
from navi_bootstrap.manifest import load_manifest, ManifestError
from navi_bootstrap.resolve import resolve_action_shas, ResolveError
from navi_bootstrap.spec import load_spec, SpecError
from navi_bootstrap.validate import run_validations


@click.group()
@click.version_option()
def cli() -> None:
    """nboot — bootstrap projects to navi-os-grade posture."""


@cli.command()
@click.option("--spec", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--pack", type=click.Path(exists=True, path_type=Path), default=None)
def validate(spec: Path, pack: Path | None) -> None:
    """Validate a spec (and optionally a pack manifest)."""
    try:
        load_spec(spec)
        click.echo(f"Spec valid: {spec}")
    except SpecError as e:
        raise click.ClickException(str(e))

    if pack:
        try:
            load_manifest(pack / "manifest.yaml")
            click.echo(f"Manifest valid: {pack / 'manifest.yaml'}")
        except ManifestError as e:
            raise click.ClickException(str(e))


@cli.command()
@click.option("--spec", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--pack", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--out", type=click.Path(path_type=Path), default=None)
@click.option("--dry-run", is_flag=True, default=False)
@click.option("--skip-resolve", is_flag=True, default=False, help="Skip SHA resolution (offline)")
def render_cmd(spec: Path, pack: Path, out: Path | None, dry_run: bool, skip_resolve: bool) -> None:
    """Render a template pack into a new project (greenfield)."""
    try:
        spec_data = load_spec(spec)
    except SpecError as e:
        raise click.ClickException(str(e))

    try:
        manifest = load_manifest(pack / "manifest.yaml")
    except ManifestError as e:
        raise click.ClickException(str(e))

    output_dir = out or Path(spec_data["name"])

    # Stage 0: Resolve SHAs
    action_shas_config = manifest.get("action_shas", [])
    try:
        shas, versions = resolve_action_shas(action_shas_config, skip=skip_resolve or dry_run)
    except ResolveError as e:
        raise click.ClickException(str(e))

    # Stage 2: Plan
    templates_dir = pack / "templates"
    render_plan = plan(manifest, spec_data, templates_dir)

    if dry_run:
        click.echo("Dry run — render plan:")
        for entry in render_plan.entries:
            mode_tag = f" [{entry.mode}]" if entry.mode != "create" else ""
            click.echo(f"  {entry.src} → {entry.dest}{mode_tag}")
        return

    # Stage 3: Render
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        written = render(
            render_plan, spec_data, templates_dir, output_dir,
            mode="greenfield", action_shas=shas, action_versions=versions,
        )
    except FileExistsError as e:
        raise click.ClickException(str(e))

    click.echo(f"Rendered {len(written)} files to {output_dir}")

    # Stage 5: Hooks
    hooks = manifest.get("hooks", [])
    if hooks:
        click.echo("Running hooks...")
        results = run_hooks(hooks, output_dir)
        for r in results:
            status = "OK" if r.success else "FAIL"
            click.echo(f"  [{status}] {r.command}")


# Click doesn't allow "render" as a command name (conflicts with method), so alias it
render_cmd.name = "render"


@cli.command()
@click.option("--spec", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--pack", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--target", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--dry-run", is_flag=True, default=False)
@click.option("--skip-resolve", is_flag=True, default=False, help="Skip SHA resolution (offline)")
def apply(spec: Path, pack: Path, target: Path, dry_run: bool, skip_resolve: bool) -> None:
    """Apply a template pack to an existing project."""
    try:
        spec_data = load_spec(spec)
    except SpecError as e:
        raise click.ClickException(str(e))

    try:
        manifest = load_manifest(pack / "manifest.yaml")
    except ManifestError as e:
        raise click.ClickException(str(e))

    # Stage 0: Resolve SHAs
    action_shas_config = manifest.get("action_shas", [])
    try:
        shas, versions = resolve_action_shas(action_shas_config, skip=skip_resolve or dry_run)
    except ResolveError as e:
        raise click.ClickException(str(e))

    # Stage 2: Plan
    templates_dir = pack / "templates"
    render_plan = plan(manifest, spec_data, templates_dir)

    if dry_run:
        click.echo("Dry run — render plan:")
        for entry in render_plan.entries:
            mode_tag = f" [{entry.mode}]" if entry.mode != "create" else ""
            click.echo(f"  {entry.src} → {entry.dest}{mode_tag}")
        return

    # Stage 3: Render
    written = render(
        render_plan, spec_data, templates_dir, target,
        mode="apply", action_shas=shas, action_versions=versions,
    )
    click.echo(f"Applied {len(written)} files to {target}")

    # Stage 4: Validate
    validations = manifest.get("validation", [])
    if validations:
        click.echo("Running validations...")
        results = run_validations(validations, target)
        for r in results:
            if r.skipped:
                status = "SKIP"
            elif r.passed:
                status = "PASS"
            else:
                status = "FAIL"
            click.echo(f"  [{status}] {r.description}")

    # Stage 5: Hooks
    hooks = manifest.get("hooks", [])
    if hooks:
        click.echo("Running hooks...")
        results = run_hooks(hooks, target)
        for r in results:
            status = "OK" if r.success else "FAIL"
            click.echo(f"  [{status}] {r.command}")
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_cli.py -v`
Expected: all PASS

**Step 5: Run full test suite**

Run: `uv run pytest -v`
Expected: all PASS

**Step 6: Commit**

```bash
git add src/navi_bootstrap/cli.py tests/test_cli.py
git commit -m "feat: add nboot CLI with render, apply, and validate commands"
```

---

## Task 9: Base Pack — Manifest + Templates

This creates the first real template pack: the base pack that bootstraps CI, pre-commit, tool config, CLAUDE.md, DEBT.md, and dependabot.

**Files:**
- Create: `packs/base/manifest.yaml`
- Create: `packs/base/templates/pre-commit-config.yaml.j2`
- Create: `packs/base/templates/dependabot.yml.j2`
- Create: `packs/base/templates/pyproject-tools.toml.j2`
- Create: `packs/base/templates/workflows/tests.yml.j2`
- Create: `packs/base/templates/CLAUDE.md.j2`
- Create: `packs/base/templates/DEBT.md.j2`
- Create: `tests/test_base_pack.py`

**Step 1: Write integration test for the base pack**

```python
# tests/test_base_pack.py
"""Integration tests for the base template pack."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

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
        self, base_spec: dict[str, Any], fake_shas: dict[str, str],
        fake_versions: dict[str, str], tmp_path: Path,
    ) -> None:
        manifest = load_manifest(PACK_DIR / "manifest.yaml")
        templates_dir = PACK_DIR / "templates"
        render_plan = plan(manifest, base_spec, templates_dir)
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        written = render(
            render_plan, base_spec, templates_dir, output_dir,
            mode="apply", action_shas=fake_shas, action_versions=fake_versions,
        )
        assert len(written) > 0

        # Check key files exist
        assert (output_dir / ".pre-commit-config.yaml").exists()
        assert (output_dir / ".github" / "dependabot.yml").exists()
        assert (output_dir / "CLAUDE.md").exists()
        assert (output_dir / "DEBT.md").exists()

    def test_ci_workflow_uses_shas(
        self, base_spec: dict[str, Any], fake_shas: dict[str, str],
        fake_versions: dict[str, str], tmp_path: Path,
    ) -> None:
        manifest = load_manifest(PACK_DIR / "manifest.yaml")
        templates_dir = PACK_DIR / "templates"
        render_plan = plan(manifest, base_spec, templates_dir)
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        render(
            render_plan, base_spec, templates_dir, output_dir,
            mode="apply", action_shas=fake_shas, action_versions=fake_versions,
        )
        ci_content = (output_dir / ".github" / "workflows" / "tests.yml").read_text()
        # SHAs must appear in the workflow, never hardcoded strings
        assert fake_shas["actions_checkout"] in ci_content
        assert fake_shas["harden_runner"] in ci_content

    def test_pyproject_append_has_markers(
        self, base_spec: dict[str, Any], fake_shas: dict[str, str],
        fake_versions: dict[str, str], tmp_path: Path,
    ) -> None:
        manifest = load_manifest(PACK_DIR / "manifest.yaml")
        templates_dir = PACK_DIR / "templates"
        render_plan = plan(manifest, base_spec, templates_dir)
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        # Pre-existing pyproject.toml
        (output_dir / "pyproject.toml").write_text('[project]\nname = "arctl"\n')
        render(
            render_plan, base_spec, templates_dir, output_dir,
            mode="apply", action_shas=fake_shas, action_versions=fake_versions,
        )
        content = (output_dir / "pyproject.toml").read_text()
        assert "# --- nboot: base ---" in content
        assert "[tool.ruff]" in content

    def test_ci_skipped_when_feature_false(
        self, base_spec: dict[str, Any], fake_shas: dict[str, str],
        fake_versions: dict[str, str], tmp_path: Path,
    ) -> None:
        base_spec["features"]["ci"] = False
        manifest = load_manifest(PACK_DIR / "manifest.yaml")
        templates_dir = PACK_DIR / "templates"
        render_plan = plan(manifest, base_spec, templates_dir)
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        render(
            render_plan, base_spec, templates_dir, output_dir,
            mode="apply", action_shas=fake_shas, action_versions=fake_versions,
        )
        assert not (output_dir / ".github" / "workflows" / "tests.yml").exists()
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_base_pack.py -v`
Expected: FAIL (pack directory doesn't exist)

**Step 3: Create the base pack manifest**

`packs/base/manifest.yaml` — matches the unified design spec exactly.

**Step 4: Create all base pack templates**

Create each template file under `packs/base/templates/`. Reference the navi-os project for gold-standard patterns.

Key template details:
- **pre-commit-config.yaml.j2**: ruff, mypy, bandit, detect-secrets hooks, configured for `{{ spec.python_version }}`
- **dependabot.yml.j2**: pip and github-actions update schedules
- **pyproject-tools.toml.j2**: ruff, mypy, bandit tool config sections (mode: append)
- **workflows/tests.yml.j2**: test + lint + security CI jobs using `{{ action_shas.* }}` for all GitHub Actions
- **CLAUDE.md.j2**: agent guidance for the target project
- **DEBT.md.j2**: technical debt tracking template

The templates should reference navi-os conventions:
- `line-length = 100` for ruff
- SHA-pinned actions with version comments
- harden-runner in every job
- matrix strategy for python test versions from `{{ spec.recon.python_test_versions }}`

**Step 5: Run tests**

Run: `uv run pytest tests/test_base_pack.py -v`
Expected: all PASS

**Step 6: Run full test suite**

Run: `uv run pytest -v`
Expected: all PASS

**Step 7: Commit**

```bash
git add packs/ tests/test_base_pack.py
git commit -m "feat: add base template pack with CI, pre-commit, and tool config"
```

---

## Task 10: Final Integration + Cleanup

**Step 1: Run full test suite with coverage**

Run: `uv run pytest --cov=navi_bootstrap --cov-report=term-missing -v`
Expected: all PASS, >80% coverage

**Step 2: Run ruff**

Run: `uv run ruff check src/ tests/`
Expected: clean

**Step 3: Smoke test the CLI end-to-end**

```bash
# Create a test spec
echo '{"name": "smoke-test", "language": "python", "python_version": "3.12", "features": {"ci": true, "pre_commit": true}, "recon": {"python_test_versions": ["3.12"]}}' > /tmp/smoke-spec.json

# Dry run
uv run nboot apply --spec /tmp/smoke-spec.json --pack ./packs/base --target /tmp/smoke-target --dry-run --skip-resolve

# Real run (with skip-resolve for offline)
mkdir -p /tmp/smoke-target
uv run nboot apply --spec /tmp/smoke-spec.json --pack ./packs/base --target /tmp/smoke-target --skip-resolve
```

**Step 4: Commit any fixes**

**Step 5: Create CLAUDE.md for the nboot project itself**

A minimal CLAUDE.md with project conventions for future development sessions.

```bash
git add -A
git commit -m "chore: integration test, cleanup, and project CLAUDE.md"
```
