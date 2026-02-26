# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Project Navi

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
        results.append(
            HookResult(
                command=command,
                success=result.returncode == 0,
                stdout=result.stdout,
                stderr=result.stderr,
                returncode=result.returncode,
            )
        )

    return results
