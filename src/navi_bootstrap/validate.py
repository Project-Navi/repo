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
            results.append(
                ValidationResult(description=description, passed=False, skipped=True)
            )
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

        results.append(
            ValidationResult(
                description=description,
                passed=passed,
                stdout=result.stdout,
                stderr=result.stderr,
                returncode=result.returncode,
            )
        )

    return results
