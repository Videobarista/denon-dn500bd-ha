"""Run the fuzz target's checks on the seed corpus and on random bursts.

CI also fuzzes the parser with Atheris (``fuzz/``); this keeps the checks
and the seeds exercised in the normal test run.
"""

from __future__ import annotations

from pathlib import Path
import random

import pytest

from custom_components.denon_dn500bd import api
from fuzz.parser_checks import check

CORPUS = Path(__file__).resolve().parent.parent / "fuzz" / "corpus"
_ALPHABET = b"@0123456789ackn+STPLtiETRMPCDG-NUL \r\n\x00\x7f\xa0\xff"


@pytest.mark.parametrize("seed", sorted(CORPUS.iterdir()), ids=lambda path: path.name)
def test_seed_corpus(seed: Path) -> None:
    """Every seed passes the checks."""
    check(api, seed.read_bytes())


def test_random_bursts() -> None:
    """Random bursts, mostly built from protocol characters, pass the checks."""
    rng = random.Random(500)  # noqa: S311 - test data, not cryptography
    for _ in range(5000):
        size = rng.randrange(0, 160)
        if rng.random() < 0.8:
            data = bytes(rng.choice(_ALPHABET) for _ in range(size))
        else:
            data = rng.randbytes(size)
        check(api, data)


def test_checks_catch_a_broken_parser() -> None:
    """The checks really fail when the parser misbehaves."""

    class Broken:
        def __getattr__(self, name: str):
            return getattr(api, name)

        @staticmethod
        def parse_number(value: str | None) -> int | None:
            return -1

    with pytest.raises(AssertionError, match="number"):
        check(Broken(), b"ack+0000001")
