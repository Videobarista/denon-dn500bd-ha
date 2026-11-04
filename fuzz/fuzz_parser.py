"""Fuzz the parser of the player's answers with Atheris (libFuzzer).

Runs in CI (``.github/workflows/fuzz.yml``). Locally, on Linux or macOS with
Python 3.11-3.13:

    pip install -r requirements_fuzz.txt
    python fuzz/fuzz_parser.py -max_total_time=60 fuzz/corpus

Only ``api.py`` and its two sibling modules are loaded, so Home Assistant is
not needed.
"""

from __future__ import annotations

import importlib
from pathlib import Path
import sys
import types

import atheris

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = "custom_components.denon_dn500bd"


def _load_api() -> types.ModuleType:
    """Import api.py without the package's __init__ (which needs Home Assistant)."""
    for name, path in (
        ("custom_components", ROOT / "custom_components"),
        (PACKAGE, ROOT / "custom_components" / "denon_dn500bd"),
    ):
        package = types.ModuleType(name)
        package.__path__ = [str(path)]
        sys.modules[name] = package
    return importlib.import_module(f"{PACKAGE}.api")


with atheris.instrument_imports():
    api = _load_api()
    import parser_checks


def test_one_input(data: bytes) -> None:
    """LibFuzzer entry point: one burst from the 'player'."""
    parser_checks.check(api, data)


def main() -> None:
    """Start fuzzing; libFuzzer options come from the command line."""
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
