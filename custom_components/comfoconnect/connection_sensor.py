"""Binary Sensor for the ComfoConnect integration."""
from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import DeviceInfo

from . import DOMAIN, ComfoConnectBridge, set_conn_update


_LOGGER = logging.getLogger(__name__)

COMFO_CONNECTION_SENSOR: ComfoConnectionSensor = None


def comfo_connection_sensor_initialize(
        ccb: ComfoConnectBridge,
        config_entry: ConfigEntry
) -> ComfoConnectionSensor:
    global COMFO_CONNECTION_SENSOR
    COMFO_CONNECTION_SENSOR = ComfoConnectionSensor(
        ccb=ccb, config_entry=config_entry
    )
    set_conn_update(comfo_connection_sensor_update)
    return COMFO_CONNECTION_SENSOR


def comfo_connection_sensor_update(value: bool) -> None:
    if COMFO_CONNECTION_SENSOR is not None:
        COMFO_CONNECTION_SENSOR.set_value(value)


class ComfoConnectionSensor(BinarySensorEntity):
    _attr_should_poll = False

    def __init__(
            self,
            ccb: ComfoConnectBridge,
            config_entry: ConfigEntry
    ) -> None:
        """Initialize the ComfoConnect sensor."""
        self._ccb = ccb
        self._attr_name = f"Connection"
        self._attr_unique_id = f"{config_entry.unique_id}-" + "connection"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._ccb.uuid)},
        )
        self._attr_is_on = None
        _LOGGER.error(
            "Initializing Comfoconnect connection sensor",
        )

    def set_to_none(self):
        self._attr_is_on = None

    async def async_added_to_hass(self) -> None:
        """Register for sensor updates."""
        _LOGGER.error(
            "Registering Comfoconnect connection sensor",
        )
        self.async_on_remove(self.set_to_none)

    def set_value(self, value) -> None:
        """Handle update callbacks."""
        _LOGGER.error(
            "Connection sensor update: %s",
            value,
        )

        self._attr_is_on = value
        self.schedule_update_ha_state()
