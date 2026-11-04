"""Checks the fuzz target runs on every input.

The player's answers are the only untrusted bytes the integration reads.
Whatever arrives, the parser must not raise and its results must stay within
these limits. Used by ``fuzz_parser.py`` (Atheris) and by the test suite.
"""

from __future__ import annotations

import re
from types import ModuleType

_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]")
_MAX_HHHMMSS = 999 * 3600 + 59 * 60 + 59
_MAX_MMMSS = 999 * 60 + 59


def _require(condition: bool, what: str, value: object) -> None:
    if not condition:
        raise AssertionError(f"{what}: {value!r}")


def check(api: ModuleType, data: bytes) -> None:
    """Parse one burst and verify the results."""
    burst = api.parse_burst(data)
    _require(burst.marker in (None, "ack", "nack"), "unknown marker", burst.marker)
    _require(burst.bare is None or isinstance(burst.bare, str), "bare answer", burst.bare)
    for message in burst.messages:
        _require(bool(message), "empty message", burst.messages)
        _require("@0" not in message, "message not split", message)
        parts = api.split_message(message)
        if parts is not None:
            _require("".join(parts) == message, "split changed the message", parts)
    api.message_codes(burst.messages)

    text = data.decode("latin-1")
    for value in {text, text[:5], text[:7], text[:9], burst.bare or ""}:
        seconds = api.parse_hhhmmss(value)
        _require(seconds is None or 0 <= seconds <= _MAX_HHHMMSS, "hhhmmss", value)
        seconds = api.parse_mmmss(value)
        _require(seconds is None or 0 <= seconds <= _MAX_MMMSS, "mmmss", value)
        number = api.parse_number(value)
        _require(number is None or 0 <= number < 10**9, "number", value)
        level = api.parse_signed(value, -99)
        _require(level is None or isinstance(level, int), "signed", value)
        cleaned = api.clean_text(value)
        _require(
            cleaned is None or (cleaned == cleaned.strip() and not _CONTROL_RE.search(cleaned)),
            "clean_text",
            value,
        )
        try:
            api.validate_command(value)
        except api.DenonCommandError:
            continue
        _require(
            0 < len(value) <= api.const.MAX_PACKET - 3
            and all("\x21" <= char <= "\x7e" and char != "@" for char in value),
            "unsafe command accepted",
            value,
        )
