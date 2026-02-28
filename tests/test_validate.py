"""Tests for post-render validation runner."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from navi_bootstrap.validate import run_validations


class TestRunValidations:
    @patch("navi_bootstrap.validate.subprocess.run")
    def test_passing_validation(self, mock_run: MagicMock, tmp_path: Path) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        results = run_validations(
            [{"description": "test", "command": "echo ok", "expect": "exit_code_0"}],
            tmp_path,
        )
        assert len(results) == 1
        assert results[0].passed

    @patch("navi_bootstrap.validate.subprocess.run")
    def test_failing_validation(self, mock_run: MagicMock, tmp_path: Path) -> None:
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="fail")
        results = run_validations(
            [{"description": "test", "command": "bad", "expect": "exit_code_0"}],
            tmp_path,
        )
        assert len(results) == 1
        assert not results[0].passed

    @patch("navi_bootstrap.validate.subprocess.run")
    def test_warnings_accepted(self, mock_run: MagicMock, tmp_path: Path) -> None:
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
    def test_skips_method_based_validations(self, mock_run: MagicMock, tmp_path: Path) -> None:
        results = run_validations(
            [{"description": "SHA check", "method": "sha_verification"}],
            tmp_path,
        )
        assert len(results) == 1
        assert results[0].skipped
        mock_run.assert_not_called()
