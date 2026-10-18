"""Number entities for the ComfoConnect integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from aiocomfoconnect.exceptions import AioComfoConnectError
from aiocomfoconnect.properties import (
    PROPERTY_PROFILE_TEMPERATURE_COOL,
    PROPERTY_PROFILE_TEMPERATURE_NORMAL,
    PROPERTY_PROFILE_TEMPERATURE_WARM,
    PROPERTY_RMOT_COOLING_THRESHOLD,
    PROPERTY_RMOT_HEATING_THRESHOLD,
    Property,
)
from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberEntityDescription, NumberMode
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ComfoConnectBridge, ComfoConnectConfigEntry
from .const import DOMAIN
from .entity import ComfoConnectEntity

_LOGGER = logging.getLogger(__name__)

# One at a time: these entities poll or send commands, and the bridge doesn't like many requests at once.
PARALLEL_UPDATES = 1


@dataclass
class ComfoConnectNumberRequiredKeysMixin:
    """Mixin for required number keys."""

    property: Property


@dataclass
class ComfoConnectNumberEntityDescription(NumberEntityDescription, ComfoConnectNumberRequiredKeysMixin):
    """Describe a ComfoConnect numeric setting."""


NUMBER_TYPES = (
    ComfoConnectNumberEntityDescription(
        key="rmot_heating",
        translation_key="rmot_heating",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        mode=NumberMode.BOX,
        property=PROPERTY_RMOT_HEATING_THRESHOLD,
    ),
    ComfoConnectNumberEntityDescription(
        key="rmot_cooling",
        translation_key="rmot_cooling",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        mode=NumberMode.BOX,
        property=PROPERTY_RMOT_COOLING_THRESHOLD,
    ),
    # The profile temperatures are only used in the fixed temperature profile mode. The unit also stores them in adaptive mode.
    ComfoConnectNumberEntityDescription(
        key="profile_temperature_warm",
        translation_key="profile_temperature_warm",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        mode=NumberMode.BOX,
        property=PROPERTY_PROFILE_TEMPERATURE_WARM,
    ),
    ComfoConnectNumberEntityDescription(
        key="profile_temperature_normal",
        translation_key="profile_temperature_normal",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        mode=NumberMode.BOX,
        property=PROPERTY_PROFILE_TEMPERATURE_NORMAL,
    ),
    ComfoConnectNumberEntityDescription(
        key="profile_temperature_cool",
        translation_key="profile_temperature_cool",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        mode=NumberMode.BOX,
        property=PROPERTY_PROFILE_TEMPERATURE_COOL,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ComfoConnectConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the ComfoConnect numbers."""
    ccb = config_entry.runtime_data
    async_add_entities([ComfoConnectNumber(ccb, description) for description in NUMBER_TYPES], True)


class ComfoConnectNumber(ComfoConnectEntity, NumberEntity):
    """Representation of a ComfoConnect temperature setting."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False
    entity_description: ComfoConnectNumberEntityDescription

    def __init__(self, ccb: ComfoConnectBridge, description: ComfoConnectNumberEntityDescription) -> None:
        """Initialize the number."""
        super().__init__(ccb)
        self.entity_description = description
        self._attr_unique_id = f"{ccb.uuid}-{description.key}"
        # Unavailable until the first poll has read the value and its limits.
        self._attr_available = False

    @callback
    def _handle_availability(self, available: bool) -> None:
        """Wait for a fresh poll when the bridge recovers."""
        if not available:
            self._attr_available = False
            self.async_write_ha_state()
        else:
            self.async_schedule_update_ha_state(True)

    async def async_update(self) -> None:
        """Read the temperature and its device-specific limits."""
        if not self._ccb.is_available:
            self._attr_available = False
            return
        try:
            # One request returns the value together with the range and step size the unit accepts.
            constraints = await self._ccb.get_property_constraints(self.entity_description.property)
            if constraints.minimum > constraints.maximum or constraints.step <= 0:
                raise ValueError("Invalid property limits")
        except (AioComfoConnectError, ValueError) as err:
            self._attr_available = False
            _LOGGER.warning("Could not update %s: %s", self.entity_id, err)
            return
        self._attr_native_value = constraints.value
        self._attr_native_min_value = constraints.minimum
        self._attr_native_max_value = constraints.maximum
        self._attr_native_step = constraints.step
        self._attr_available = self._ccb.is_available

    async def async_set_native_value(self, value: float) -> None:
        """Write the temperature, then read back what the unit reports."""
        try:
            await self._ccb.set_property(self.entity_description.property, value)
        except AioComfoConnectError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="set_failed", translation_placeholders={"entity": self.name, "error": str(err)}
            ) from err
        self.async_schedule_update_ha_state(True)
