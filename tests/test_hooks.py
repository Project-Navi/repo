"""Tests for post-render hook runner."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from navi_bootstrap.hooks import run_hooks


class TestRunHooks:
    @patch("navi_bootstrap.hooks.subprocess.run")
    def test_runs_hooks_sequentially(self, mock_run: MagicMock, tmp_path: Path) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        results = run_hooks(["echo hello", "echo world"], tmp_path)
        assert len(results) == 2
        assert all(r.success for r in results)
        assert mock_run.call_count == 2

    @patch("navi_bootstrap.hooks.subprocess.run")
    def test_reports_failures_without_stopping(self, mock_run: MagicMock, tmp_path: Path) -> None:
        mock_run.side_effect = [
            MagicMock(returncode=1, stdout="", stderr="fail"),
            MagicMock(returncode=0, stdout="ok", stderr=""),
        ]
        results = run_hooks(["bad", "good"], tmp_path)
        assert not results[0].success
        assert results[1].success

    def test_empty_hooks(self, tmp_path: Path) -> None:
        results = run_hooks([], tmp_path)
        assert results == []

    @patch("navi_bootstrap.hooks.subprocess.run")
    def test_captures_output(self, mock_run: MagicMock, tmp_path: Path) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="some output", stderr="some warning")
        results = run_hooks(["test_cmd"], tmp_path)
        assert results[0].stdout == "some output"
        assert results[0].stderr == "some warning"
