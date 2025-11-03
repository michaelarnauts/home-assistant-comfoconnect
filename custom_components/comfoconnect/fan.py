"""Fan for the ComfoConnect integration with Manual → Auto fix."""

from __future__ import annotations

import logging
import asyncio
from typing import Any

from aiocomfoconnect.const import VentilationMode, VentilationSpeed
from aiocomfoconnect.sensors import (
    SENSOR_FAN_SPEED_MODE,
    SENSOR_OPERATING_MODE,
    SENSORS,
)
from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util.percentage import (
    ordered_list_item_to_percentage,
    percentage_to_ordered_list_item,
)

from . import DOMAIN, SIGNAL_COMFOCONNECT_UPDATE_RECEIVED, ComfoConnectBridge

_LOGGER = logging.getLogger(__name__)

FAN_SPEEDS = [VentilationSpeed.LOW, VentilationSpeed.MEDIUM, VentilationSpeed.HIGH]
PRESET_MODES = [VentilationMode.AUTO, VentilationMode.MANUAL]

FAN_SPEED_MAPPING = {
    0: VentilationSpeed.AWAY,
    1: VentilationSpeed.LOW,
    2: VentilationSpeed.MEDIUM,
    3: VentilationSpeed.HIGH,
}

MODE_MAPPING = {
    -1: VentilationMode.AUTO,
     1: VentilationMode.MANUAL,
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the ComfoConnect fan."""
    ccb = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities([ComfoConnectFan(ccb=ccb, config_entry=config_entry)], True)


class ComfoConnectFan(FanEntity):
    """Representation of the ComfoConnect fan platform."""

    _attr_enable_turn_on_off_backwards_compatibility = False
    _attr_icon = "mdi:air-conditioner"
    _attr_should_poll = False
    _attr_supported_features = (
        FanEntityFeature.SET_SPEED
        | FanEntityFeature.PRESET_MODE
        | FanEntityFeature.TURN_ON
        | FanEntityFeature.TURN_OFF
    )
    _attr_preset_modes = list(PRESET_MODES)
    _attr_speed_count = len(FAN_SPEEDS)
    _attr_has_entity_name = True
    _attr_name = None

    def __init__(self, ccb: ComfoConnectBridge, config_entry: ConfigEntry) -> None:
        """Initialize the ComfoConnect fan."""
        self._ccb = ccb
        self._attr_unique_id = self._ccb.uuid
        self._attr_preset_mode = None
        self._attr_percentage = 0
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._ccb.uuid)},
            manufacturer="ComfoConnect",
            model="ComfoAir Q",
            name="ComfoAir Q Fan",
        )

    async def async_added_to_hass(self) -> None:
        """Register for sensor updates."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_COMFOCONNECT_UPDATE_RECEIVED.format(self._ccb.uuid, SENSOR_FAN_SPEED_MODE),
                self._handle_speed_update,
            )
        )
        await self._ccb.register_sensor(SENSORS.get(SENSOR_FAN_SPEED_MODE))

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_COMFOCONNECT_UPDATE_RECEIVED.format(self._ccb.uuid, SENSOR_OPERATING_MODE),
                self._handle_mode_update,
            )
        )
        await self._ccb.register_sensor(SENSORS.get(SENSOR_OPERATING_MODE))

    def _handle_speed_update(self, value: int) -> None:
        """Handle update callbacks."""
        speed = FAN_SPEED_MAPPING.get(value, VentilationSpeed.LOW)
        if speed == VentilationSpeed.AWAY:
            self._attr_percentage = 0
        else:
            self._attr_percentage = ordered_list_item_to_percentage(FAN_SPEEDS, speed)

        self.schedule_update_ha_state()

    def _handle_mode_update(self, value: int) -> None:
        """Handle update callbacks."""
        self._attr_preset_mode = MODE_MAPPING.get(value, VentilationMode.MANUAL)
        self.schedule_update_ha_state()

    @property
    def is_on(self) -> bool:
        """Return true if the fan is on."""
        return self._attr_percentage > 0

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Turn on the fan, ensuring it correctly goes to AUTO mode."""
        if not self.is_on:
            # Zet fan aan (standaard laag)
            if percentage is None:
                percentage = ordered_list_item_to_percentage(FAN_SPEEDS, VentilationSpeed.LOW)
            await self.async_set_percentage(percentage)

            # Forceer twee mode switches: Manual → Auto
            await self.async_set_preset_mode(VentilationMode.MANUAL)
            await asyncio.sleep(0.5)
            await self.async_set_preset_mode(VentilationMode.AUTO)
        else:
            # Fan is al aan, gewoon mode instellen als opgegeven
            if preset_mode:
                await self.async_set_preset_mode(preset_mode)
            if percentage is not None:
                await self.async_set_percentage(percentage)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the fan (set to away)."""
        await self.async_set_percentage(0)

    async def async_set_percentage(self, percentage: int) -> None:
        """Set fan speed percentage."""
        percentage = max(0, min(percentage, 100))

        if percentage == 0:
            speed = VentilationSpeed.AWAY
        else:
            speed = percentage_to_ordered_list_item(FAN_SPEEDS, percentage)

        await self._ccb.set_speed(speed)
        self._attr_percentage = percentage
        self.schedule_update_ha_state()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new preset mode."""
        if preset_mode not in self.preset_modes:
            _LOGGER.warning("Invalid preset mode: %s", preset_mode)
            return

        await self._ccb.set_mode(preset_mode)
        self._attr_preset_mode = preset_mode
        self.schedule_update_ha_state()
