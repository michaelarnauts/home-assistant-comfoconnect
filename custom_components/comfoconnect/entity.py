"""Base entity for the ComfoConnect integration."""

from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from . import DOMAIN, SIGNAL_COMFOCONNECT_AVAILABILITY, ComfoConnectBridge


class ComfoConnectEntity(Entity):
    """An entity of the ventilation unit, available while the bridge has a session."""

    _attr_has_entity_name = True

    def __init__(self, ccb: ComfoConnectBridge) -> None:
        """Initialize the entity on the ventilation unit's device."""
        self._ccb = ccb
        self._attr_available = ccb.is_available
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, ccb.uuid)})

    async def async_added_to_hass(self) -> None:
        """Follow the bridge's availability."""
        self.async_on_remove(async_dispatcher_connect(self.hass, SIGNAL_COMFOCONNECT_AVAILABILITY.format(self._ccb.uuid), self._handle_availability))

    @callback
    def _handle_availability(self, available: bool) -> None:
        """Handle bridge availability changes."""
        self._attr_available = available
        self.async_write_ha_state()
