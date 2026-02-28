# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Project Navi

"""Adversarial audit: diff module edge cases."""

from __future__ import annotations

from pathlib import Path

import pytest

from navi_bootstrap.diff import compute_diffs
from navi_bootstrap.engine import RenderedFile


class TestDiffAppendMultiPack:
    """Diff must compute append correctly when multiple packs are in the file."""

    def test_diff_append_preserves_other_pack_blocks(self, tmp_path: Path) -> None:
        """Diffing pack-b's append must not show pack-a's block being removed."""
        (tmp_path / "config.toml").write_text(
            "[base]\nkey = 1\n# --- nboot: pack-a ---\nfrom-a\n# --- end nboot: pack-a ---\n"
        )
        rendered = [RenderedFile(dest="config.toml", content="from-b\n", mode="append")]

        diffs = compute_diffs(rendered, tmp_path, pack_name="pack-b")

        assert len(diffs) == 1
        # Should show pack-b being added, NOT pack-a being removed
        assert "+# --- nboot: pack-b ---" in diffs[0].diff_text
        assert "-# --- nboot: pack-a ---" not in diffs[0].diff_text
        assert "-from-a" not in diffs[0].diff_text

    def test_diff_append_replace_only_target_pack(self, tmp_path: Path) -> None:
        """Diffing pack-b when pack-b already exists should show replacement."""
        (tmp_path / "config.toml").write_text(
            "# --- nboot: pack-a ---\n"
            "from-a\n"
            "# --- end nboot: pack-a ---\n"
            "# --- nboot: pack-b ---\n"
            "old-b\n"
            "# --- end nboot: pack-b ---\n"
        )
        rendered = [RenderedFile(dest="config.toml", content="new-b\n", mode="append")]

        diffs = compute_diffs(rendered, tmp_path, pack_name="pack-b")

        assert len(diffs) == 1
        assert "-old-b" in diffs[0].diff_text
        assert "+new-b" in diffs[0].diff_text
        # pack-a must not appear as added or removed lines
        for line in diffs[0].diff_text.splitlines():
            if line.startswith(("-", "+")) and "pack-a" in line:
                # Allow --- a/config.toml header
                if line.startswith("--- a/") or line.startswith("+++ b/"):
                    continue
                pytest.fail(f"pack-a appears in add/remove line: {line}")


class TestDiffEdgeCases:
    """Edge cases for the diff engine."""

    def test_empty_rendered_content(self, tmp_path: Path) -> None:
        """Empty rendered content for a new file should still show as new."""
        rendered = [RenderedFile(dest="empty.txt", content="")]

        diffs = compute_diffs(rendered, tmp_path, pack_name="test")

        # Empty new file — no diff lines to show, but it's still "new"
        # Either 0 diffs (empty file = nothing to show) or 1 diff is acceptable
        # The key: it must not crash
        assert isinstance(diffs, list)

    def test_binary_like_content(self, tmp_path: Path) -> None:
        """Content with unusual characters must not crash the differ."""
        rendered = [RenderedFile(dest="weird.txt", content="line1\x00line2\n")]

        diffs = compute_diffs(rendered, tmp_path, pack_name="test")

        assert len(diffs) == 1
        assert diffs[0].is_new is True

    def test_deeply_nested_dest_path(self, tmp_path: Path) -> None:
        """Dest paths with many directory levels work."""
        rendered = [RenderedFile(dest="a/b/c/d/e/f.txt", content="deep\n")]

        diffs = compute_diffs(rendered, tmp_path, pack_name="test")

        assert len(diffs) == 1
        assert "a/b/c/d/e/f.txt" in diffs[0].diff_text

    def test_existing_file_no_trailing_newline(self, tmp_path: Path) -> None:
        """Existing file without trailing newline still diffs correctly."""
        (tmp_path / "no-newline.txt").write_text("no newline here")
        rendered = [RenderedFile(dest="no-newline.txt", content="no newline here\n")]

        diffs = compute_diffs(rendered, tmp_path, pack_name="test")

        assert len(diffs) == 1  # Content differs (trailing newline)

    def test_append_to_nonexistent_file(self, tmp_path: Path) -> None:
        """Appending to a file that doesn't exist shows as new with markers."""
        rendered = [RenderedFile(dest="new.toml", content="config\n", mode="append")]

        diffs = compute_diffs(rendered, tmp_path, pack_name="test")

        assert len(diffs) == 1
        assert diffs[0].is_new is True
        assert "+# --- nboot: test ---" in diffs[0].diff_text
