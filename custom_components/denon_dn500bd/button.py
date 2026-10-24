"""Button entities (remote-control commands) for the Denon DN-500BD MKII."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import DenonConfigEntry, DenonCoordinator
from .definitions import BUTTONS, ButtonCommand
from .entity import DenonEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DenonConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the buttons."""
    coordinator = entry.runtime_data
    async_add_entities(DenonButton(coordinator, command) for command in BUTTONS)


class DenonButton(DenonEntity, ButtonEntity):
    """A remote-control command.

    The player may refuse a command (for example during unskippable disc
    content); that is logged at debug level only.
    """

    def __init__(self, coordinator: DenonCoordinator, command: ButtonCommand) -> None:
        """Initialise the button."""
        super().__init__(coordinator, command.key)
        self._command = command.command
        self._attr_translation_key = command.key
        self._attr_entity_registry_enabled_default = command.enabled_default
        if command.icon:
            self._attr_icon = command.icon

    async def async_press(self) -> None:
        """Send the command."""
        await self.coordinator.async_send_command(self._command)
