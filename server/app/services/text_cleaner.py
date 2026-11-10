"""Normalize text extracted from uploaded documents before storage."""

import unicodedata

_ALLOWED_CONTROLS = {"\n", "\t"}

_REMOVE_CODEPOINTS = {
    0x00AD,  # soft hyphen
    0x200B,  # zero width space
    0x200C,  # zero width non-joiner
    0x2060,  # word joiner
    0xFEFF,  # byte order mark
    *range(0x202A, 0x202F),  # bidi embedding/override
    *range(0x2066, 0x206A),  # bidi isolates
}
_REMOVE_TABLE = {code: None for code in _REMOVE_CODEPOINTS}

_LINE_SEPARATOR = chr(0x2028)
_PARAGRAPH_SEPARATOR = chr(0x2029)
_NO_BREAK_SPACE = chr(0x00A0)
_REPLACEMENT_CHARACTER = chr(0xFFFD)
_ZERO_WIDTH_JOINER = chr(0x200D)


def _is_allowed(char: str) -> bool:
    if char in _ALLOWED_CONTROLS:
        return True
    code = ord(char)
    if 0xD800 <= code <= 0xDFFF:
        return False
    category = unicodedata.category(char)
    if category == "Cf" and char != _ZERO_WIDTH_JOINER:
        return False
    return category != "Cc"


def sanitize_text(text: str) -> str:
    """Remove characters PostgreSQL or UTF-8 cannot safely store.

    Covers NUL/control characters, lone surrogates, BOM and zero-width
    characters, replacement characters from lossy decoding, and normalizes
    line endings and Unicode composition. Idempotent.
    """
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace(_LINE_SEPARATOR, "\n").replace(
        _PARAGRAPH_SEPARATOR, "\n"
    )
    text = text.translate(_REMOVE_TABLE)
    text = text.replace(_NO_BREAK_SPACE, " ").replace(
        _REPLACEMENT_CHARACTER, ""
    )
    text = "".join(char for char in text if _is_allowed(char))
    return unicodedata.normalize("NFC", text)
