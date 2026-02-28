# ruff: noqa: RUF003
"""Adversarial tests: Unicode attacks on spec values.

Tests homoglyphs, zero-width characters, fullwidth ASCII, and combining chars.
Every test asserts: (1) clean output produced, (2) warning emitted.
"""

from __future__ import annotations

import logging

import pytest

from navi_bootstrap.sanitize import sanitize_spec

from .conftest import (
    FULLWIDTH_PAYLOAD,
    ZERO_WIDTH_CHARS,
)


class TestHomoglyphNormalization:
    """Cyrillic and Greek homoglyphs are replaced with ASCII equivalents."""

    def test_cyrillic_a_in_name(self, caplog: pytest.LogCaptureFixture) -> None:
        spec = {"name": "n\u0430vi", "language": "python"}
        with caplog.at_level(logging.WARNING, logger="navi_bootstrap.sanitize"):
            result = sanitize_spec(spec)
        assert result["name"] == "navi"
        assert "homoglyph" in caplog.text.lower()

    def test_multiple_cyrillic_in_description(self, caplog: pytest.LogCaptureFixture) -> None:
        spec = {
            "name": "test",
            "language": "python",
            "description": "\u0440\u0443th\u043en",  # рутhоn
        }
        with caplog.at_level(logging.WARNING, logger="navi_bootstrap.sanitize"):
            result = sanitize_spec(spec)
        assert result["description"] == "python"
        assert "homoglyph" in caplog.text.lower()

    def test_greek_homoglyphs_in_strings(self, caplog: pytest.LogCaptureFixture) -> None:
        spec = {
            "name": "test",
            "language": "python",
            "description": "\u0391\u0392C",  # ΑΒC → ABC
        }
        with caplog.at_level(logging.WARNING, logger="navi_bootstrap.sanitize"):
            result = sanitize_spec(spec)
        assert result["description"] == "ABC"
        assert "homoglyph" in caplog.text.lower()

    def test_mixed_cyrillic_greek(self, caplog: pytest.LogCaptureFixture) -> None:
        spec = {
            "name": "test",
            "language": "python",
            "description": "\u0430\u03bf",  # Cyrillic а + Greek ο → ao
        }
        with caplog.at_level(logging.WARNING, logger="navi_bootstrap.sanitize"):
            result = sanitize_spec(spec)
        assert result["description"] == "ao"


class TestZeroWidthStripping:
    """Zero-width characters are stripped from all string values."""

    def test_zero_width_space_stripped(self, caplog: pytest.LogCaptureFixture) -> None:
        spec = {"name": "te\u200bst", "language": "python"}
        with caplog.at_level(logging.WARNING, logger="navi_bootstrap.sanitize"):
            result = sanitize_spec(spec)
        assert result["name"] == "test"
        assert "zero-width" in caplog.text.lower()

    def test_all_six_zero_width_chars(self, caplog: pytest.LogCaptureFixture) -> None:
        payload = "test" + "".join(ZERO_WIDTH_CHARS) + "end"
        spec = {"name": payload, "language": "python"}
        with caplog.at_level(logging.WARNING, logger="navi_bootstrap.sanitize"):
            result = sanitize_spec(spec)
        assert result["name"] == "testend"
        assert "zero-width" in caplog.text.lower()

    def test_zero_width_in_nested_values(self, caplog: pytest.LogCaptureFixture) -> None:
        spec = {
            "name": "test",
            "language": "python",
            "recon": {"test_framework": "py\u200btest"},
        }
        with caplog.at_level(logging.WARNING, logger="navi_bootstrap.sanitize"):
            result = sanitize_spec(spec)
        assert result["recon"]["test_framework"] == "pytest"


class TestFullwidthNormalization:
    """Fullwidth ASCII characters are normalized to regular ASCII."""

    def test_fullwidth_ignore(self, caplog: pytest.LogCaptureFixture) -> None:
        spec = {"name": "test", "language": "python", "description": FULLWIDTH_PAYLOAD}
        with caplog.at_level(logging.WARNING, logger="navi_bootstrap.sanitize"):
            result = sanitize_spec(spec)
        assert result["description"] == "ignore"
        assert "fullwidth" in caplog.text.lower()

    def test_fullwidth_in_name(self, caplog: pytest.LogCaptureFixture) -> None:
        spec = {"name": "\uff54\uff45\uff53\uff54", "language": "python"}  # ｔｅｓｔ
        with caplog.at_level(logging.WARNING, logger="navi_bootstrap.sanitize"):
            result = sanitize_spec(spec)
        assert result["name"] == "test"


class TestCleanInputUnchanged:
    """Clean inputs pass through without warnings."""

    def test_clean_spec_no_warnings(self, caplog: pytest.LogCaptureFixture) -> None:
        spec = {
            "name": "my-project",
            "language": "python",
            "description": "A normal project",
        }
        with caplog.at_level(logging.WARNING, logger="navi_bootstrap.sanitize"):
            result = sanitize_spec(spec)
        assert result == spec
        assert caplog.text == ""

    def test_non_string_values_preserved(self, caplog: pytest.LogCaptureFixture) -> None:
        spec = {
            "name": "test",
            "language": "python",
            "features": {"ci": True},
            "recon": {"test_count": 42},
        }
        with caplog.at_level(logging.WARNING, logger="navi_bootstrap.sanitize"):
            result = sanitize_spec(spec)
        assert result["features"]["ci"] is True
        assert result["recon"]["test_count"] == 42
        assert caplog.text == ""
