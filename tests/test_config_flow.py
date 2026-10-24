"""Tests for the config, reconfigure and options flows."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import patch

import pytest

from custom_components.denon_dn500bd.const import (
    CONF_ADD_OFFLINE,
    CONF_CAPABILITIES,
    CONF_MODEL_ID,
    CONF_POLL_INTERVAL,
    CONF_POWER_ON_ENTITY,
    CONF_REPROBE,
    CONF_SW_VERSION,
    DOMAIN,
)
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from .common import make_entry
from .fake_player import FakePlayer, free_port


@pytest.fixture(autouse=True)
def mock_setup_entry() -> Generator[None]:
    """Do not set the integration up after a flow finishes."""
    with patch("custom_components.denon_dn500bd.async_setup_entry", return_value=True):
        yield


async def test_user_flow(hass: HomeAssistant, player: FakePlayer) -> None:
    """A reachable player is probed once and added."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "127.0.0.1", CONF_PORT: player.port}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Denon DN-500BD MKII"
    data = result["data"]
    assert data[CONF_HOST] == "127.0.0.1"
    assert data[CONF_PORT] == player.port
    assert data[CONF_MODEL_ID] == "DN-500BDUS"
    assert data[CONF_SW_VERSION] == "00004072"
    assert "mt" in data[CONF_CAPABILITIES]
    assert "DVOV" in data[CONF_CAPABILITIES]
    assert result["result"].unique_id == "127.0.0.1"


async def test_user_flow_only_reports_answered_settings(
    hass: HomeAssistant, player: FakePlayer
) -> None:
    """Settings the player does not answer are left out of the cache."""
    del player.values["DVPABN"]
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "127.0.0.1", CONF_PORT: player.port}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert "DVPABN" not in result["data"][CONF_CAPABILITIES]


async def test_user_flow_cannot_connect(hass: HomeAssistant) -> None:
    """An unreachable player shows an error and the form again."""
    port = free_port()
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "127.0.0.1", CONF_PORT: port}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}

    # Recovers once the player is there.
    fake = FakePlayer()
    await fake.start(port)
    try:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "127.0.0.1", CONF_PORT: port}
        )
    finally:
        await fake.stop()
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_add_offline(hass: HomeAssistant) -> None:
    """A switched off player can be added; it is probed later."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: "127.0.0.1", CONF_PORT: free_port(), CONF_ADD_OFFLINE: True},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_CAPABILITIES] is None


async def test_user_flow_already_configured(hass: HomeAssistant, player: FakePlayer) -> None:
    """The same address cannot be added twice."""
    make_entry(player.port).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "127.0.0.1", CONF_PORT: player.port}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reconfigure(hass: HomeAssistant, player: FakePlayer) -> None:
    """The address can be changed; it is validated first."""
    entry = make_entry(free_port())
    entry.add_to_hass(hass)

    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "127.0.0.1", CONF_PORT: free_port()}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "127.0.0.1", CONF_PORT: player.port}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_PORT] == player.port
    assert "mt" in entry.data[CONF_CAPABILITIES]


async def test_options_flow(hass: HomeAssistant, player: FakePlayer) -> None:
    """Poll interval is stored; re-probing clears the capability cache."""
    entry = make_entry(player.port)
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_POLL_INTERVAL: 15, CONF_POWER_ON_ENTITY: "script.denon_on", CONF_REPROBE: True},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {CONF_POLL_INTERVAL: 15, CONF_POWER_ON_ENTITY: "script.denon_on"}
    assert entry.data[CONF_CAPABILITIES] is None


async def test_reconfigure_same_address(hass: HomeAssistant) -> None:
    """Saving the same address does not need the player (it holds one connection)."""
    port = free_port()
    entry = make_entry(port)
    entry.add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "127.0.0.1", CONF_PORT: port}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
