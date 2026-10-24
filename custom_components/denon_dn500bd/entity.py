"""Base entity for the Denon DN-500BD MKII."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_MODEL_ID, CONF_SW_VERSION, DOMAIN, MANUFACTURER, MODEL
from .coordinator import DenonCoordinator


class DenonEntity(CoordinatorEntity[DenonCoordinator]):
    """Common device info and availability."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: DenonCoordinator, key: str) -> None:
        """Initialise the entity."""
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            manufacturer=MANUFACTURER,
            model=MODEL,
            model_id=entry.data.get(CONF_MODEL_ID),
            sw_version=entry.data.get(CONF_SW_VERSION),
            name=entry.title,
        )

    @property
    def available(self) -> bool:
        """Unavailable while the player is offline (see the Connection sensor)."""
        return self.coordinator.data.online
