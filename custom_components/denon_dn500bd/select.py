"""Select entities (settings with fixed choices) for the Denon DN-500BD MKII."""

from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import DenonConfigEntry, DenonCoordinator
from .definitions import SELECTS, SelectSetting
from .entity import DenonEntity

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DenonConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the selects the player reported during the probe."""
    coordinator = entry.runtime_data
    caps = coordinator.capabilities or set()
    async_add_entities(
        DenonSelect(coordinator, setting) for setting in SELECTS if setting.code in caps
    )


class DenonSelect(DenonEntity, SelectEntity):
    """A setting with a fixed list of choices."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: DenonCoordinator, setting: SelectSetting) -> None:
        """Initialise the select."""
        super().__init__(coordinator, setting.code.lower())
        self._setting = setting
        self._by_suffix = setting.readback or {
            suffix: option for option, suffix in setting.options.items()
        }
        self._expected = {option: suffix for suffix, option in self._by_suffix.items()}
        # For settings with a separate read-back table: None = not checked yet,
        # 0 = documented set codes are right, 1 = set codes are shifted too.
        self._shift: int | None = None if setting.readback else 0
        self._attr_translation_key = setting.key
        self._attr_options = list(setting.options)
        self._attr_entity_registry_enabled_default = setting.enabled_default
        if setting.icon:
            self._attr_icon = setting.icon

    @property
    def current_option(self) -> str | None:
        """Current choice; None when the player reports a value not in the list."""
        value = self.coordinator.data.get(self._setting.code)
        return None if value is None else self._by_suffix.get(value)

    def _command(self, option: str) -> str:
        suffix = self._setting.options[option]
        if self._shift and suffix.isdigit():
            return str(int(suffix) + self._shift)
        return suffix

    async def async_select_option(self, option: str) -> None:
        """Change the setting (and learn the set codes on the first change)."""
        code = self._setting.code
        before = self.coordinator.data.get(code)
        sent = self._command(option)
        if not await self.coordinator.async_set_setting(code, sent):
            return
        if self._shift is not None:
            return
        after = self.coordinator.data.get(code)
        if after == before:
            return  # nothing changed, nothing learned
        if after == self._expected.get(option):
            self._shift = 0
            _LOGGER.debug("%s: documented set codes confirmed", code)
        elif after == sent and sent.isdigit():
            # The player uses one table for setting and reporting: the
            # documented set codes are one too low. Correct it right away.
            self._shift = 1
            _LOGGER.debug("%s: set codes are shifted, correcting", code)
            await self.coordinator.async_set_setting(code, self._command(option))
