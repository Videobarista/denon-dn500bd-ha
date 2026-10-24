"""Setup, offline behaviour and reconnection."""

from __future__ import annotations

import asyncio
import logging

import pytest

from custom_components.denon_dn500bd.const import CONF_CAPABILITIES
from custom_components.denon_dn500bd.coordinator import DenonCoordinator
from custom_components.denon_dn500bd.diagnostics import async_get_config_entry_diagnostics
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_OFF, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .common import entity_id, make_entry, setup_entry, unload_entry
from .fake_player import FakePlayer, free_port, wait_for


def _integration_problems(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    """Warnings or errors logged by the integration itself."""
    return [
        record
        for record in caplog.records
        if record.levelno >= logging.WARNING and "denon_dn500bd" in record.name
    ]


async def test_setup_and_unload(hass: HomeAssistant, player: FakePlayer) -> None:
    """A reachable player is set up and cleanly unloaded."""
    entry = make_entry(player.port)
    await setup_entry(hass, entry)
    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get(entity_id(hass, entry, "sensor", "connection")).state == "online"
    await unload_entry(hass, entry)
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_player_off_is_a_state_not_an_error(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Switched off: setup succeeds, Connection says why, nothing above INFO is logged."""
    caplog.set_level(logging.DEBUG)
    entry = make_entry(free_port())
    await setup_entry(hass, entry)
    try:
        assert entry.state is ConfigEntryState.LOADED

        connection = hass.states.get(entity_id(hass, entry, "sensor", "connection"))
        assert connection.state == "offline"
        assert connection.attributes["reason"] == "connection_refused"
        assert hass.states.get(entity_id(hass, entry, "media_player", "media_player")).state == (
            STATE_OFF
        )
        assert (
            hass.states.get(entity_id(hass, entry, "sensor", "disc_status")).state
            == STATE_UNAVAILABLE
        )

        # Commands while offline: no exception, no error in the UI or log.
        player_id = entity_id(hass, entry, "media_player", "media_player")
        await hass.services.async_call(
            "media_player", "media_play", {"entity_id": player_id}, blocking=True
        )
        await hass.services.async_call(
            "media_player", "turn_on", {"entity_id": player_id}, blocking=True
        )
        assert not _integration_problems(caplog)
    finally:
        await unload_entry(hass, entry)


async def test_comes_back_online(hass: HomeAssistant) -> None:
    """The player is found again as soon as it answers, then fully refreshed."""
    port = free_port()
    entry = make_entry(port)
    await setup_entry(hass, entry)
    connection_id = entity_id(hass, entry, "sensor", "connection")
    assert hass.states.get(connection_id).state == "offline"

    fake = FakePlayer()
    await fake.start(port)
    try:
        await wait_for(lambda: hass.states.get(connection_id).state == "online")
        player_id = entity_id(hass, entry, "media_player", "media_player")
        await wait_for(lambda: hass.states.get(player_id).state == "playing")
        assert "?DVOV" in fake.received  # full refresh includes the settings
    finally:
        await unload_entry(hass, entry)
        await fake.stop()


async def test_dropped_connection_quick_check(hass: HomeAssistant, player: FakePlayer) -> None:
    """A dropped connection is re-opened right away without going offline."""
    entry = make_entry(player.port)
    await setup_entry(hass, entry)
    connection_id = entity_id(hass, entry, "sensor", "connection")
    seen: set[str] = set()
    try:
        count = len(player.received)
        await player.drop_connections()
        for _ in range(25):
            seen.add(hass.states.get(connection_id).state)
            await asyncio.sleep(0.02)
        await wait_for(lambda: len(player.received) > count + 3)
        assert seen == {"online"}
    finally:
        await unload_entry(hass, entry)


async def test_switched_off_while_running(hass: HomeAssistant, player: FakePlayer) -> None:
    """Switching the player off is noticed and shown as offline."""
    entry = make_entry(player.port)
    await setup_entry(hass, entry)
    connection_id = entity_id(hass, entry, "sensor", "connection")
    player_id = entity_id(hass, entry, "media_player", "media_player")
    try:
        await player.stop()
        await wait_for(lambda: hass.states.get(connection_id).state == "offline")
        assert hass.states.get(player_id).state == STATE_OFF
        assert hass.states.get(connection_id).attributes["reason"] in (
            "connection_refused",
            "connection_lost",
        )
    finally:
        await unload_entry(hass, entry)


async def test_standby_without_answer(hass: HomeAssistant, player: FakePlayer) -> None:
    """A player that stops answering goes offline with reason no_response."""
    entry = make_entry(player.port)
    await setup_entry(hass, entry)
    connection_id = entity_id(hass, entry, "sensor", "connection")
    try:
        player.respond = False
        await wait_for(lambda: hass.states.get(connection_id).state == "offline")
        assert hass.states.get(connection_id).attributes["reason"] == "no_response"
        player.respond = True
        await wait_for(lambda: hass.states.get(connection_id).state == "online")
    finally:
        await unload_entry(hass, entry)


async def test_capabilities_probed_when_added_offline(
    hass: HomeAssistant, player: FakePlayer
) -> None:
    """An entry added while the player was off gets its setting entities later."""
    entry = make_entry(player.port, capabilities=None)
    await setup_entry(hass, entry)
    try:
        await wait_for(lambda: entry.data[CONF_CAPABILITIES] is not None)
        await hass.async_block_till_done()
        await wait_for(lambda: entry.state is ConfigEntryState.LOADED)
        assert "DVOV" in entry.data[CONF_CAPABILITIES]
        output_level = entity_id(hass, entry, "number", "dvov")
        await wait_for(lambda: hass.states.get(output_level) is not None)
        await wait_for(lambda: hass.states.get(output_level).state == "-3")
    finally:
        await unload_entry(hass, entry)


async def test_diagnostics_redact_address(hass: HomeAssistant, player: FakePlayer) -> None:
    """Diagnostics never contain the address of the player."""
    entry = make_entry(player.port)
    await setup_entry(hass, entry)
    try:
        result = await async_get_config_entry_diagnostics(hass, entry)
        assert result["entry"]["host"] == "**REDACTED**"
        assert result["online"] is True
        assert "mt" in result["capabilities"]
        assert "127.0.0.1" not in str(result)
    finally:
        await unload_entry(hass, entry)


def test_no_accidental_coordinator_overrides() -> None:
    """Helpers must not shadow DataUpdateCoordinator internals (v1.0.0 bug)."""
    allowed = {"__init__", "async_shutdown"}
    base = set(dir(DataUpdateCoordinator))
    overridden = {
        name
        for name in vars(DenonCoordinator)
        if name in base and name not in allowed and not name.startswith("__")
    }
    assert not overridden
