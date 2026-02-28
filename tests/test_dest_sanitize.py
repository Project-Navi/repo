"""Tests for dest sanitization: Jinja delimiters must survive in manifest dest paths.

GPT external review found: sanitize_manifest() escapes Jinja delimiters in dest,
breaking the looped dest template feature that _render_dest_path() supports.
"""

from __future__ import annotations

from navi_bootstrap.sanitize import sanitize_manifest


class TestManifestDestPreservesJinja:
    """sanitize_manifest must not escape Jinja delimiters in dest fields."""

    def test_simple_dest_unchanged(self) -> None:
        manifest = {
            "name": "test-pack",
            "version": "0.1.0",
            "templates": [{"src": "readme.j2", "dest": "README.md"}],
        }
        result = sanitize_manifest(manifest)
        assert result["templates"][0]["dest"] == "README.md"

    def test_looped_dest_preserves_jinja(self) -> None:
        """The core bug: {{ item.name }} in dest must not be escaped."""
        manifest = {
            "name": "test-pack",
            "version": "0.1.0",
            "templates": [
                {"src": "module.py.j2", "dest": "src/{{ item.name }}.py"},
            ],
        }
        result = sanitize_manifest(manifest)
        assert result["templates"][0]["dest"] == "src/{{ item.name }}.py"

    def test_dest_with_block_tags_preserved(self) -> None:
        """{% %} delimiters in dest should also survive."""
        manifest = {
            "name": "test-pack",
            "version": "0.1.0",
            "templates": [
                {"src": "mod.j2", "dest": "{% if x %}a{% endif %}/file.py"},
            ],
        }
        result = sanitize_manifest(manifest)
        assert "{% if x %}" in result["templates"][0]["dest"]

    def test_dest_still_strips_traversal(self) -> None:
        """Path traversal in dest must still be cleaned."""
        manifest = {
            "name": "test-pack",
            "version": "0.1.0",
            "templates": [
                {"src": "evil.j2", "dest": "../../etc/passwd"},
            ],
        }
        result = sanitize_manifest(manifest)
        assert ".." not in result["templates"][0]["dest"]
        assert result["templates"][0]["dest"] == "etc/passwd"

    def test_dest_still_strips_null_bytes(self) -> None:
        """Null bytes in dest must still be stripped."""
        manifest = {
            "name": "test-pack",
            "version": "0.1.0",
            "templates": [
                {"src": "f.j2", "dest": "src/file\x00.py"},
            ],
        }
        result = sanitize_manifest(manifest)
        assert "\x00" not in result["templates"][0]["dest"]

    def test_dest_still_strips_zero_width(self) -> None:
        """Zero-width chars in dest must still be cleaned."""
        manifest = {
            "name": "test-pack",
            "version": "0.1.0",
            "templates": [
                {"src": "f.j2", "dest": "src/fi\u200ble.py"},
            ],
        }
        result = sanitize_manifest(manifest)
        assert "\u200b" not in result["templates"][0]["dest"]

    def test_manifest_name_still_escapes_jinja(self) -> None:
        """Non-dest string fields must still escape Jinja (prevent injection)."""
        manifest = {
            "name": "{{ malicious }}",
            "version": "0.1.0",
            "templates": [],
        }
        result = sanitize_manifest(manifest)
        assert "{{" not in result["name"]
