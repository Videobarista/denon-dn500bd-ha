"""Config flow for the Denon DN-500BD MKII."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers import selector

from .api import DenonClient, DenonConnectionError
from .const import (
    CONF_ADD_OFFLINE,
    CONF_CAPABILITIES,
    CONF_MODEL_ID,
    CONF_POLL_INTERVAL,
    CONF_REPROBE,
    CONF_SW_VERSION,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_PORT,
    DOMAIN,
    MAX_POLL_INTERVAL,
    MIN_POLL_INTERVAL,
    MODEL,
)
from .coordinator import DenonConfigEntry, ProbeResult, async_probe_player

_LOGGER = logging.getLogger(__name__)

# The player accepts a single connection; give it a moment to release ours
# before the integration opens its own.
_RELEASE_DELAY = 0.5


async def async_validate(host: str, port: int) -> ProbeResult:
    """Connect, probe the player once and disconnect again."""
    client = DenonClient(host, port)
    try:
        await client.connect()
        return await async_probe_player(client)
    finally:
        await client.close()


def _user_schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "")): str,
            vol.Required(CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_PORT)): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=65535)
            ),
            vol.Optional(CONF_ADD_OFFLINE, default=defaults.get(CONF_ADD_OFFLINE, False)): bool,
        }
    )


class DenonConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for the address of the player."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = user_input[CONF_PORT]
            await self.async_set_unique_id(host.lower())
            self._abort_if_unique_id_configured()
            data: dict[str, Any] = {CONF_HOST: host, CONF_PORT: port}
            try:
                result = await async_validate(host, port)
            except DenonConnectionError as err:
                _LOGGER.debug("Player %s:%s not reachable: %s", host, port, err)
                if user_input.get(CONF_ADD_OFFLINE):
                    # Capabilities are probed the first time the player answers.
                    data[CONF_CAPABILITIES] = None
                    return self.async_create_entry(title=MODEL, data=data)
                errors["base"] = "cannot_connect"
            else:
                data[CONF_CAPABILITIES] = result.capabilities
                data[CONF_MODEL_ID] = result.model_id
                data[CONF_SW_VERSION] = result.sw_version
                await asyncio.sleep(_RELEASE_DELAY)
                return self.async_create_entry(title=MODEL, data=data)
        return self.async_show_form(
            step_id="user", data_schema=_user_schema(user_input or {}), errors=errors
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the address of the player."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = user_input[CONF_PORT]
            if self._address_in_use(host, entry):
                return self.async_abort(reason="already_configured")
            if host == entry.data[CONF_HOST] and port == entry.data[CONF_PORT]:
                # Same player: the running integration holds its only connection.
                return self.async_update_reload_and_abort(entry)
            try:
                result = await async_validate(host, port)
            except DenonConnectionError as err:
                _LOGGER.debug("Player %s:%s not reachable: %s", host, port, err)
                errors["base"] = "cannot_connect"
            else:
                await asyncio.sleep(_RELEASE_DELAY)
                return self.async_update_reload_and_abort(
                    entry,
                    unique_id=host.lower(),
                    data_updates={
                        CONF_HOST: host,
                        CONF_PORT: port,
                        CONF_CAPABILITIES: result.capabilities,
                        CONF_MODEL_ID: result.model_id,
                        CONF_SW_VERSION: result.sw_version,
                    },
                )
        defaults = user_input or {
            CONF_HOST: entry.data[CONF_HOST],
            CONF_PORT: entry.data[CONF_PORT],
        }
        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=defaults[CONF_HOST]): str,
                vol.Required(CONF_PORT, default=defaults[CONF_PORT]): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=65535)
                ),
            }
        )
        return self.async_show_form(step_id="reconfigure", data_schema=schema, errors=errors)

    def _address_in_use(self, host: str, entry: DenonConfigEntry) -> bool:
        """True when another entry already uses this address."""
        return any(
            other.entry_id != entry.entry_id and other.unique_id == host.lower()
            for other in self._async_current_entries(include_ignore=False)
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: DenonConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return DenonOptionsFlow()


class DenonOptionsFlow(OptionsFlow):
    """Poll interval and re-probing of the supported features."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Manage the options."""
        entry = self.config_entry
        if user_input is not None:
            if user_input.pop(CONF_REPROBE, False):
                # Forget the cache; it is rebuilt the next time the player answers.
                self.hass.config_entries.async_update_entry(
                    entry, data={**entry.data, CONF_CAPABILITIES: None}
                )
            return self.async_create_entry(data=user_input)
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_POLL_INTERVAL,
                    default=entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=MIN_POLL_INTERVAL,
                        max=MAX_POLL_INTERVAL,
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="s",
                    )
                ),
                vol.Optional(CONF_REPROBE, default=False): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
