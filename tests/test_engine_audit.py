# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Project Navi

"""Adversarial audit: engine edge cases found during code review."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from navi_bootstrap.engine import (
    RenderedFile,
    _eval_condition,
    _resolve_dotpath,
    _write_append,
    plan,
    write_rendered,
)

# --- Bug #1: Multi-pack append corruption ---


class TestMultiPackAppend:
    """When two packs append to the same file, updating one must not destroy the other."""

    def test_second_pack_preserves_first_pack_markers(self, tmp_path: Path) -> None:
        """Appending pack-b must not remove pack-a's block."""
        target = tmp_path / "pyproject.toml"
        target.write_text(
            '[project]\nname = "test"\n'
            "# --- nboot: pack-a ---\n"
            "content-from-a\n"
            "# --- end nboot: pack-a ---\n"
        )

        # Now append as pack-b
        _write_append(target, "content-from-b\n", "pack-b")

        result = target.read_text()
        # pack-a's block MUST still be present
        assert "# --- nboot: pack-a ---" in result
        assert "content-from-a" in result
        # pack-b's block must also be present
        assert "# --- nboot: pack-b ---" in result
        assert "content-from-b" in result

    def test_updating_pack_b_only_replaces_pack_b(self, tmp_path: Path) -> None:
        """Re-appending pack-b replaces pack-b only, leaves pack-a intact."""
        target = tmp_path / "pyproject.toml"
        target.write_text(
            '[project]\nname = "test"\n'
            "# --- nboot: pack-a ---\n"
            "content-from-a\n"
            "# --- end nboot: pack-a ---\n"
            "# --- nboot: pack-b ---\n"
            "old-content-from-b\n"
            "# --- end nboot: pack-b ---\n"
        )

        _write_append(target, "new-content-from-b\n", "pack-b")

        result = target.read_text()
        # pack-a untouched
        assert "# --- nboot: pack-a ---" in result
        assert "content-from-a" in result
        # pack-b updated
        assert "new-content-from-b" in result
        assert "old-content-from-b" not in result
        # Only one block per pack
        assert result.count("# --- nboot: pack-a ---") == 1
        assert result.count("# --- nboot: pack-b ---") == 1

    def test_write_rendered_multiple_packs_same_file(self, tmp_path: Path) -> None:
        """write_rendered called for two packs in sequence preserves both."""
        target = tmp_path / "config.toml"
        target.write_text('[base]\nkey = "val"\n')

        # First pack appends
        files_a = [RenderedFile(dest="config.toml", content="from-a\n", mode="append")]
        write_rendered(files_a, tmp_path, "pack-a")

        # Second pack appends
        files_b = [RenderedFile(dest="config.toml", content="from-b\n", mode="append")]
        write_rendered(files_b, tmp_path, "pack-b")

        result = target.read_text()
        assert "from-a" in result
        assert "from-b" in result
        assert "# --- nboot: pack-a ---" in result
        assert "# --- nboot: pack-b ---" in result


# --- Bug #2: Pack name with regex metacharacters ---


class TestPackNameRegexSafety:
    """Pack names with regex metacharacters must not corrupt marker matching."""

    def test_pack_name_with_dots(self, tmp_path: Path) -> None:
        target = tmp_path / "config.toml"
        target.write_text("")
        _write_append(target, "content\n", "my.pack.v2")

        result = target.read_text()
        assert "# --- nboot: my.pack.v2 ---" in result

        # Re-append should replace, not duplicate
        _write_append(target, "updated\n", "my.pack.v2")
        result = target.read_text()
        assert result.count("# --- nboot: my.pack.v2 ---") == 1
        assert "updated" in result
        assert "content" not in result

    def test_pack_name_with_plus(self, tmp_path: Path) -> None:
        target = tmp_path / "config.toml"
        target.write_text("")
        _write_append(target, "content\n", "pack+extra")

        _write_append(target, "new\n", "pack+extra")
        result = target.read_text()
        assert result.count("# --- nboot: pack+extra ---") == 1
        assert "new" in result


# --- Bug #3: _eval_condition with double negation ---


class TestEvalConditionEdgeCases:
    """Edge cases in condition evaluation."""

    def test_double_negation_cancels_out(self) -> None:
        """!!spec.features.ci should be equivalent to spec.features.ci (truthy)."""
        spec: dict[str, Any] = {"features": {"ci": True}}
        # !! = not not = identity
        assert _eval_condition("!!spec.features.ci", spec) is True

    def test_double_negation_on_falsy(self) -> None:
        spec: dict[str, Any] = {"features": {"ci": False}}
        assert _eval_condition("!!spec.features.ci", spec) is False

    def test_empty_condition_does_not_crash(self) -> None:
        """Empty string condition should not raise."""
        spec: dict[str, Any] = {"features": {}}
        # Should return some boolean without crashing
        result = _eval_condition("", spec)
        assert isinstance(result, bool)

    def test_single_negation_works(self) -> None:
        spec: dict[str, Any] = {"features": {"ci": True}}
        assert _eval_condition("!spec.features.ci", spec) is False

    def test_missing_path_is_falsy(self) -> None:
        spec: dict[str, Any] = {}
        assert _eval_condition("spec.nonexistent.deep.path", spec) is False


# --- Bug #4: _resolve_dotpath edge cases ---


class TestResolveDotpathEdgeCases:
    def test_empty_string_path(self) -> None:
        obj = {"spec": {"name": "test"}}
        result = _resolve_dotpath(obj, "")
        # Empty path splits to [""], dict.get("") returns None
        assert result is None

    def test_none_in_chain(self) -> None:
        obj = {"spec": None}
        result = _resolve_dotpath(obj, "spec.name")
        assert result is None

    def test_list_in_chain(self) -> None:
        obj = {"spec": [1, 2, 3]}
        result = _resolve_dotpath(obj, "spec.name")
        assert result is None


# --- Bug #5: plan() with empty/edge-case manifests ---


class TestPlanEdgeCases:
    def test_empty_templates_list(self) -> None:
        manifest = {"name": "test", "templates": [], "conditions": {}, "loops": {}}
        spec: dict[str, Any] = {"name": "test", "language": "python"}
        result = plan(manifest, spec, Path("/unused"))
        assert result.entries == []

    def test_missing_templates_key(self) -> None:
        manifest: dict[str, Any] = {"name": "test", "conditions": {}, "loops": {}}
        spec: dict[str, Any] = {"name": "test", "language": "python"}
        result = plan(manifest, spec, Path("/unused"))
        assert result.entries == []

    def test_loop_over_missing_path_produces_no_entries(self) -> None:
        manifest = {
            "name": "test",
            "templates": [{"src": "mod.j2", "dest": "src/{{ item.name }}.py"}],
            "conditions": {},
            "loops": {"mod.j2": {"over": "spec.nonexistent", "as": "item"}},
        }
        spec: dict[str, Any] = {"name": "test", "language": "python"}
        result = plan(manifest, spec, Path("/unused"))
        assert result.entries == []

    def test_all_conditions_false_produces_empty_plan(self) -> None:
        manifest = {
            "name": "test",
            "templates": [{"src": "a.j2", "dest": "a.txt"}],
            "conditions": {"a.j2": "spec.features.nonexistent"},
            "loops": {},
        }
        spec: dict[str, Any] = {"name": "test", "language": "python", "features": {}}
        result = plan(manifest, spec, Path("/unused"))
        assert result.entries == []
