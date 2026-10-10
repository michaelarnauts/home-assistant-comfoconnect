"""Number for the ComfoConnect integration."""

from __future__ import annotations

import logging
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Any, Callable

from aiocomfoconnect.properties import (
    PROPERTY_CLIME_COOLING_COMFORT_TEMP,
    PROPERTY_CLIME_COOLING_KNEE_POINT,
    PROPERTY_CLIME_COOLING_TEMP_LIMIT,
    PROPERTY_CLIME_HEATING_COMFORT_TEMP,
    PROPERTY_CLIME_HEATING_DELTA,
    PROPERTY_CLIME_HEATING_KNEE_POINT,
    PROPERTY_CLIME_HEATPUMP_MAX_TEMP,
    PROPERTY_CLIME_HEATPUMP_MIN_TEMP,
    PROPERTY_CLIME_MANUAL_TARGET_TEMP,
    PROPERTY_RMOT_COOLING_THRESHOLD,
    PROPERTY_RMOT_HEATING_THRESHOLD,
    Property,
)
from homeassistant.components.number import NumberEntity, NumberEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DOMAIN, SIGNAL_COMFOCONNECT_AVAILABILITY, ComfoConnectBridge

_LOGGER = logging.getLogger(__name__)


@dataclass
class ComfoconnectNumberDescriptionMixin:
    """Mixin for required keys."""

    set_value_fn: Callable[[ComfoConnectBridge, float], Awaitable[Any]]
    get_value_fn: Callable[[ComfoConnectBridge], Awaitable[Any]]


@dataclass
class ComfoconnectNumberEntityDescription(NumberEntityDescription, ComfoconnectNumberDescriptionMixin):
    """Describes ComfoConnect number entity."""


def _comfoclime_temperature_getter(prop: Property) -> Callable[[ComfoConnectBridge], Awaitable[Any]]:
    """Build a getter for a ComfoClime temperature, which is stored in tenths of a degree."""

    async def get_value(ccb: ComfoConnectBridge) -> float:
        return await ccb.get_comfoclime_property(prop) / 10

    return get_value


def _comfoclime_temperature_setter(prop: Property) -> Callable[[ComfoConnectBridge, float], Awaitable[Any]]:
    """Build a setter for a ComfoClime temperature, which is stored in tenths of a degree."""

    async def set_value(ccb: ComfoConnectBridge, value: float) -> None:
        await ccb.set_comfoclime_property(prop, round(value * 10))

    return set_value


def _temperature_getter(prop: Property) -> Callable[[ComfoConnectBridge], Awaitable[Any]]:
    """Build a getter for a ventilation unit temperature, which is stored in tenths of a degree."""

    async def get_value(ccb: ComfoConnectBridge) -> float:
        return await ccb.get_property(prop) / 10

    return get_value


def _temperature_setter(prop: Property) -> Callable[[ComfoConnectBridge, float], Awaitable[Any]]:
    """Build a setter for a ventilation unit temperature, which is stored in tenths of a degree."""

    async def set_value(ccb: ComfoConnectBridge, value: float) -> None:
        await ccb.set_property_typed(prop.unit, prop.subunit, prop.property_id, round(value * 10), prop.property_type)

    return set_value


