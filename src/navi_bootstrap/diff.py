# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Project Navi

"""Diff engine: compare rendered output against existing files on disk."""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from pathlib import Path

from navi_bootstrap.engine import RenderedFile

_MARKER_START = "# --- nboot: {pack_name} ---"
_MARKER_END = "# --- end nboot: {pack_name} ---"
_MARKER_RE = re.compile(
    r"# --- nboot: (?P<pack>\S+) ---\n.*?# --- end nboot: (?P=pack) ---\n?",
    re.DOTALL,
)


@dataclass
class DiffResult:
    """A single file's diff output."""

    dest: str
    diff_text: str
    is_new: bool


def _pack_marker_re(pack_name: str) -> re.Pattern[str]:
    """Build a regex that matches only the given pack's marker block."""
    escaped = re.escape(pack_name)
    return re.compile(
        rf"# --- nboot: {escaped} ---\n.*?# --- end nboot: {escaped} ---\n?",
        re.DOTALL,
    )


def _compute_append_content(existing: str, rendered: str, pack_name: str) -> str:
    """Compute what append mode would produce, matching engine._write_append logic."""
    marker_start = _MARKER_START.format(pack_name=pack_name)
    marker_end = _MARKER_END.format(pack_name=pack_name)
    block = f"{marker_start}\n{rendered}{marker_end}\n"

    if marker_start in existing:
        pack_re = _pack_marker_re(pack_name)
        new_content = pack_re.sub("", existing, count=1)
        if new_content and not new_content.endswith("\n"):
            new_content += "\n"
        return new_content + block
    else:
        if existing and not existing.endswith("\n"):
            existing += "\n"
        return existing + block


def compute_diffs(
    rendered_files: list[RenderedFile],
    target: Path,
    *,
    pack_name: str,
) -> list[DiffResult]:
    """Compare rendered files against what exists on disk.

    Returns a list of DiffResult for files that would change.
    Unchanged files are omitted.
    """
    results: list[DiffResult] = []

    for rf in rendered_files:
        file_path = target / rf.dest
        is_new = not file_path.exists()

        if is_new:
            # New file: diff against empty
            # For append mode, wrap in marker blocks like the engine would
            if rf.mode == "append":
                marker_start = _MARKER_START.format(pack_name=pack_name)
                marker_end = _MARKER_END.format(pack_name=pack_name)
                new_content = f"{marker_start}\n{rf.content}{marker_end}\n"
            else:
                new_content = rf.content
            diff_lines = list(
                difflib.unified_diff(
                    [],
                    new_content.splitlines(keepends=True),
                    fromfile="/dev/null",
                    tofile=f"b/{rf.dest}",
                )
            )
        else:
            existing = file_path.read_text()

            if rf.mode == "append":
                new_content = _compute_append_content(existing, rf.content, pack_name)
            else:
                new_content = rf.content

            if existing == new_content:
                continue

            diff_lines = list(
                difflib.unified_diff(
                    existing.splitlines(keepends=True),
                    new_content.splitlines(keepends=True),
                    fromfile=f"a/{rf.dest}",
                    tofile=f"b/{rf.dest}",
                )
            )

        if diff_lines:
            results.append(
                DiffResult(
                    dest=rf.dest,
                    diff_text="".join(diff_lines),
                    is_new=is_new,
                )
            )

    return results
