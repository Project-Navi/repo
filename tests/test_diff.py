# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Project Navi

"""Tests for plan --diff: preview rendered output as unified diff."""

from __future__ import annotations

from pathlib import Path

from navi_bootstrap.engine import RenderedFile


class TestDiffNewFile:
    """New files (not on disk) show as full additions."""

    def test_new_file_produces_diff_lines(self) -> None:
        from navi_bootstrap.diff import compute_diffs

        rendered = [RenderedFile(dest="README.md", content="# Hello\n\nWorld\n")]
        target = Path("/nonexistent")

        diffs = compute_diffs(rendered, target, pack_name="test-pack")

        assert len(diffs) == 1
        assert diffs[0].dest == "README.md"
        assert diffs[0].is_new is True
        # Every content line should appear as an addition
        assert "+# Hello" in diffs[0].diff_text
        assert "+World" in diffs[0].diff_text

    def test_new_file_header_shows_dev_null(self) -> None:
        from navi_bootstrap.diff import compute_diffs

        rendered = [RenderedFile(dest="hello.txt", content="hi\n")]
        target = Path("/nonexistent")

        diffs = compute_diffs(rendered, target, pack_name="test-pack")

        assert "--- /dev/null" in diffs[0].diff_text
        assert "+++ b/hello.txt" in diffs[0].diff_text


class TestDiffUnchangedFile:
    """Files identical to what's on disk produce no diff."""

    def test_identical_file_produces_no_diff(self, tmp_path: Path) -> None:
        from navi_bootstrap.diff import compute_diffs

        (tmp_path / "hello.txt").write_text("Hello world\n")
        rendered = [RenderedFile(dest="hello.txt", content="Hello world\n")]

        diffs = compute_diffs(rendered, tmp_path, pack_name="test-pack")

        assert len(diffs) == 0


class TestDiffChangedFile:
    """Files that differ from what's on disk show a unified diff."""

    def test_changed_file_shows_diff(self, tmp_path: Path) -> None:
        from navi_bootstrap.diff import compute_diffs

        (tmp_path / "hello.txt").write_text("Hello world\n")
        rendered = [RenderedFile(dest="hello.txt", content="Hello universe\n")]

        diffs = compute_diffs(rendered, tmp_path, pack_name="test-pack")

        assert len(diffs) == 1
        assert diffs[0].is_new is False
        assert "-Hello world" in diffs[0].diff_text
        assert "+Hello universe" in diffs[0].diff_text

    def test_changed_file_header_shows_paths(self, tmp_path: Path) -> None:
        from navi_bootstrap.diff import compute_diffs

        (tmp_path / "hello.txt").write_text("old\n")
        rendered = [RenderedFile(dest="hello.txt", content="new\n")]

        diffs = compute_diffs(rendered, tmp_path, pack_name="test-pack")

        assert "--- a/hello.txt" in diffs[0].diff_text
        assert "+++ b/hello.txt" in diffs[0].diff_text


class TestDiffAppendMode:
    """Append-mode files compute the full result with markers, then diff."""

    def test_append_to_existing_file(self, tmp_path: Path) -> None:
        from navi_bootstrap.diff import compute_diffs

        (tmp_path / "pyproject.toml").write_text('[project]\nname = "foo"\n')
        rendered = [
            RenderedFile(
                dest="pyproject.toml",
                content="[tool.ruff]\nline-length = 100\n",
                mode="append",
            )
        ]

        diffs = compute_diffs(rendered, tmp_path, pack_name="test-pack")

        assert len(diffs) == 1
        # Should show the marker block being added
        assert "+# --- nboot: test-pack ---" in diffs[0].diff_text
        assert "+line-length = 100" in diffs[0].diff_text

    def test_append_replaces_existing_markers(self, tmp_path: Path) -> None:
        from navi_bootstrap.diff import compute_diffs

        existing = (
            '[project]\nname = "foo"\n'
            "# --- nboot: test-pack ---\n"
            "old-content\n"
            "# --- end nboot: test-pack ---\n"
        )
        (tmp_path / "pyproject.toml").write_text(existing)
        rendered = [
            RenderedFile(
                dest="pyproject.toml",
                content="new-content\n",
                mode="append",
            )
        ]

        diffs = compute_diffs(rendered, tmp_path, pack_name="test-pack")

        assert len(diffs) == 1
        assert "-old-content" in diffs[0].diff_text
        assert "+new-content" in diffs[0].diff_text

    def test_append_no_change_produces_no_diff(self, tmp_path: Path) -> None:
        from navi_bootstrap.diff import compute_diffs

        existing = (
            '[project]\nname = "foo"\n'
            "# --- nboot: test-pack ---\n"
            "[tool.ruff]\nline-length = 100\n"
            "# --- end nboot: test-pack ---\n"
        )
        (tmp_path / "pyproject.toml").write_text(existing)
        rendered = [
            RenderedFile(
                dest="pyproject.toml",
                content="[tool.ruff]\nline-length = 100\n",
                mode="append",
            )
        ]

        diffs = compute_diffs(rendered, tmp_path, pack_name="test-pack")

        assert len(diffs) == 0


class TestDiffMultipleFiles:
    """Multiple files: only changed/new files appear in output."""

    def test_mixed_new_changed_unchanged(self, tmp_path: Path) -> None:
        from navi_bootstrap.diff import compute_diffs

        # Existing unchanged file
        (tmp_path / "unchanged.txt").write_text("same\n")
        # Existing changed file
        (tmp_path / "changed.txt").write_text("old\n")

        rendered = [
            RenderedFile(dest="unchanged.txt", content="same\n"),
            RenderedFile(dest="changed.txt", content="new\n"),
            RenderedFile(dest="brand-new.txt", content="fresh\n"),
        ]

        diffs = compute_diffs(rendered, tmp_path, pack_name="test-pack")

        assert len(diffs) == 2
        dests = {d.dest for d in diffs}
        assert dests == {"changed.txt", "brand-new.txt"}


class TestDiffResult:
    """DiffResult dataclass fields."""

    def test_diff_result_has_required_fields(self) -> None:
        from navi_bootstrap.diff import DiffResult

        dr = DiffResult(dest="foo.txt", diff_text="some diff", is_new=True)
        assert dr.dest == "foo.txt"
        assert dr.diff_text == "some diff"
        assert dr.is_new is True