COMFOCLIME_NUMBER_TYPES = (
    ComfoconnectNumberEntityDescription(
        key="comfoclime_heating_comfort_temperature",
        name="Heating comfort temperature",
        entity_category=EntityCategory.CONFIG,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=15,
        native_max_value=25,
        native_step=0.5,
        get_value_fn=_comfoclime_temperature_getter(PROPERTY_CLIME_HEATING_COMFORT_TEMP),
        set_value_fn=_comfoclime_temperature_setter(PROPERTY_CLIME_HEATING_COMFORT_TEMP),
    ),
    ComfoconnectNumberEntityDescription(
        key="comfoclime_cooling_comfort_temperature",
        name="Cooling comfort temperature",
        entity_category=EntityCategory.CONFIG,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=20,
        native_max_value=28,
        native_step=0.5,
        get_value_fn=_comfoclime_temperature_getter(PROPERTY_CLIME_COOLING_COMFORT_TEMP),
        set_value_fn=_comfoclime_temperature_setter(PROPERTY_CLIME_COOLING_COMFORT_TEMP),
    ),
    ComfoconnectNumberEntityDescription(
        key="comfoclime_manual_target_temperature",
        name="Manual target temperature",
        entity_category=EntityCategory.CONFIG,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=18,
        native_max_value=28,
        native_step=0.5,
        get_value_fn=_comfoclime_temperature_getter(PROPERTY_CLIME_MANUAL_TARGET_TEMP),
        set_value_fn=_comfoclime_temperature_setter(PROPERTY_CLIME_MANUAL_TARGET_TEMP),
    ),
    ComfoconnectNumberEntityDescription(
        key="comfoclime_heating_knee_point",
        name="Heating knee point",
        entity_category=EntityCategory.CONFIG,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=5,
        native_max_value=15,
        native_step=0.5,
        entity_registry_enabled_default=False,
        get_value_fn=_comfoclime_temperature_getter(PROPERTY_CLIME_HEATING_KNEE_POINT),
        set_value_fn=_comfoclime_temperature_setter(PROPERTY_CLIME_HEATING_KNEE_POINT),
    ),
    ComfoconnectNumberEntityDescription(
        key="comfoclime_cooling_knee_point",
        name="Cooling knee point",
        entity_category=EntityCategory.CONFIG,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=15,
        native_max_value=25,
        native_step=0.5,
        entity_registry_enabled_default=False,
        get_value_fn=_comfoclime_temperature_getter(PROPERTY_CLIME_COOLING_KNEE_POINT),
        set_value_fn=_comfoclime_temperature_setter(PROPERTY_CLIME_COOLING_KNEE_POINT),
    ),
    ComfoconnectNumberEntityDescription(
        key="comfoclime_cooling_temperature_limit",
        name="Cooling temperature limit",
        entity_category=EntityCategory.CONFIG,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=20,
        native_max_value=28,
        native_step=0.5,
        entity_registry_enabled_default=False,
        get_value_fn=_comfoclime_temperature_getter(PROPERTY_CLIME_COOLING_TEMP_LIMIT),
        set_value_fn=_comfoclime_temperature_setter(PROPERTY_CLIME_COOLING_TEMP_LIMIT),
    ),
    ComfoconnectNumberEntityDescription(
        key="comfoclime_heating_reduction_delta",
        name="Heating reduction delta",
        entity_category=EntityCategory.CONFIG,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=0,
        native_max_value=5,
        native_step=0.5,
        entity_registry_enabled_default=False,
        get_value_fn=_comfoclime_temperature_getter(PROPERTY_CLIME_HEATING_DELTA),
        set_value_fn=_comfoclime_temperature_setter(PROPERTY_CLIME_HEATING_DELTA),
    ),
    ComfoconnectNumberEntityDescription(
        key="comfoclime_heatpump_min_temperature",
        name="Heat pump minimum temperature",
        entity_category=EntityCategory.CONFIG,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=10,
        native_max_value=17,
        native_step=1,
        entity_registry_enabled_default=False,
        get_value_fn=_comfoclime_temperature_getter(PROPERTY_CLIME_HEATPUMP_MIN_TEMP),
        set_value_fn=_comfoclime_temperature_setter(PROPERTY_CLIME_HEATPUMP_MIN_TEMP),
    ),
    ComfoconnectNumberEntityDescription(
        key="comfoclime_heatpump_max_temperature",
        name="Heat pump maximum temperature",
        entity_category=EntityCategory.CONFIG,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=40,
        native_max_value=60,
        native_step=1,
        entity_registry_enabled_default=False,
        get_value_fn=_comfoclime_temperature_getter(PROPERTY_CLIME_HEATPUMP_MAX_TEMP),
        set_value_fn=_comfoclime_temperature_setter(PROPERTY_CLIME_HEATPUMP_MAX_TEMP),
    ),
)

# These live on the ventilation unit, but are only meaningful when a ComfoClime drives the seasons.
COMFOCLIME_UNIT_NUMBER_TYPES = (
    ComfoconnectNumberEntityDescription(
        key="rmot_heating_threshold",
        name="RMOT heating threshold",
        entity_category=EntityCategory.CONFIG,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=5,
        native_max_value=20,
        native_step=0.5,
        entity_registry_enabled_default=False,
        get_value_fn=_temperature_getter(PROPERTY_RMOT_HEATING_THRESHOLD),
        set_value_fn=_temperature_setter(PROPERTY_RMOT_HEATING_THRESHOLD),
    ),
    ComfoconnectNumberEntityDescription(
        key="rmot_cooling_threshold",
        name="RMOT cooling threshold",
        entity_category=EntityCategory.CONFIG,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=5,
        native_max_value=35,
        native_step=0.5,
        entity_registry_enabled_default=False,
        get_value_fn=_temperature_getter(PROPERTY_RMOT_COOLING_THRESHOLD),
        set_value_fn=_temperature_setter(PROPERTY_RMOT_COOLING_THRESHOLD),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the ComfoConnect numbers."""
    ccb = hass.data[DOMAIN][config_entry.entry_id]

    if not ccb.comfoclime_serial:
        return

    numbers = [ComfoConnectNumber(ccb=ccb, description=description, device_id=ccb.comfoclime_serial) for description in COMFOCLIME_NUMBER_TYPES]
    numbers += [ComfoConnectNumber(ccb=ccb, description=description) for description in COMFOCLIME_UNIT_NUMBER_TYPES]

    async_add_entities(numbers, True)


class ComfoConnectNumber(NumberEntity):
    """Representation of a ComfoConnect number."""

    _attr_has_entity_name = True
    entity_description: ComfoconnectNumberEntityDescription

    def __init__(
        self,
        ccb: ComfoConnectBridge,
        description: ComfoconnectNumberEntityDescription,
        device_id: str | None = None,
    ) -> None:
        """Initialize the ComfoConnect number."""
        self._ccb = ccb
        self.entity_description = description
        self._attr_unique_id = f"{self._ccb.uuid}-{description.key}"
        self._attr_available = ccb.is_available
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id or self._ccb.uuid)},
        )

    async def async_added_to_hass(self) -> None:
        """Register for availability changes."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_COMFOCONNECT_AVAILABILITY.format(self._ccb.uuid),
                self._handle_availability_update,
            )
        )

    @callback
    def _handle_availability_update(self, available: bool) -> None:
        """Handle bridge availability changes."""
        self._attr_available = available
        self.async_write_ha_state()

    async def async_update(self) -> None:
        """Update the state."""
        self._attr_native_value = await self.entity_description.get_value_fn(self._ccb)

    async def async_set_native_value(self, value: float) -> None:
        """Set the value."""
        await self.entity_description.set_value_fn(self._ccb, value)
        self._attr_native_value = value
        self.async_write_ha_state()
