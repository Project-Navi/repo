# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Project Navi

"""Tests for nboot init — project inspection and spec generation."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from navi_bootstrap.cli import cli
from navi_bootstrap.init import (
    detect_existing_tools,
    detect_features,
    detect_git_remote,
    detect_language,
    detect_python_metadata,
    detect_test_info,
    inspect_project,
    parse_github_url,
)
from navi_bootstrap.spec import validate_spec

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_pyproject(target: Path, content: str) -> None:
    (target / "pyproject.toml").write_text(content)


def _make_python_project(target: Path) -> None:
    """Create a realistic Python project directory."""
    target.mkdir(parents=True, exist_ok=True)
    _write_pyproject(
        target,
        """\
[project]
name = "acme-widget"
version = "1.2.0"
description = "A widget factory"
license = "MIT"
requires-python = ">=3.12"
authors = [
    { name = "Alice", email = "alice@example.com" }
]
dependencies = [
    "click>=8.1.0",
    "jinja2>=3.1.0",
]

[dependency-groups]
dev = [
    "pytest>=8.0.0",
    "ruff>=0.9.0",
    "mypy>=1.8.0",
]

[tool.ruff]
line-length = 100

[tool.mypy]
python_version = "3.12"

[tool.pytest.ini_options]
testpaths = ["tests"]
""",
    )

    # Source layout
    src = target / "src" / "acme_widget"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("")
    (src / "core.py").write_text("def hello(): pass\n")

    # Tests
    tests = target / "tests"
    tests.mkdir()
    (tests / "test_core.py").write_text("def test_hello(): pass\ndef test_goodbye(): pass\n")
    (tests / "test_utils.py").write_text("def test_parse(): pass\n")

    # Pre-commit
    (target / ".pre-commit-config.yaml").write_text("repos: []\n")

    # GitHub
    gh = target / ".github"
    gh.mkdir()
    (gh / "dependabot.yml").write_text("version: 2\n")
    wf = gh / "workflows"
    wf.mkdir()
    (wf / "tests.yml").write_text("name: Tests\n")


# ---------------------------------------------------------------------------
# TestDetectLanguage
# ---------------------------------------------------------------------------


class TestDetectLanguage:
    def test_python_from_pyproject_toml(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'x'\n")
        assert detect_language(tmp_path) == "python"

    def test_python_from_setup_py(self, tmp_path: Path) -> None:
        (tmp_path / "setup.py").write_text("from setuptools import setup\n")
        assert detect_language(tmp_path) == "python"

    def test_typescript_from_package_json(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text('{"name": "x"}\n')
        assert detect_language(tmp_path) == "typescript"

    def test_go_from_go_mod(self, tmp_path: Path) -> None:
        (tmp_path / "go.mod").write_text("module example.com/x\n")
        assert detect_language(tmp_path) == "go"

    def test_rust_from_cargo_toml(self, tmp_path: Path) -> None:
        (tmp_path / "Cargo.toml").write_text("[package]\nname = 'x'\n")
        assert detect_language(tmp_path) == "rust"

    def test_no_language_detected(self, tmp_path: Path) -> None:
        assert detect_language(tmp_path) is None

    def test_python_preferred_when_both_pyproject_and_package_json(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'x'\n")
        (tmp_path / "package.json").write_text('{"name": "x"}\n')
        assert detect_language(tmp_path) == "python"


# ---------------------------------------------------------------------------
# TestParseGithubUrl
# ---------------------------------------------------------------------------


class TestParseGithubUrl:
    def test_ssh_url(self) -> None:
        assert parse_github_url("git@github.com:MyOrg/my-repo.git") == ("MyOrg", "my-repo")

    def test_https_url(self) -> None:
        assert parse_github_url("https://github.com/MyOrg/my-repo.git") == ("MyOrg", "my-repo")

    def test_https_without_git_suffix(self) -> None:
        assert parse_github_url("https://github.com/MyOrg/my-repo") == ("MyOrg", "my-repo")

    def test_non_github_url(self) -> None:
        assert parse_github_url("git@gitlab.com:MyOrg/my-repo.git") is None

    def test_malformed_url(self) -> None:
        assert parse_github_url("not-a-url") is None

    def test_empty_string(self) -> None:
        assert parse_github_url("") is None


# ---------------------------------------------------------------------------
# TestDetectPythonMetadata
# ---------------------------------------------------------------------------


class TestDetectPythonMetadata:
    def test_extracts_name_version_description(self, tmp_path: Path) -> None:
        _write_pyproject(
            tmp_path,
            '[project]\nname = "acme"\nversion = "1.0.0"\ndescription = "A thing"\n',
        )
        result = detect_python_metadata(tmp_path)
        assert result["name"] == "acme"
        assert result["version"] == "1.0.0"
        assert result["description"] == "A thing"

    def test_extracts_python_version(self, tmp_path: Path) -> None:
        _write_pyproject(
            tmp_path,
            '[project]\nname = "x"\nrequires-python = ">=3.12"\n',
        )
        result = detect_python_metadata(tmp_path)
        assert result["python_version"] == "3.12"

    def test_extracts_python_version_with_upper_bound(self, tmp_path: Path) -> None:
        _write_pyproject(
            tmp_path,
            '[project]\nname = "x"\nrequires-python = ">=3.13,<4"\n',
        )
        result = detect_python_metadata(tmp_path)
        assert result["python_version"] == "3.13"

    def test_extracts_python_version_with_exclusion(self, tmp_path: Path) -> None:
        _write_pyproject(
            tmp_path,
            '[project]\nname = "x"\nrequires-python = "!=3.9,>=3.12"\n',
        )
        result = detect_python_metadata(tmp_path)
        assert result["python_version"] == "3.12"

    def test_extracts_runtime_dependencies(self, tmp_path: Path) -> None:
        _write_pyproject(
            tmp_path,
            '[project]\nname = "x"\ndependencies = ["click>=8.1", "jinja2>=3.1.0"]\n',
        )
        result = detect_python_metadata(tmp_path)
        assert result["dependencies"]["runtime"] == ["click", "jinja2"]

    def test_extracts_dev_deps_from_dependency_groups(self, tmp_path: Path) -> None:
        _write_pyproject(
            tmp_path,
            '[project]\nname = "x"\n\n[dependency-groups]\ndev = ["pytest>=8.0", "ruff>=0.9"]\n',
        )
        result = detect_python_metadata(tmp_path)
        assert result["dependencies"]["dev"] == ["pytest", "ruff"]

    def test_extracts_dev_deps_from_optional_dependencies(self, tmp_path: Path) -> None:
        _write_pyproject(
            tmp_path,
            '[project]\nname = "x"\n\n[project.optional-dependencies]\ndev = ["pytest>=8.0"]\n',
        )
        result = detect_python_metadata(tmp_path)
        assert result["dependencies"]["dev"] == ["pytest"]

    def test_prefers_dependency_groups_over_optional(self, tmp_path: Path) -> None:
        _write_pyproject(
            tmp_path,
            (
                '[project]\nname = "x"\n\n'
                "[dependency-groups]\ndev = ['ruff>=0.9']\n\n"
                "[project.optional-dependencies]\ndev = ['old-tool']\n"
            ),
        )
        result = detect_python_metadata(tmp_path)
        assert result["dependencies"]["dev"] == ["ruff"]

    def test_detects_src_layout(self, tmp_path: Path) -> None:
        _write_pyproject(tmp_path, '[project]\nname = "acme-widget"\n')
        pkg = tmp_path / "src" / "acme_widget"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text("")
        result = detect_python_metadata(tmp_path)
        assert result["structure"]["src_dir"] == "src/acme_widget"

    def test_detects_test_dir(self, tmp_path: Path) -> None:
        _write_pyproject(tmp_path, '[project]\nname = "x"\n')
        (tmp_path / "tests").mkdir()
        result = detect_python_metadata(tmp_path)
        assert result["structure"]["test_dir"] == "tests"

    def test_src_dir_prefers_package_matching_project_name(self, tmp_path: Path) -> None:
        _write_pyproject(tmp_path, '[project]\nname = "acme-widget"\n')
        # Two packages — acme_widget should be preferred over alpha_lib
        for name in ("alpha_lib", "acme_widget"):
            pkg = tmp_path / "src" / name
            pkg.mkdir(parents=True)
            (pkg / "__init__.py").write_text("")
        result = detect_python_metadata(tmp_path)
        assert result["structure"]["src_dir"] == "src/acme_widget"

    def test_detects_test_dir_from_pytest_config(self, tmp_path: Path) -> None:
        _write_pyproject(
            tmp_path,
            '[project]\nname = "x"\n\n[tool.pytest.ini_options]\ntestpaths = ["test"]\n',
        )
        (tmp_path / "test").mkdir()
        result = detect_python_metadata(tmp_path)
        assert result["structure"]["test_dir"] == "test"

    def test_extracts_author(self, tmp_path: Path) -> None:
        _write_pyproject(
            tmp_path,
            '[project]\nname = "x"\nauthors = [{name = "Alice", email = "a@b.com"}]\n',
        )
        result = detect_python_metadata(tmp_path)
        assert result["author"] == {"name": "Alice", "email": "a@b.com"}

    def test_extracts_license_string(self, tmp_path: Path) -> None:
        _write_pyproject(tmp_path, '[project]\nname = "x"\nlicense = "MIT"\n')
        result = detect_python_metadata(tmp_path)
        assert result["license"] == "MIT"

    def test_extracts_license_table(self, tmp_path: Path) -> None:
        _write_pyproject(tmp_path, '[project]\nname = "x"\nlicense = {text = "MIT"}\n')
        result = detect_python_metadata(tmp_path)
        assert result["license"] == "MIT"

    def test_no_pyproject_toml(self, tmp_path: Path) -> None:
        result = detect_python_metadata(tmp_path)
        assert result == {}

    def test_missing_project_section(self, tmp_path: Path) -> None:
        _write_pyproject(tmp_path, "[tool.ruff]\nline-length = 100\n")
        result = detect_python_metadata(tmp_path)
        assert result == {}

    def test_malformed_toml_returns_empty(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("{{not valid toml}}")
        result = detect_python_metadata(tmp_path)
        assert result == {}


# ---------------------------------------------------------------------------
# TestDetectExistingTools
# ---------------------------------------------------------------------------


class TestDetectExistingTools:
    def test_detects_ruff_in_tool_section(self, tmp_path: Path) -> None:
        _write_pyproject(tmp_path, "[tool.ruff]\nline-length = 100\n")
        result = detect_existing_tools(tmp_path)
        assert result["ruff"] is True

    def test_detects_mypy_in_tool_section(self, tmp_path: Path) -> None:
        _write_pyproject(tmp_path, '[tool.mypy]\npython_version = "3.12"\n')
        result = detect_existing_tools(tmp_path)
        assert result["mypy"] is True

    def test_detects_pre_commit(self, tmp_path: Path) -> None:
        (tmp_path / ".pre-commit-config.yaml").write_text("repos: []\n")
        result = detect_existing_tools(tmp_path)
        assert result["pre_commit"] is True

    def test_detects_dependabot(self, tmp_path: Path) -> None:
        gh = tmp_path / ".github"
        gh.mkdir()
        (gh / "dependabot.yml").write_text("version: 2\n")
        result = detect_existing_tools(tmp_path)
        assert result["dependabot"] is True

    def test_detects_bandit_in_dev_deps(self, tmp_path: Path) -> None:
        _write_pyproject(
            tmp_path,
            '[project]\nname = "x"\n\n[dependency-groups]\ndev = ["bandit>=1.7"]\n',
        )
        result = detect_existing_tools(tmp_path)
        assert result["bandit"] is True

    def test_no_tools_detected(self, tmp_path: Path) -> None:
        result = detect_existing_tools(tmp_path)
        assert result["ruff"] is False
        assert result["mypy"] is False
        assert result["pre_commit"] is False
        assert result["dependabot"] is False
        assert result["bandit"] is False


# ---------------------------------------------------------------------------
# TestDetectFeatures
# ---------------------------------------------------------------------------


class TestDetectFeatures:
    def test_detects_ci(self, tmp_path: Path) -> None:
        wf = tmp_path / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "tests.yml").write_text("name: CI\n")
        result = detect_features(tmp_path)
        assert result["ci"] is True

    def test_detects_pre_commit(self, tmp_path: Path) -> None:
        (tmp_path / ".pre-commit-config.yaml").write_text("repos: []\n")
        result = detect_features(tmp_path)
        assert result["pre_commit"] is True

    def test_detects_ci_yaml_extension(self, tmp_path: Path) -> None:
        wf = tmp_path / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "tests.yaml").write_text("name: CI\n")
        result = detect_features(tmp_path)
        assert result["ci"] is True

    def test_no_features(self, tmp_path: Path) -> None:
        result = detect_features(tmp_path)
        assert result["ci"] is False
        assert result["pre_commit"] is False


# ---------------------------------------------------------------------------
# TestDetectGitRemote
# ---------------------------------------------------------------------------


class TestDetectGitRemote:
    def test_detects_github_remote(self, tmp_path: Path) -> None:
        subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(tmp_path),
                "remote",
                "add",
                "origin",
                "git@github.com:MyOrg/my-repo.git",
            ],
            check=True,
            capture_output=True,
        )
        result = detect_git_remote(tmp_path)
        assert result == {"org": "MyOrg", "repo": "my-repo"}

    def test_no_git_repo(self, tmp_path: Path) -> None:
        result = detect_git_remote(tmp_path)
        assert result == {}

    def test_non_github_remote(self, tmp_path: Path) -> None:
        subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(tmp_path),
                "remote",
                "add",
                "origin",
                "git@gitlab.com:MyOrg/my-repo.git",
            ],
            check=True,
            capture_output=True,
        )
        result = detect_git_remote(tmp_path)
        assert result == {}


# ---------------------------------------------------------------------------
# TestDetectTestInfo
# ---------------------------------------------------------------------------


class TestDetectTestInfo:
    def test_finds_test_dir_and_counts(self, tmp_path: Path) -> None:
        tests = tmp_path / "tests"
        tests.mkdir()
        (tests / "test_a.py").write_text("def test_one(): pass\ndef test_two(): pass\n")
        (tests / "test_b.py").write_text("def test_three(): pass\n")
        result = detect_test_info(tmp_path)
        assert result["test_framework"] == "pytest"
        assert result["test_count"] == 3

    def test_no_tests(self, tmp_path: Path) -> None:
        result = detect_test_info(tmp_path)
        assert result == {}

    def test_ignores_non_test_files(self, tmp_path: Path) -> None:
        tests = tmp_path / "tests"
        tests.mkdir()
        (tests / "conftest.py").write_text("import pytest\n")
        (tests / "test_core.py").write_text("def test_it(): pass\n")
        (tests / "helpers.py").write_text("def helper(): pass\n")
        result = detect_test_info(tmp_path)
        assert result["test_count"] == 1


# ---------------------------------------------------------------------------
# TestInspectProject
# ---------------------------------------------------------------------------


class TestInspectProject:
    def test_full_python_project(self, tmp_path: Path) -> None:
        _make_python_project(tmp_path)
        result = inspect_project(tmp_path)
        assert result["name"] == "acme-widget"
        assert result["language"] == "python"
        assert result["python_version"] == "3.12"
        assert result["structure"]["src_dir"] == "src/acme_widget"
        assert result["structure"]["test_dir"] == "tests"
        assert result["features"]["ci"] is True
        assert result["features"]["pre_commit"] is True
        assert result["recon"]["existing_tools"]["ruff"] is True
        assert result["recon"]["test_count"] == 3

    def test_empty_directory(self, tmp_path: Path) -> None:
        result = inspect_project(tmp_path)
        # Should still return a dict, just sparse
        assert isinstance(result, dict)
        assert "recon" in result

    def test_produces_valid_spec_for_full_project(self, tmp_path: Path) -> None:
        _make_python_project(tmp_path)
        result = inspect_project(tmp_path)
        # Must pass schema validation
        validate_spec(result)

    def test_detects_existing_ci_workflows(self, tmp_path: Path) -> None:
        wf = tmp_path / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "tests.yml").write_text("name: CI\n")
        (wf / "lint.yml").write_text("name: Lint\n")
        result = inspect_project(tmp_path)
        assert sorted(result["recon"]["existing_ci"]) == ["lint.yml", "tests.yml"]

    def test_sets_has_pyproject_toml(self, tmp_path: Path) -> None:
        _write_pyproject(tmp_path, '[project]\nname = "x"\n')
        result = inspect_project(tmp_path)
        assert result["recon"]["has_pyproject_toml"] is True

    def test_sets_has_github_dir(self, tmp_path: Path) -> None:
        (tmp_path / ".github").mkdir()
        result = inspect_project(tmp_path)
        assert result["recon"]["has_github_dir"] is True


# ---------------------------------------------------------------------------
# TestInitCommand (CLI integration)
# ---------------------------------------------------------------------------


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


class TestInitCommand:
    def test_init_creates_spec_file(self, runner: CliRunner, tmp_path: Path) -> None:
        _make_python_project(tmp_path)
        result = runner.invoke(cli, ["init", "--target", str(tmp_path), "--yes"])
        assert result.exit_code == 0, result.output
        spec_path = tmp_path / "nboot-spec.json"
        assert spec_path.exists()
        spec = json.loads(spec_path.read_text())
        assert spec["name"] == "acme-widget"

    def test_init_default_output_path(self, runner: CliRunner, tmp_path: Path) -> None:
        _make_python_project(tmp_path)
        result = runner.invoke(cli, ["init", "--target", str(tmp_path), "--yes"])
        assert result.exit_code == 0
        assert (tmp_path / "nboot-spec.json").exists()

    def test_init_custom_output_path(self, runner: CliRunner, tmp_path: Path) -> None:
        _make_python_project(tmp_path)
        out = tmp_path / "custom.json"
        result = runner.invoke(cli, ["init", "--target", str(tmp_path), "--out", str(out), "--yes"])
        assert result.exit_code == 0
        assert out.exists()

    def test_init_yes_skips_prompts(self, runner: CliRunner, tmp_path: Path) -> None:
        _make_python_project(tmp_path)
        result = runner.invoke(cli, ["init", "--target", str(tmp_path), "--yes"])
        assert result.exit_code == 0
        # Should not contain prompt text
        assert "Write spec?" not in result.output

    def test_init_interactive_confirms(self, runner: CliRunner, tmp_path: Path) -> None:
        _make_python_project(tmp_path)
        result = runner.invoke(cli, ["init", "--target", str(tmp_path)], input="y\n")
        assert result.exit_code == 0
        assert (tmp_path / "nboot-spec.json").exists()

    def test_init_interactive_decline(self, runner: CliRunner, tmp_path: Path) -> None:
        _make_python_project(tmp_path)
        result = runner.invoke(cli, ["init", "--target", str(tmp_path)], input="n\n")
        assert result.exit_code == 0
        assert not (tmp_path / "nboot-spec.json").exists()

    def test_init_prompts_for_missing_language(self, runner: CliRunner, tmp_path: Path) -> None:
        # Empty dir — no language markers
        result = runner.invoke(
            cli, ["init", "--target", str(tmp_path)], input="python\ntest-project\ny\n"
        )
        assert result.exit_code == 0
        spec = json.loads((tmp_path / "nboot-spec.json").read_text())
        assert spec["language"] == "python"
        assert spec["name"] == "test-project"

    def test_init_yes_fails_without_language(self, runner: CliRunner, tmp_path: Path) -> None:
        # Empty dir + --yes = can't proceed without required fields
        result = runner.invoke(cli, ["init", "--target", str(tmp_path), "--yes"])
        assert result.exit_code != 0
        assert "Could not detect project language" in result.output

    def test_init_yes_fails_without_name(self, runner: CliRunner, tmp_path: Path) -> None:
        # Language detected but no [project] section — name can't be detected
        (tmp_path / "pyproject.toml").write_text("[tool.ruff]\nline-length = 100\n")
        result = runner.invoke(cli, ["init", "--target", str(tmp_path), "--yes"])
        assert result.exit_code != 0
        assert "Could not detect project name" in result.output

    def test_init_generated_spec_validates(self, runner: CliRunner, tmp_path: Path) -> None:
        _make_python_project(tmp_path)
        runner.invoke(cli, ["init", "--target", str(tmp_path), "--yes"])
        spec = json.loads((tmp_path / "nboot-spec.json").read_text())
        # Should not raise
        validate_spec(spec)

    def test_init_displays_detected_info(self, runner: CliRunner, tmp_path: Path) -> None:
        _make_python_project(tmp_path)
        result = runner.invoke(cli, ["init", "--target", str(tmp_path), "--yes"])
        assert "acme-widget" in result.output
        assert "python" in result.output
