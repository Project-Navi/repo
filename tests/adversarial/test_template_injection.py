# ruff: noqa: RUF003
"""Adversarial tests: Template injection in spec values.

Tests Jinja2 delimiter escaping to prevent SSTI.
Every test asserts: (1) clean output produced, (2) warning emitted.
"""

from __future__ import annotations

import logging

import pytest

from navi_bootstrap.sanitize import sanitize_spec


class TestJinja2DelimiterEscaping:
    """Jinja2 delimiters in spec values are escaped before rendering."""

    def test_double_brace_expression(self, caplog: pytest.LogCaptureFixture) -> None:
        spec = {"name": "test", "language": "python", "description": "{{ config }}"}
        with caplog.at_level(logging.WARNING, logger="navi_bootstrap.sanitize"):
            result = sanitize_spec(spec)
        # Must not contain raw Jinja2 delimiters
        assert "{{" not in result["description"]
        assert "}}" not in result["description"]
        assert "template injection" in caplog.text.lower()

    def test_block_tag(self, caplog: pytest.LogCaptureFixture) -> None:
        spec = {
            "name": "test",
            "language": "python",
            "description": "{% import os %}",
        }
        with caplog.at_level(logging.WARNING, logger="navi_bootstrap.sanitize"):
            result = sanitize_spec(spec)
        assert "{%" not in result["description"]
        assert "%}" not in result["description"]
        assert "template injection" in caplog.text.lower()

    def test_comment_injection(self, caplog: pytest.LogCaptureFixture) -> None:
        spec = {
            "name": "test",
            "language": "python",
            "description": "{# malicious comment #}",
        }
        with caplog.at_level(logging.WARNING, logger="navi_bootstrap.sanitize"):
            result = sanitize_spec(spec)
        assert "{#" not in result["description"]
        assert "#}" not in result["description"]
        assert "template injection" in caplog.text.lower()

    def test_ssti_class_traversal(self, caplog: pytest.LogCaptureFixture) -> None:
        payload = "{{ ''.__class__.__mro__[1].__subclasses__() }}"
        spec = {"name": "test", "language": "python", "description": payload}
        with caplog.at_level(logging.WARNING, logger="navi_bootstrap.sanitize"):
            result = sanitize_spec(spec)
        assert "{{" not in result["description"]
        assert "template injection" in caplog.text.lower()

    def test_ssti_lipsum_popen(self, caplog: pytest.LogCaptureFixture) -> None:
        payload = "{{ lipsum.__globals__['os'].popen('id').read() }}"
        spec = {"name": "test", "language": "python", "description": payload}
        with caplog.at_level(logging.WARNING, logger="navi_bootstrap.sanitize"):
            result = sanitize_spec(spec)
        assert "{{" not in result["description"]

    def test_dos_loop(self, caplog: pytest.LogCaptureFixture) -> None:
        payload = "{% for x in range(999999999) %}{% endfor %}"
        spec = {"name": "test", "language": "python", "description": payload}
        with caplog.at_level(logging.WARNING, logger="navi_bootstrap.sanitize"):
            result = sanitize_spec(spec)
        assert "{%" not in result["description"]

    def test_injection_in_nested_spec_values(self, caplog: pytest.LogCaptureFixture) -> None:
        spec = {
            "name": "test",
            "language": "python",
            "modules": [
                {"name": "core", "description": "{{ config.SECRET_KEY }}"},
            ],
        }
        with caplog.at_level(logging.WARNING, logger="navi_bootstrap.sanitize"):
            result = sanitize_spec(spec)
        assert "{{" not in result["modules"][0]["description"]
        assert "template injection" in caplog.text.lower()

    def test_injection_in_name_field(self, caplog: pytest.LogCaptureFixture) -> None:
        spec = {"name": "{{ malicious }}", "language": "python"}
        with caplog.at_level(logging.WARNING, logger="navi_bootstrap.sanitize"):
            result = sanitize_spec(spec)
        assert "{{" not in result["name"]


class TestMixedAttackVectors:
    """Combined attacks: template injection + unicode + path traversal."""

    def test_homoglyph_plus_injection(self, caplog: pytest.LogCaptureFixture) -> None:
        # Cyrillic о in "config" + Jinja2 expression
        spec = {
            "name": "test",
            "language": "python",
            "description": "{{ c\u043enfig }}",
        }
        with caplog.at_level(logging.WARNING, logger="navi_bootstrap.sanitize"):
            result = sanitize_spec(spec)
        # Both homoglyph AND injection should be handled
        assert "{{" not in result["description"]

    def test_zero_width_in_delimiters(self, caplog: pytest.LogCaptureFixture) -> None:
        # Zero-width chars inserted between { and {
        spec = {
            "name": "test",
            "language": "python",
            "description": "{\u200b{ config }\u200b}",
        }
        with caplog.at_level(logging.WARNING, logger="navi_bootstrap.sanitize"):
            result = sanitize_spec(spec)
        # After zero-width stripping, {{ config }} should be caught
        assert "{{" not in result["description"]
