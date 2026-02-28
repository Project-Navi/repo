# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Project Navi

"""Project inspection and spec generation for nboot init."""

from __future__ import annotations

import logging
import re
import subprocess
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("navi_bootstrap.init")

# Order matters — first match wins.
_LANGUAGE_MARKERS: list[tuple[str, str]] = [
    ("pyproject.toml", "python"),
    ("setup.py", "python"),
    ("Cargo.toml", "rust"),
    ("go.mod", "go"),
    ("package.json", "typescript"),
]

# Try >= first (minimum bound), fall back to any 3.X match.
_PYTHON_VERSION_GE_RE = re.compile(r">=\s*3\.(\d+)")
_PYTHON_VERSION_RE = re.compile(r"3\.(\d+)")
_DEP_NAME_RE = re.compile(r"^([a-zA-Z0-9][-a-zA-Z0-9_.]*)")

_MAX_TEST_FILE_SIZE = 1_000_000  # 1 MB
_GITHUB_SSH_RE = re.compile(r"git@github\.com:([^/]+)/([^/.]+?)(?:\.git)?$")
_GITHUB_HTTPS_RE = re.compile(r"https?://github\.com/([^/]+)/([^/.]+?)(?:\.git)?$")


def detect_language(target: Path) -> str | None:
    """Detect project language from marker files."""
    for filename, language in _LANGUAGE_MARKERS:
        if (target / filename).exists():
            return language
    return None


def parse_github_url(url: str) -> tuple[str, str] | None:
    """Parse (org, repo) from a GitHub remote URL. Returns None if not GitHub."""
    for pattern in (_GITHUB_SSH_RE, _GITHUB_HTTPS_RE):
        m = pattern.match(url)
        if m:
            return m.group(1), m.group(2)
    return None


def detect_python_metadata(target: Path) -> dict[str, Any]:
    """Extract project metadata from pyproject.toml."""
    pyproject_path = target / "pyproject.toml"
    if not pyproject_path.exists():
        return {}

    try:
        data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError, PermissionError, OSError):
        logger.warning("Failed to read or parse %s", pyproject_path)
        return {}

    project = data.get("project")
    if not project:
        return {}

    result: dict[str, Any] = {}

    # Basic fields
    if name := project.get("name"):
        result["name"] = name
    if version := project.get("version"):
        result["version"] = version
    if description := project.get("description"):
        result["description"] = description

    # License — string or table
    if lic := project.get("license"):
        if isinstance(lic, str):
            result["license"] = lic
        elif isinstance(lic, dict) and "text" in lic:
            result["license"] = lic["text"]

    # Python version from requires-python — prefer >= (minimum bound)
    if requires := project.get("requires-python"):
        m = _PYTHON_VERSION_GE_RE.search(requires) or _PYTHON_VERSION_RE.search(requires)
        if m:
            result["python_version"] = f"3.{m.group(1)}"

    # Author
    authors = project.get("authors", [])
    if authors and isinstance(authors[0], dict):
        author: dict[str, str] = {}
        if "name" in authors[0]:
            author["name"] = authors[0]["name"]
        if "email" in authors[0]:
            author["email"] = authors[0]["email"]
        if author:
            result["author"] = author

    # Dependencies
    deps: dict[str, list[str]] = {}
    if runtime := project.get("dependencies"):
        deps["runtime"] = _extract_dep_names(runtime)

    # Dev deps: prefer [dependency-groups].dev over [project.optional-dependencies].dev
    dev_deps = data.get("dependency-groups", {}).get("dev")
    if dev_deps is None:
        dev_deps = project.get("optional-dependencies", {}).get("dev")
    if dev_deps:
        deps["dev"] = _extract_dep_names(dev_deps)

    if deps:
        result["dependencies"] = deps

    # Structure
    structure: dict[str, str] = {}

    # src_dir: look for src/<package>/__init__.py
    # Prefer package matching project name (e.g. "my-project" → "my_project")
    src_dir = target / "src"
    if src_dir.is_dir():
        packages = [
            c for c in sorted(src_dir.iterdir()) if c.is_dir() and (c / "__init__.py").exists()
        ]
        if packages:
            project_name = result.get("name", "")
            normalized = project_name.replace("-", "_")
            match = next((p for p in packages if p.name == normalized), None)
            structure["src_dir"] = f"src/{(match or packages[0]).name}"

    # test_dir: check pytest config first, then convention
    pytest_config = data.get("tool", {}).get("pytest", {}).get("ini_options", {})
    testpaths = pytest_config.get("testpaths", [])
    if testpaths and isinstance(testpaths[0], str):
        structure["test_dir"] = testpaths[0]
    elif (target / "tests").is_dir():
        structure["test_dir"] = "tests"
    elif (target / "test").is_dir():
        structure["test_dir"] = "test"

    if structure:
        result["structure"] = structure

    return result


