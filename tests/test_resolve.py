"""Tests for action SHA resolution."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from navi_bootstrap.resolve import ResolveError, resolve_action_shas


@pytest.fixture
def action_shas_config() -> list[dict[str, str]]:
    return [
        {"name": "actions_checkout", "repo": "actions/checkout", "tag": "v4.2.2"},
        {"name": "harden_runner", "repo": "step-security/harden-runner", "tag": "v2.10.4"},
    ]


def _make_gh_response(sha: str, tag_type: str = "commit") -> str:
    """Build a mock gh api JSON response."""
    if tag_type == "commit":
        return json.dumps({"object": {"type": "commit", "sha": sha}})
    return json.dumps({"object": {"type": "tag", "sha": "intermediate_sha", "url": "..."}})


class TestResolveActionShas:
    @patch("navi_bootstrap.resolve.subprocess.run")
    def test_resolves_lightweight_tags(
        self, mock_run: MagicMock, action_shas_config: list[dict[str, str]]
    ) -> None:
        sha1 = "a" * 40
        sha2 = "b" * 40
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=_make_gh_response(sha1)),
            MagicMock(returncode=0, stdout=_make_gh_response(sha2)),
        ]
        shas, versions = resolve_action_shas(action_shas_config)
        assert shas["actions_checkout"] == sha1
        assert shas["harden_runner"] == sha2
        assert versions["actions_checkout"] == "v4.2.2"
        assert versions["harden_runner"] == "v2.10.4"

    @patch("navi_bootstrap.resolve.subprocess.run")
    def test_resolves_annotated_tags(
        self, mock_run: MagicMock, action_shas_config: list[dict[str, str]]
    ) -> None:
        real_sha = "c" * 40
        # First call returns annotated tag, second dereferences, third is second action
        mock_run.side_effect = [
            MagicMock(
                returncode=0,
                stdout=json.dumps({"object": {"type": "tag", "sha": "intermediate", "url": "u"}}),
            ),
            MagicMock(
                returncode=0,
                stdout=json.dumps({"object": {"type": "commit", "sha": real_sha}}),
            ),
            MagicMock(
                returncode=0,
                stdout=_make_gh_response(real_sha),
            ),
        ]
        shas, _ = resolve_action_shas(action_shas_config)
        assert shas["actions_checkout"] == real_sha

    @patch("navi_bootstrap.resolve.subprocess.run")
    def test_gh_failure_raises(
        self, mock_run: MagicMock, action_shas_config: list[dict[str, str]]
    ) -> None:
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="Not Found")
        with pytest.raises(ResolveError, match="actions/checkout"):
            resolve_action_shas(action_shas_config)

    def test_empty_list_returns_empty(self) -> None:
        shas, versions = resolve_action_shas([])
        assert shas == {}
        assert versions == {}

    @patch("navi_bootstrap.resolve.subprocess.run")
    def test_skip_resolve_flag(
        self, mock_run: MagicMock, action_shas_config: list[dict[str, str]]
    ) -> None:
        shas, versions = resolve_action_shas(action_shas_config, skip=True)
        assert shas["actions_checkout"] == "SKIP_SHA_RESOLUTION"
        assert versions["actions_checkout"] == "v4.2.2"
        mock_run.assert_not_called()
