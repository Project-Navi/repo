"""Input sanitization for hostile spec and manifest values.

Sanitize-and-warn, never error. The pipeline must always produce output.
Called between load_spec()/load_manifest() and plan() in the CLI.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from copy import deepcopy
from typing import Any

logger = logging.getLogger("navi_bootstrap.sanitize")

# --- Homoglyph Map (42 pairs from navi-os unicode_security.py) ---

HOMOGLYPH_MAP: dict[str, str] = {
    # Cyrillic → Latin (lowercase)
    "\u0430": "a",
    "\u0435": "e",
    "\u043e": "o",
    "\u0440": "p",
    "\u0441": "c",
    "\u0443": "y",
    "\u0445": "x",
    # Cyrillic → Latin (uppercase)
    "\u0410": "A",
    "\u0412": "B",
    "\u0415": "E",
    "\u041a": "K",
    "\u041c": "M",
    "\u041d": "H",
    "\u041e": "O",
    "\u0420": "P",
    "\u0421": "C",
    "\u0422": "T",
    "\u0425": "X",
    # Greek → Latin (uppercase)
    "\u0391": "A",
    "\u0392": "B",
    "\u0395": "E",
    "\u0396": "Z",
    "\u0397": "H",
    "\u0399": "I",
    "\u039a": "K",
    "\u039c": "M",
    "\u039d": "N",
    "\u039f": "O",
    "\u03a1": "P",
    "\u03a4": "T",
    "\u03a5": "Y",
    "\u03a7": "X",
    # Greek → Latin (lowercase)
    "\u03b1": "a",
    "\u03bf": "o",
    # Typographic
    "\u2212": "-",  # minus sign
    "\u2013": "-",  # en dash
    "\u2014": "-",  # em dash
    "\u2018": "'",  # left single quote
    "\u2019": "'",  # right single quote
    "\u201c": '"',  # left double quote
    "\u201d": '"',  # right double quote
}

# Zero-width characters to strip
ZERO_WIDTH_CHARS: set[str] = {
    "\u200b",  # zero-width space
    "\u200c",  # zero-width non-joiner
    "\u200d",  # zero-width joiner
    "\u2060",  # word joiner
    "\ufeff",  # BOM / zero-width no-break space
    "\u180e",  # Mongolian vowel separator
}

_ZERO_WIDTH_RE = re.compile("[" + "".join(ZERO_WIDTH_CHARS) + "]")

# Jinja2 delimiter patterns
_JINJA2_DELIMITERS = re.compile(r"\{\{|\}\}|\{%|%\}|\{#|#\}")


def _strip_null_bytes(s: str) -> tuple[str, bool]:
    """Strip null bytes. Returns (cleaned, had_nulls)."""
    if "\x00" in s:
        return s.replace("\x00", ""), True
    return s, False


def _strip_zero_width(s: str) -> tuple[str, bool]:
    """Strip zero-width characters. Returns (cleaned, had_zero_width)."""
    cleaned = _ZERO_WIDTH_RE.sub("", s)
    return cleaned, cleaned != s


def _normalize_fullwidth(s: str) -> tuple[str, bool]:
    """NFKC normalize to convert fullwidth ASCII to regular ASCII.

    Returns (cleaned, had_fullwidth).
    """
    normalized = unicodedata.normalize("NFKC", s)
    return normalized, normalized != s


def _replace_homoglyphs(s: str) -> tuple[str, int]:
    """Replace known homoglyphs with ASCII equivalents.

    Returns (cleaned, count_replaced).
    """
    count = 0
    chars = list(s)
    for i, ch in enumerate(chars):
        if ch in HOMOGLYPH_MAP:
            chars[i] = HOMOGLYPH_MAP[ch]
            count += 1
    return "".join(chars), count


def _escape_jinja2(s: str) -> tuple[str, bool]:
    """Escape Jinja2 delimiters in string values.

    Replaces {{ → \\{\\{, }} → \\}\\}, {% → \\{\\%, %} → \\%\\},
    {# → \\{\\#, #} → \\#\\}.

    Returns (escaped, had_delimiters).
    """
    if _JINJA2_DELIMITERS.search(s):
        escaped = s
        escaped = escaped.replace("{{", r"\{\{")
        escaped = escaped.replace("}}", r"\}\}")
        escaped = escaped.replace("{%", r"\{\%")
        escaped = escaped.replace("%}", r"\%\}")
        escaped = escaped.replace("{#", r"\{\#")
        escaped = escaped.replace("#}", r"\#\}")
        return escaped, True
    return s, False


def _sanitize_path(s: str) -> tuple[str, bool]:
    """Remove path traversal: strip ../ segments and leading /.

    Returns (cleaned, had_traversal).
    """
    original = s
    # Strip leading /
    s = s.lstrip("/")
    # Normalize and remove .. segments
    parts = s.split("/")
    clean_parts: list[str] = []
    for part in parts:
        if part == ".." or part == ".":
            continue
        clean_parts.append(part)
    cleaned = "/".join(clean_parts)
    return cleaned, cleaned != original


def _sanitize_string(s: str, *, is_path: bool = False) -> str:
    """Apply the full sanitization pipeline to a single string.

    Order matters: null bytes → zero-width → NFKC → homoglyphs → jinja2 → path.
    Zero-width stripping before Jinja2 escaping prevents evasion via
    zero-width chars inserted between delimiters.
    """
    # 1. Null bytes
    s, had_nulls = _strip_null_bytes(s)
    if had_nulls:
        logger.warning("Sanitized null byte(s) in value")

    # 2. Zero-width characters
    s, had_zw = _strip_zero_width(s)
    if had_zw:
        logger.warning("Stripped zero-width character(s) from value")

    # 3. Fullwidth → ASCII (NFKC)
    s, had_fw = _normalize_fullwidth(s)
    if had_fw:
        logger.warning("Normalized fullwidth character(s) in value")

    # 4. Homoglyphs
    s, glyph_count = _replace_homoglyphs(s)
    if glyph_count:
        logger.warning("Replaced %d homoglyph(s) in value", glyph_count)

    # 5. Jinja2 delimiter escaping
    s, had_jinja = _escape_jinja2(s)
    if had_jinja:
        logger.warning("Escaped template injection delimiter(s) in value")

    # 6. Path traversal (only for path-like fields)
    if is_path:
        s, had_traversal = _sanitize_path(s)
        if had_traversal:
            logger.warning("Sanitized path traversal in value")

    return s


def _walk_and_sanitize(
    obj: Any,
    *,
    path_fields: set[str] | None = None,
    _current_key: str = "",
) -> Any:
    """Recursively walk a dict/list and sanitize all string values."""
    if path_fields is None:
        path_fields = set()

    if isinstance(obj, dict):
        return {
            k: _walk_and_sanitize(
                v,
                path_fields=path_fields,
                _current_key=k,
            )
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [
            _walk_and_sanitize(
                item,
                path_fields=path_fields,
                _current_key=_current_key,
            )
            for item in obj
        ]
    if isinstance(obj, str):
        is_path = _current_key in path_fields
        return _sanitize_string(obj, is_path=is_path)
    return obj


def sanitize_spec(spec_data: dict[str, Any]) -> dict[str, Any]:
    """Sanitize a loaded spec dict. Returns cleaned copy.

    Applies: null byte stripping, zero-width removal, NFKC normalization,
    homoglyph replacement, Jinja2 delimiter escaping, path traversal
    prevention (on name, module names, structure paths).
    """
    spec = deepcopy(spec_data)
    path_fields = {"name", "src_dir", "test_dir", "docs_dir"}
    result: dict[str, Any] = _walk_and_sanitize(spec, path_fields=path_fields)

    # Extra path sanitization for modules[*].name
    if "modules" in result and isinstance(result["modules"], list):
        for mod in result["modules"]:
            if isinstance(mod, dict) and "name" in mod and isinstance(mod["name"], str):
                mod["name"], had_traversal = _sanitize_path(mod["name"])
                if had_traversal:
                    logger.warning("Sanitized path traversal in module name")

    return result


def sanitize_manifest(manifest_data: dict[str, Any]) -> dict[str, Any]:
    """Sanitize a loaded manifest dict. Returns cleaned copy.

    Applies: null byte stripping, zero-width removal, NFKC normalization,
    homoglyph replacement, Jinja2 delimiter escaping on non-template fields,
    path traversal prevention on template dest paths.
    """
    manifest = deepcopy(manifest_data)

    # Sanitize string fields (description, etc.)
    for key in ("name", "description", "version"):
        if key in manifest and isinstance(manifest[key], str):
            manifest[key] = _sanitize_string(manifest[key])

    # Sanitize template dest paths
    if "templates" in manifest and isinstance(manifest["templates"], list):
        for entry in manifest["templates"]:
            if isinstance(entry, dict) and "dest" in entry:
                dest = entry["dest"]
                if isinstance(dest, str):
                    entry["dest"] = _sanitize_string(dest, is_path=True)

    return manifest