def detect_existing_tools(target: Path) -> dict[str, bool]:
    """Detect which dev tools are present in the project."""
    tools: dict[str, bool] = {
        "ruff": False,
        "mypy": False,
        "bandit": False,
        "pre_commit": False,
        "dependabot": False,
    }

    # Parse pyproject.toml for tool sections and dev deps
    pyproject_path = target / "pyproject.toml"
    if pyproject_path.exists():
        try:
            data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
        except (tomllib.TOMLDecodeError, UnicodeDecodeError, PermissionError, OSError):
            data = {}

        tool = data.get("tool", {})
        if "ruff" in tool:
            tools["ruff"] = True
        if "mypy" in tool:
            tools["mypy"] = True

        # Check dev deps for bandit
        dev_deps = data.get("dependency-groups", {}).get("dev", [])
        if not dev_deps:
            dev_deps = data.get("project", {}).get("optional-dependencies", {}).get("dev", [])
        dep_names = _extract_dep_names(dev_deps)
        if "bandit" in dep_names:
            tools["bandit"] = True

    # File-based detection
    if (target / ".pre-commit-config.yaml").exists():
        tools["pre_commit"] = True
    if (target / ".github" / "dependabot.yml").exists():
        tools["dependabot"] = True

    return tools


def detect_features(target: Path) -> dict[str, bool]:
    """Detect which features are active in the project."""
    features: dict[str, bool] = {
        "ci": False,
        "pre_commit": False,
    }

    wf_dir = target / ".github" / "workflows"
    if wf_dir.is_dir() and (any(wf_dir.glob("*.yml")) or any(wf_dir.glob("*.yaml"))):
        features["ci"] = True

    if (target / ".pre-commit-config.yaml").exists():
        features["pre_commit"] = True

    return features


def detect_git_remote(target: Path) -> dict[str, str]:
    """Get GitHub org/repo from git remote origin. Returns empty dict if unavailable."""
    try:
        result = subprocess.run(
            ["git", "-C", str(target), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return {}

    parsed = parse_github_url(result.stdout.strip())
    if parsed:
        return {"org": parsed[0], "repo": parsed[1]}
    return {}


def detect_test_info(target: Path) -> dict[str, Any]:
    """Detect test framework, directory, and approximate test count."""
    # Look for test directories
    test_dir = None
    for candidate in ("tests", "test"):
        if (target / candidate).is_dir():
            test_dir = target / candidate
            break

    if test_dir is None:
        return {}

    # Count test functions in test_*.py files (skip symlinks, cap file size)
    count = 0
    for test_file in test_dir.rglob("test_*.py"):
        if test_file.is_symlink():
            continue
        try:
            if test_file.stat().st_size > _MAX_TEST_FILE_SIZE:
                logger.warning("Skipping oversized test file: %s", test_file)
                continue
            content = test_file.read_text(errors="replace")
        except (PermissionError, OSError):
            continue
        count += len(re.findall(r"^\s*def test_", content, re.MULTILINE))

    return {
        "test_framework": "pytest",
        "test_count": count,
    }


def inspect_project(target: Path) -> dict[str, Any]:
    """Run all detectors and assemble a spec dict."""
    spec: dict[str, Any] = {}

    # Language detection
    language = detect_language(target)
    if language:
        spec["language"] = language

    # Language-specific metadata
    if language == "python":
        metadata = detect_python_metadata(target)
        spec.update(metadata)

    # Features
    features = detect_features(target)
    if any(features.values()):
        spec["features"] = features

    # GitHub remote
    github = detect_git_remote(target)
    if github:
        spec["github"] = github

    # Recon section
    recon: dict[str, Any] = {}

    recon["existing_tools"] = detect_existing_tools(target)
    recon["has_pyproject_toml"] = (target / "pyproject.toml").exists()
    recon["has_github_dir"] = (target / ".github").is_dir()

    # Existing CI workflows
    wf_dir = target / ".github" / "workflows"
    if wf_dir.is_dir():
        recon["existing_ci"] = sorted(
            f.name for ext in ("*.yml", "*.yaml") for f in wf_dir.glob(ext)
        )

    # Test info
    test_info = detect_test_info(target)
    if test_info:
        recon.update(test_info)

    recon["updated_at"] = datetime.now(UTC).isoformat()

    spec["recon"] = recon

    return spec


def _extract_dep_names(deps: list[str]) -> list[str]:
    """Extract package names from dependency specifiers, stripping version constraints."""
    names: list[str] = []
    for dep in deps:
        if not isinstance(dep, str):
            continue
        m = _DEP_NAME_RE.match(dep)
        if m:
            names.append(m.group(1))
    return names
