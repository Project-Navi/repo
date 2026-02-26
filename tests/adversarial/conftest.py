# ruff: noqa: RUF003
"""Hostile payloads for adversarial testing of navi-bootstrap.

Adapted from navi-os INJECTION_PAYLOADS. Each payload targets a specific
attack vector in the rendering pipeline. Every test asserts TWO things:
(1) clean output produced, (2) warning emitted.
"""

from __future__ import annotations

import pytest

# --- Unicode Payloads ---

CYRILLIC_HOMOGLYPHS = {
    # Cyrillic characters that look identical to Latin
    "\u0430": "a",  # Cyrillic а → Latin a
    "\u0435": "e",  # Cyrillic е → Latin e
    "\u043e": "o",  # Cyrillic о → Latin o
    "\u0440": "p",  # Cyrillic р → Latin p
    "\u0441": "c",  # Cyrillic с → Latin c
    "\u0443": "y",  # Cyrillic у → Latin y
    "\u0445": "x",  # Cyrillic х → Latin x
}

GREEK_HOMOGLYPHS = {
    "\u03b1": "a",  # Greek α → Latin a
    "\u03bf": "o",  # Greek ο → Latin o
    "\u0391": "A",  # Greek Α → Latin A
    "\u0392": "B",  # Greek Β → Latin B
    "\u0395": "E",  # Greek Ε → Latin E
    "\u039a": "K",  # Greek Κ → Latin K
    "\u039c": "M",  # Greek Μ → Latin M
    "\u039d": "N",  # Greek Ν → Latin N
    "\u039f": "O",  # Greek Ο → Latin O
    "\u03a1": "P",  # Greek Ρ → Latin P
    "\u03a4": "T",  # Greek Τ → Latin T
}

ZERO_WIDTH_CHARS = [
    "\u200b",  # zero-width space
    "\u200c",  # zero-width non-joiner
    "\u200d",  # zero-width joiner
    "\u2060",  # word joiner
    "\ufeff",  # BOM / zero-width no-break space
    "\u180e",  # Mongolian vowel separator
]

FULLWIDTH_PAYLOAD = "\uff49\uff47\uff4e\uff4f\uff52\uff45"  # ｉｇｎｏｒｅ


# --- Path Traversal Payloads ---

PATH_TRAVERSAL_PAYLOADS = [
    ("../../../etc/passwd", "etc/passwd"),
    ("../../.env", ".env"),
    ("foo/../../../bar", "foo/bar"),
    ("/absolute/path", "absolute/path"),
    ("foo/./bar/../baz", "foo/baz"),
]

NULL_BYTE_PAYLOADS = [
    ("hello\x00world", "helloworld"),
    ("test\x00.json\x00.txt", "test.json.txt"),
]


# --- Template Injection Payloads ---

JINJA2_INJECTION_PAYLOADS = [
    "{{ config }}",
    "{% import os %}",
    "{{ ''.__class__.__mro__[1].__subclasses__() }}",
    "{# comment injection #}",
    "{{ lipsum.__globals__['os'].popen('id').read() }}",
    "{% for x in range(999999999) %}{% endfor %}",
    "{{ request.environ }}",
]


# --- Hostile Spec Fixture ---


@pytest.fixture
def hostile_spec() -> dict:
    """A spec with adversarial values across all fields."""
    return {
        "name": "n\u0430vi-b\u043e\u043etstr\u0430p",  # Cyrillic homoglyphs
        "language": "python",
        "python_version": "3.12",
        "description": "A {{ config }} project\x00with null",
        "structure": {
            "src_dir": "src/n\u0430vi",  # Cyrillic а
            "test_dir": "../../../etc",  # path traversal
        },
        "features": {"ci": True},
        "modules": [
            {"name": "../\x00evil", "description": "{% import os %}"},
        ],
        "recon": {
            "test_framework": "pytest\u200b\u200b\u200b",  # zero-width chars
            "test_count": 125,
        },
    }


@pytest.fixture
def hostile_manifest() -> dict:
    """A manifest with adversarial dest paths."""
    return {
        "name": "hostile-pack",
        "version": "0.1.0",
        "description": "{{ lipsum.__globals__ }}",
        "templates": [
            {"src": "file.j2", "dest": "../../../etc/shadow"},
            {"src": "file2.j2", "dest": "/absolute/path.txt"},
            {"src": "file3.j2", "dest": "normal/\x00path.txt"},
        ],
        "conditions": {},
        "loops": {},
        "hooks": [],
    }
