# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Project Navi

"""Tests for dest path sandbox — _render_dest_path must use SandboxedEnvironment.

GPT external review found: _render_dest_path uses a vanilla jinja2.Environment,
allowing hostile packs to exploit dunder attribute access in dest templates.
"""

from __future__ import annotations

from typing import Any

import jinja2
import pytest

from navi_bootstrap.engine import _render_dest_path


class TestDestPathSandbox:
    """_render_dest_path must block dunder attribute access (SSTI prevention)."""

    def test_dunder_class_access_raises_security_error(self) -> None:
        """Accessing __class__ in dest template must raise SecurityError."""
        context: dict[str, Any] = {"spec": {"name": "test"}}
        with pytest.raises(jinja2.exceptions.SecurityError):
            _render_dest_path("{{ ''.__class__ }}", context)

    def test_dunder_mro_access_raises_security_error(self) -> None:
        """Accessing __mro__ via __class__ must raise SecurityError."""
        context: dict[str, Any] = {"spec": {"name": "test"}}
        with pytest.raises(jinja2.exceptions.SecurityError):
            _render_dest_path("{{ ''.__class__.__mro__ }}", context)

    def test_dunder_subclasses_raises_security_error(self) -> None:
        """Accessing __subclasses__ must raise SecurityError."""
        context: dict[str, Any] = {"spec": {"name": "test"}}
        with pytest.raises(jinja2.exceptions.SecurityError):
            _render_dest_path("{{ ''.__class__.__subclasses__() }}", context)

    def test_normal_dest_rendering_still_works(self) -> None:
        """Sandboxed environment must still render normal dest templates."""
        context: dict[str, Any] = {"spec": {"name": "myapp"}, "item": {"name": "auth"}}
        result = _render_dest_path("src/{{ item.name }}.py", context)
        assert result == "src/auth.py"

    def test_spec_value_in_dest_still_works(self) -> None:
        """Accessing spec values in dest templates must still work."""
        context: dict[str, Any] = {"spec": {"name": "myapp"}}
        result = _render_dest_path("{{ spec.name }}/README.md", context)
        assert result == "myapp/README.md"

    def test_strict_undefined_still_enforced(self) -> None:
        """StrictUndefined must still raise on missing variables."""
        context: dict[str, Any] = {"spec": {"name": "test"}}
        with pytest.raises(jinja2.exceptions.UndefinedError):
            _render_dest_path("{{ nonexistent }}/file.py", context)
