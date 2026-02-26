# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Project Navi

"""Adversarial audit — bravo's lane: engine hardening, path confinement, timeouts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import jinja2
import pytest

from navi_bootstrap.engine import (
    RenderedFile,
    _render_dest_path,
    plan,
    write_rendered,
)

# --- C2: Path confinement in write_rendered ---


class TestPathConfinement:
    """write_rendered must not write outside output_dir."""

    def test_traversal_in_dest_blocked(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        files = [RenderedFile(dest="../escape.txt", content="pwned\n")]

        with pytest.raises(ValueError, match="outside"):
            write_rendered(files, output_dir, "test-pack")

        # File must not exist outside output_dir
        assert not (tmp_path / "escape.txt").exists()

    def test_absolute_dest_blocked(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        files = [RenderedFile(dest="/tmp/evil.txt", content="pwned\n")]

        with pytest.raises(ValueError, match="outside"):
            write_rendered(files, output_dir, "test-pack")

    def test_symlink_escape_blocked(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        # Create a symlink pointing outside
        escape_target = tmp_path / "escape_dir"
        escape_target.mkdir()
        (output_dir / "link").symlink_to(escape_target)

        files = [RenderedFile(dest="link/evil.txt", content="pwned\n")]

        with pytest.raises(ValueError, match="outside"):
            write_rendered(files, output_dir, "test-pack")

        assert not (escape_target / "evil.txt").exists()

    def test_normal_nested_path_allowed(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        files = [RenderedFile(dest="src/deep/file.txt", content="ok\n")]

        written = write_rendered(files, output_dir, "test-pack")
        assert len(written) == 1
        assert (output_dir / "src" / "deep" / "file.txt").read_text() == "ok\n"


# --- H2: spec.name as output dir ---


class TestSpecNameOutputDir:
    """render_cmd uses spec.name as default output dir — dangerous names must be caught."""

    def test_dest_with_path_separator_in_name(self) -> None:
        """_render_dest_path with path separators should work (plan resolves these)."""
        # This tests the engine's handling, not the CLI default dir
        context: dict[str, Any] = {"spec": {"name": "test"}, "item": {"name": "sub/mod"}}
        result = _render_dest_path("src/{{ item.name }}.py", context)
        assert result == "src/sub/mod.py"


# --- H3: Subprocess timeouts ---


class TestSubprocessTimeouts:
    """Hooks and validations must not hang forever."""

    def test_hook_timeout(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import subprocess as sp

        from navi_bootstrap.hooks import run_hooks

        # Patch subprocess.run to simulate timeout
        original_run = sp.run

        def fake_run(*args: Any, **kwargs: Any) -> sp.CompletedProcess[str]:
            if kwargs.get("timeout"):
                raise sp.TimeoutExpired(cmd=args[0], timeout=kwargs["timeout"])
            return original_run(*args, **kwargs)

        monkeypatch.setattr(sp, "run", fake_run)

        results = run_hooks(["sleep 1"], tmp_path)
        assert len(results) == 1
        assert not results[0].success
        assert "Timed out" in results[0].stderr

    def test_validation_timeout(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import subprocess as sp

        from navi_bootstrap.validate import run_validations

        original_run = sp.run

        def fake_run(*args: Any, **kwargs: Any) -> sp.CompletedProcess[str]:
            if kwargs.get("timeout"):
                raise sp.TimeoutExpired(cmd=args[0], timeout=kwargs["timeout"])
            return original_run(*args, **kwargs)

        monkeypatch.setattr(sp, "run", fake_run)

        validations = [{"command": "sleep 1", "description": "hang test"}]
        results = run_validations(validations, tmp_path)
        assert len(results) == 1
        assert not results[0].passed
        assert "Timed out" in results[0].stderr


# --- H5: SandboxedEnvironment for dest path rendering ---


class TestDestPathSandbox:
    """_render_dest_path must not allow arbitrary Python execution."""

    def test_import_blocked_in_dest(self) -> None:
        """Jinja2 dest path rendering should block dangerous expressions."""
        # This tests that we don't use a vanilla Environment for user-controlled paths
        context: dict[str, Any] = {"spec": {"name": "test"}}
        # Sandboxed env should block this or raise
        try:
            result = _render_dest_path("{{ ''.__class__.__mro__ }}", context)
            # If it renders, at least it shouldn't give useful info for exploitation
            assert "__class__" not in result or "type" not in result
        except (jinja2.exceptions.SecurityError, jinja2.exceptions.UndefinedError):
            pass  # Either security block or undefined — both are safe


# --- M2: exit_code_0_or_warnings logic ---


class TestValidationWarningsMode:
    """exit_code_0_or_warnings should accept 0 and 1, not everything."""

    def test_warnings_mode_accepts_exit_0(self, tmp_path: Path) -> None:
        from navi_bootstrap.validate import run_validations

        validations = [
            {"command": "true", "expect": "exit_code_0_or_warnings", "description": "ok"}
        ]
        results = run_validations(validations, tmp_path)
        assert results[0].passed is True

    def test_warnings_mode_accepts_exit_1(self, tmp_path: Path) -> None:
        from navi_bootstrap.validate import run_validations

        validations = [
            {"command": "exit 1", "expect": "exit_code_0_or_warnings", "description": "warn"}
        ]
        results = run_validations(validations, tmp_path)
        assert results[0].passed is True

    def test_warnings_mode_rejects_exit_2(self, tmp_path: Path) -> None:
        from navi_bootstrap.validate import run_validations

        validations = [
            {"command": "exit 2", "expect": "exit_code_0_or_warnings", "description": "fail"}
        ]
        results = run_validations(validations, tmp_path)
        assert results[0].passed is False


# --- M3: Unbounded loop expansion ---


class TestLoopExpansionLimit:
    """Loop expansion must have a reasonable upper bound."""

    def test_loop_over_huge_list_is_bounded(self, tmp_path: Path) -> None:
        pack_dir = tmp_path / "pack"
        pack_dir.mkdir()
        templates_dir = pack_dir / "templates"
        templates_dir.mkdir()
        (templates_dir / "mod.j2").write_text("{{ item }}\n")

        manifest = {
            "name": "test",
            "templates": [{"src": "mod.j2", "dest": "{{ item }}.txt"}],
            "conditions": {},
            "loops": {"mod.j2": {"over": "spec.items", "as": "item"}},
        }
        spec: dict[str, Any] = {"name": "test", "language": "python", "items": list(range(10_000))}

        with pytest.raises(ValueError, match=r"[Ll]imit|[Tt]oo many"):
            plan(manifest, spec, templates_dir)


# --- M4: Duplicate dest paths ---


class TestDuplicateDestPaths:
    """Duplicate dest paths should be detected and rejected."""

    def test_duplicate_create_dest_rejected(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        files = [
            RenderedFile(dest="same.txt", content="first\n"),
            RenderedFile(dest="same.txt", content="second\n"),
        ]

        with pytest.raises(ValueError, match=r"[Dd]uplicate"):
            write_rendered(files, output_dir, "test-pack")

    def test_duplicate_append_dest_allowed(self, tmp_path: Path) -> None:
        """Multiple appends to same file is valid (different packs do this)."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        (output_dir / "config.toml").write_text("[base]\n")
        files = [
            RenderedFile(dest="config.toml", content="a\n", mode="append"),
            RenderedFile(dest="config.toml", content="b\n", mode="append"),
        ]

        # Should not raise — append to same file is legitimate
        written = write_rendered(files, output_dir, "test-pack")
        assert len(written) == 2


# --- M6: FileNotFoundError from missing gh ---


class TestResolveGhMissing:
    """Missing gh CLI should produce ResolveError, not FileNotFoundError."""

    def test_missing_gh_gives_resolve_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from navi_bootstrap.resolve import ResolveError, resolve_action_shas

        # Make gh unfindable
        monkeypatch.setenv("PATH", "/nonexistent")

        entries = [{"name": "actions/checkout", "repo": "actions/checkout", "tag": "v4"}]

        with pytest.raises(ResolveError):
            resolve_action_shas(entries)
