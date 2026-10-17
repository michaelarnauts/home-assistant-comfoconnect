"""Number entities for the ComfoConnect integration."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from aiocomfoconnect.exceptions import (
    AioComfoConnectNotConnected,
    AioComfoConnectNotReachable,
    AioComfoConnectTimeout,
    ComfoConnectError,
)
from aiocomfoconnect.properties import PROPERTY_RMOT_COOLING_THRESHOLD, PROPERTY_RMOT_HEATING_THRESHOLD, Property
from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberEntityDescription, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DOMAIN, SIGNAL_COMFOCONNECT_AVAILABILITY, ComfoConnectBridge

_LOGGER = logging.getLogger(__name__)


@dataclass
class ComfoConnectNumberRequiredKeysMixin:
    """Mixin for required number keys."""

    property: Property
    get_value_fn: Callable[[ComfoConnectBridge], Awaitable[int]]
    set_value_fn: Callable[[ComfoConnectBridge, float], Awaitable[Any]]


@dataclass
class ComfoConnectNumberEntityDescription(NumberEntityDescription, ComfoConnectNumberRequiredKeysMixin):
    """Describe a ComfoConnect numeric setting."""


async def _set_threshold(ccb: ComfoConnectBridge, prop: Property, value: float) -> None:
    """Write a threshold in the unit's tenths of a degree."""
    await ccb.set_property_typed(prop.unit, prop.subunit, prop.property_id, round(value * 10), prop.property_type)


NUMBER_TYPES = (
    ComfoConnectNumberEntityDescription(
        key="rmot_heating",
        name="Heating RMOT threshold",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        mode=NumberMode.BOX,
        property=PROPERTY_RMOT_HEATING_THRESHOLD,
        get_value_fn=lambda ccb: ccb.get_property(PROPERTY_RMOT_HEATING_THRESHOLD),
        set_value_fn=lambda ccb, value: _set_threshold(ccb, PROPERTY_RMOT_HEATING_THRESHOLD, value),
    ),
    ComfoConnectNumberEntityDescription(
        key="rmot_cooling",
        name="Cooling RMOT threshold",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        mode=NumberMode.BOX,
        property=PROPERTY_RMOT_COOLING_THRESHOLD,
        get_value_fn=lambda ccb: ccb.get_property(PROPERTY_RMOT_COOLING_THRESHOLD),
        set_value_fn=lambda ccb, value: _set_threshold(ccb, PROPERTY_RMOT_COOLING_THRESHOLD, value),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the ComfoConnect numbers."""
    ccb = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities([ComfoConnectNumber(ccb, description) for description in NUMBER_TYPES], True)


class ComfoConnectNumber(NumberEntity):
    """Representation of a ComfoConnect RMOT threshold."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False
    _attr_has_entity_name = True
    entity_description: ComfoConnectNumberEntityDescription

    def __init__(self, ccb: ComfoConnectBridge, description: ComfoConnectNumberEntityDescription) -> None:
        """Initialize the number."""
        self._ccb = ccb
        self.entity_description = description
        self._attr_unique_id = f"{ccb.uuid}-{description.key}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, ccb.uuid)})
        self._attr_available = False

    async def async_added_to_hass(self) -> None:
        """Subscribe to bridge availability changes."""
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_COMFOCONNECT_AVAILABILITY.format(self._ccb.uuid), self._handle_availability_update)
        )

    @callback
    def _handle_availability_update(self, available: bool) -> None:
        """Wait for a fresh poll when the bridge recovers."""
        if not available:
            self._attr_available = False
            self.async_write_ha_state()
        else:
            self.async_schedule_update_ha_state(True)

    async def async_update(self) -> None:
        """Read the threshold and its device-specific limits."""
        if not self._ccb.is_available:
            self._attr_available = False
            return
        try:
            limits = await self._read_metadata(0x20)
            step = await self._read_metadata(0x40)
            if len(limits) != 2 or len(step) != 1 or limits[0] > limits[1] or step[0] <= 0:
                raise ValueError("Invalid RMOT property limits")
            value = await self.entity_description.get_value_fn(self._ccb)
        except (ComfoConnectError, AioComfoConnectTimeout, AioComfoConnectNotConnected, AioComfoConnectNotReachable, ValueError) as err:
            self._attr_available = False
            _LOGGER.warning("Could not update %s: %s", self.entity_description.name, err)
            return
        self._attr_native_min_value, self._attr_native_max_value = (limit / 10 for limit in limits)
        self._attr_native_step = step[0] / 10
        self._attr_native_value = value / 10
        self._attr_available = self._ccb.is_available

    async def async_set_native_value(self, value: float) -> None:
        """Write the threshold; read the reported value on the next update."""
        await self.entity_description.set_value_fn(self._ccb, value)

    async def _read_metadata(self, kind: int) -> list[int]:
        """Read signed 16-bit range or step metadata for this property."""
        prop = self.entity_description.property
        response = await self._ccb.cmd_rmi_request(bytes([0x01, prop.unit, prop.subunit, kind, prop.property_id]))
        data = bytes(response.message)
        if len(data) % 2:
            raise ValueError("Invalid RMOT property metadata")
        return [int.from_bytes(data[index : index + 2], "little", signed=True) for index in range(0, len(data), 2)]
