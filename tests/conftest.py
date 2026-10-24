"""Shared fixtures: a fake DN-500BD MKII that speaks the LAN protocol."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

import pytest

from custom_components.denon_dn500bd import config_flow as config_flow_module, const

from .fake_player import FakePlayer


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: Any) -> None:
    """Enable custom integrations in all tests."""


@pytest.fixture(autouse=True)
def auto_socket_enabled(socket_enabled: Any) -> None:
    """The fake player is a real TCP server on 127.0.0.1."""


@pytest.fixture(autouse=True)
def fast_timing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Shorten every timeout and back-off so the tests run quickly."""
    monkeypatch.setattr(const, "CONNECT_TIMEOUT", 1.0)
    monkeypatch.setattr(const, "REQUEST_TIMEOUT", 0.3)
    monkeypatch.setattr(const, "RETRY_FIRST", 0.1)
    monkeypatch.setattr(const, "RETRY_MAX", 0.3)
    monkeypatch.setattr(const, "FIRST_ATTEMPT_TIMEOUT", 3.0)
    monkeypatch.setattr(const, "COMMAND_GAP", 0.0)
    monkeypatch.setattr(const, "BURST_IDLE", 0.01)
    monkeypatch.setattr(const, "REFRESH_DELAY_PUSH", 0.05)
    monkeypatch.setattr(const, "REFRESH_DELAY_COMMAND", 0.05)
    monkeypatch.setattr(config_flow_module, "_RELEASE_DELAY", 0.0)


@pytest.fixture
async def player() -> AsyncGenerator[FakePlayer]:
    """A running fake player."""
    fake = FakePlayer()
    await fake.start()
    yield fake
    await fake.stop()
