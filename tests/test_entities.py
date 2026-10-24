"""Entity states and the commands they send."""

from __future__ import annotations

from collections.abc import AsyncGenerator
import logging

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.core import HomeAssistant

from .common import entity_id, make_entry, setup_entry, unload_entry
from .fake_player import FakePlayer, wait_for


@pytest.fixture
async def entry(hass: HomeAssistant, player: FakePlayer) -> AsyncGenerator[MockConfigEntry]:
    """The integration set up against the fake player."""
    config_entry = make_entry(player.port)
    await setup_entry(hass, config_entry)
    # Settings are read right after setup; wait until the last one (mute) is in.
    player_id = entity_id(hass, config_entry, "media_player", "media_player")
    await wait_for(lambda: hass.states.get(player_id).attributes.get("is_volume_muted") is not None)
    yield config_entry
    await unload_entry(hass, config_entry)


def _state(hass: HomeAssistant, entry: MockConfigEntry, platform: str, key: str):
    return hass.states.get(entity_id(hass, entry, platform, key))


async def test_media_player_state(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Playing Blu-ray: state, chapter and time code in seconds."""
    state = _state(hass, entry, "media_player", "media_player")
    assert state.state == "playing"
    assert state.attributes["media_position"] == 73
    assert state.attributes["media_duration"] == 113
    assert state.attributes["media_track"] == 1
    assert state.attributes["media_content_type"] == "video"
    assert state.attributes["is_volume_muted"] is False
    assert "media_position_updated_at" in state.attributes


async def test_sensors(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Status sensors map the player's codes."""
    assert _state(hass, entry, "sensor", "connection").state == "online"
    assert _state(hass, entry, "sensor", "disc_status").state == "disc_in"
    assert _state(hass, entry, "sensor", "disc_type").state == "bd_video"
    assert _state(hass, entry, "sensor", "playback_status").state == "playing"
    assert _state(hass, entry, "sensor", "playback_chapter").state == "1"
    assert _state(hass, entry, "sensor", "playback_title").state == "87"
    assert _state(hass, entry, "sensor", "audio_format").state == "Dolby Digital"
    assert _state(hass, entry, "sensor", "audio_channels").state == "5.1"
    assert _state(hass, entry, "sensor", "audio_language").state == "eng"
    assert _state(hass, entry, "sensor", "subtitle_language").state == "unknown"


async def test_push_updates_state(
    hass: HomeAssistant, entry: MockConfigEntry, player: FakePlayer
) -> None:
    """Status pushed by the player shows up without waiting for a poll."""
    player.values["ST"] = "PP"
    player.push("STPP")
    player_id = entity_id(hass, entry, "media_player", "media_player")
    await wait_for(lambda: hass.states.get(player_id).state == "paused")


async def test_media_player_commands(
    hass: HomeAssistant, entry: MockConfigEntry, player: FakePlayer
) -> None:
    """Transport commands send the documented codes."""
    player_id = entity_id(hass, entry, "media_player", "media_player")
    for service, code in (
        ("media_pause", "2348"),
        ("media_play", "2353"),
        ("media_next_track", "2332"),
        ("media_previous_track", "2333"),
        ("media_stop", "2354"),
    ):
        await hass.services.async_call(
            "media_player", service, {"entity_id": player_id}, blocking=True
        )
        assert code in player.received
    await hass.services.async_call(
        "media_player",
        "volume_mute",
        {"entity_id": player_id, "is_volume_muted": True},
        blocking=True,
    )
    assert "mt00" in player.received
    await wait_for(lambda: hass.states.get(player_id).attributes.get("is_volume_muted") is True)


async def test_refused_command_is_not_an_error(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    player: FakePlayer,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A nack (unskippable disc content) is logged at debug only."""
    caplog.set_level(logging.DEBUG)
    player.nack.add("2332")
    player_id = entity_id(hass, entry, "media_player", "media_player")
    await hass.services.async_call(
        "media_player", "media_next_track", {"entity_id": player_id}, blocking=True
    )
    assert "2332" in player.received
    assert hass.states.get(player_id).state == "playing"
    assert not [
        record
        for record in caplog.records
        if record.levelno >= logging.WARNING and "denon_dn500bd" in record.name
    ]


async def test_number_rounds_to_step(
    hass: HomeAssistant, entry: MockConfigEntry, player: FakePlayer
) -> None:
    """Levels are whole numbers and rounded before sending."""
    number_id = entity_id(hass, entry, "number", "dvov")
    state = hass.states.get(number_id)
    assert state.state == "-3"
    assert state.attributes["step"] == 1
    await hass.services.async_call(
        "number", "set_value", {"entity_id": number_id, "value": 3.4}, blocking=True
    )
    assert "DVOV+03" in player.received
    await wait_for(lambda: hass.states.get(number_id).state == "3")


async def test_select_and_switch(
    hass: HomeAssistant, entry: MockConfigEntry, player: FakePlayer
) -> None:
    """Settings are sent and read back."""
    select_id = entity_id(hass, entry, "select", "dvvr")
    assert hass.states.get(select_id).state == "1080p"
    await hass.services.async_call(
        "select", "select_option", {"entity_id": select_id, "option": "720p"}, blocking=True
    )
    assert "DVVR4" in player.received
    await wait_for(lambda: hass.states.get(select_id).state == "720p")

    switch_id = entity_id(hass, entry, "switch", "pcap")
    assert hass.states.get(switch_id).state == "on"
    await hass.services.async_call("switch", "turn_off", {"entity_id": switch_id}, blocking=True)
    assert "PCAP01" in player.received
    await wait_for(lambda: hass.states.get(switch_id).state == "off")


async def test_unknown_setting_value(
    hass: HomeAssistant, entry: MockConfigEntry, player: FakePlayer
) -> None:
    """A value outside the documented list shows as unknown, not as an error."""
    player.values["DVVR"] = "7"
    player.push("DVVR7")
    select_id = entity_id(hass, entry, "select", "dvvr")
    await wait_for(lambda: hass.states.get(select_id).state == "unknown")


async def test_button(hass: HomeAssistant, entry: MockConfigEntry, player: FakePlayer) -> None:
    """Buttons send their remote-control code."""
    button_id = entity_id(hass, entry, "button", "menu_home")
    await hass.services.async_call("button", "press", {"entity_id": button_id}, blocking=True)
    assert "PCHM" in player.received
