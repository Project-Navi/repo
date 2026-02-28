"""Adversarial tests: Path traversal and null byte attacks.

Tests ../ escape, absolute paths, null bytes in paths and names.
Every test asserts: (1) clean output produced, (2) warning emitted.
"""

from __future__ import annotations

import logging

import pytest

from navi_bootstrap.sanitize import sanitize_manifest, sanitize_spec


class TestSpecPathTraversal:
    """Path traversal in spec fields (name, modules, structure)."""

    def test_dotdot_in_spec_name(self, caplog: pytest.LogCaptureFixture) -> None:
        spec = {"name": "../../../etc/passwd", "language": "python"}
        with caplog.at_level(logging.WARNING, logger="navi_bootstrap.sanitize"):
            result = sanitize_spec(spec)
        assert ".." not in result["name"]
        assert "path traversal" in caplog.text.lower()

    def test_absolute_path_in_spec_name(self, caplog: pytest.LogCaptureFixture) -> None:
        spec = {"name": "/etc/passwd", "language": "python"}
        with caplog.at_level(logging.WARNING, logger="navi_bootstrap.sanitize"):
            result = sanitize_spec(spec)
        assert not result["name"].startswith("/")
        assert "path traversal" in caplog.text.lower()

    def test_dotdot_in_module_name(self, caplog: pytest.LogCaptureFixture) -> None:
        spec = {
            "name": "test",
            "language": "python",
            "modules": [{"name": "../../evil"}],
        }
        with caplog.at_level(logging.WARNING, logger="navi_bootstrap.sanitize"):
            result = sanitize_spec(spec)
        assert ".." not in result["modules"][0]["name"]
        assert "path traversal" in caplog.text.lower()

    def test_dotdot_in_structure_test_dir(self, caplog: pytest.LogCaptureFixture) -> None:
        spec = {
            "name": "test",
            "language": "python",
            "structure": {"src_dir": "src", "test_dir": "../../../etc"},
        }
        with caplog.at_level(logging.WARNING, logger="navi_bootstrap.sanitize"):
            result = sanitize_spec(spec)
        assert ".." not in result["structure"]["test_dir"]
        assert "path traversal" in caplog.text.lower()


class TestManifestPathTraversal:
    """Path traversal in manifest dest paths."""

    def test_dotdot_in_dest(self, caplog: pytest.LogCaptureFixture) -> None:
        manifest = {
            "name": "test-pack",
            "templates": [{"src": "f.j2", "dest": "../../../etc/shadow"}],
        }
        with caplog.at_level(logging.WARNING, logger="navi_bootstrap.sanitize"):
            result = sanitize_manifest(manifest)
        assert ".." not in result["templates"][0]["dest"]
        assert "path traversal" in caplog.text.lower()

    def test_absolute_dest(self, caplog: pytest.LogCaptureFixture) -> None:
        manifest = {
            "name": "test-pack",
            "templates": [{"src": "f.j2", "dest": "/etc/passwd"}],
        }
        with caplog.at_level(logging.WARNING, logger="navi_bootstrap.sanitize"):
            result = sanitize_manifest(manifest)
        assert not result["templates"][0]["dest"].startswith("/")
        assert "path traversal" in caplog.text.lower()

    def test_multiple_traversal_dests(self, caplog: pytest.LogCaptureFixture) -> None:
        manifest = {
            "name": "test-pack",
            "templates": [
                {"src": "a.j2", "dest": "../../a.txt"},
                {"src": "b.j2", "dest": "/abs/b.txt"},
            ],
        }
        with caplog.at_level(logging.WARNING, logger="navi_bootstrap.sanitize"):
            result = sanitize_manifest(manifest)
        for t in result["templates"]:
            assert ".." not in t["dest"]
            assert not t["dest"].startswith("/")


class TestNullBytes:
    """Null bytes are stripped from all string values."""

    def test_null_byte_in_name(self, caplog: pytest.LogCaptureFixture) -> None:
        spec = {"name": "test\x00project", "language": "python"}
        with caplog.at_level(logging.WARNING, logger="navi_bootstrap.sanitize"):
            result = sanitize_spec(spec)
        assert "\x00" not in result["name"]
        assert result["name"] == "testproject"
        assert "null byte" in caplog.text.lower()

    def test_null_byte_in_manifest_dest(self, caplog: pytest.LogCaptureFixture) -> None:
        manifest = {
            "name": "test-pack",
            "templates": [{"src": "f.j2", "dest": "file\x00.txt"}],
        }
        with caplog.at_level(logging.WARNING, logger="navi_bootstrap.sanitize"):
            result = sanitize_manifest(manifest)
        assert "\x00" not in result["templates"][0]["dest"]

    def test_null_byte_in_description(self, caplog: pytest.LogCaptureFixture) -> None:
        spec = {"name": "test", "language": "python", "description": "foo\x00bar"}
        with caplog.at_level(logging.WARNING, logger="navi_bootstrap.sanitize"):
            result = sanitize_spec(spec)
        assert result["description"] == "foobar"
        assert "null byte" in caplog.text.lower()
