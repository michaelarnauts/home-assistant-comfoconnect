"""Binary Sensor for the ComfoConnect integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from aiocomfoconnect.sensors import (
    SENSOR_COMFOCOOL_STATE,
    SENSOR_COMFOFOND_GHE_PRESENT,
    SENSOR_SEASON_COOLING_ACTIVE,
    SENSOR_SEASON_HEATING_ACTIVE,
    SENSORS,
)
from aiocomfoconnect.sensors import (
    Sensor as AioComfoConnectSensor,
)
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DOMAIN, SIGNAL_COMFOCONNECT_ALARM_RECEIVED, SIGNAL_COMFOCONNECT_UPDATE_RECEIVED, ComfoConnectBridge

_LOGGER = logging.getLogger(__name__)


@dataclass
class ComfoconnectRequiredKeysMixin:
    """Mixin for required keys."""

    ccb_sensor: AioComfoConnectSensor


@dataclass
class ComfoconnectBinarySensorEntityDescription(BinarySensorEntityDescription, ComfoconnectRequiredKeysMixin):
    """Describes ComfoConnect binary sensor entity."""


SENSOR_TYPES = (
    ComfoconnectBinarySensorEntityDescription(
        key=SENSOR_SEASON_HEATING_ACTIVE,
        name="Heating Season Active",
        ccb_sensor=SENSORS.get(SENSOR_SEASON_HEATING_ACTIVE),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ComfoconnectBinarySensorEntityDescription(
        key=SENSOR_SEASON_COOLING_ACTIVE,
        name="Cooling Season Active",
        ccb_sensor=SENSORS.get(SENSOR_SEASON_COOLING_ACTIVE),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ComfoconnectBinarySensorEntityDescription(
        key=SENSOR_COMFOFOND_GHE_PRESENT,
        name="ComfoFond GHE present",
        ccb_sensor=SENSORS.get(SENSOR_COMFOFOND_GHE_PRESENT),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ComfoconnectBinarySensorEntityDescription(
        key=SENSOR_COMFOCOOL_STATE,
        name="ComfoCool state",
        ccb_sensor=SENSORS.get(SENSOR_COMFOCOOL_STATE),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the ComfoConnect binary sensors."""
    ccb = hass.data[DOMAIN][config_entry.entry_id]

    sensors = [ComfoConnectBinarySensor(ccb=ccb, config_entry=config_entry, description=description) for description in SENSOR_TYPES]
    sensors.append(ComfoConnectAlarmBinarySensor(ccb=ccb))

    async_add_entities(sensors, True)


class ComfoConnectBinarySensor(BinarySensorEntity):
    """Representation of a ComfoConnect sensor."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    entity_description: ComfoconnectBinarySensorEntityDescription

    def __init__(
        self,
        ccb: ComfoConnectBridge,
        config_entry: ConfigEntry,
        description: ComfoconnectBinarySensorEntityDescription,
    ) -> None:
        """Initialize the ComfoConnect sensor."""
        self._ccb = ccb
        self.entity_description = description
        self._attr_name = f"{description.name}"
        self._attr_unique_id = f"{self._ccb.uuid}-{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._ccb.uuid)},
        )

    async def async_added_to_hass(self) -> None:
        """Register for sensor updates."""
        _LOGGER.debug(
            "Registering for sensor %s (%d)",
            self.entity_description.name,
            self.entity_description.key,
        )
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_COMFOCONNECT_UPDATE_RECEIVED.format(self._ccb.uuid, self.entity_description.key),
                self._handle_update,
            )
        )
        await self._ccb.register_sensor(self.entity_description.ccb_sensor)

    def _handle_update(self, value):
        """Handle update callbacks."""
        _LOGGER.debug(
            "Handle update for sensor %s (%d): %s",
            self.entity_description.name,
            self.entity_description.key,
            value,
        )

        self._attr_is_on = True if value else False
        self.schedule_update_ha_state()


class ComfoConnectAlarmBinarySensor(BinarySensorEntity):
    """Representation of active ComfoConnect alarms."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True
    _attr_name = "Active alarms"
    _attr_should_poll = False

    def __init__(self, ccb: ComfoConnectBridge) -> None:
        """Initialize the ComfoConnect alarm sensor."""
        self._ccb = ccb
        self._node_id = ccb.active_alarm_node_id
        self._errors = ccb.active_alarms
        self._attr_unique_id = f"{self._ccb.uuid}-active_alarms"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._ccb.uuid)},
        )
        self._update_state()

    async def async_added_to_hass(self) -> None:
        """Register for alarm updates."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_COMFOCONNECT_ALARM_RECEIVED.format(self._ccb.uuid),
                self._handle_update,
            )
        )

    @property
    def extra_state_attributes(self) -> dict:
        """Return alarm details."""
        return {
            "node_id": self._node_id,
            "alarm_count": len(self._errors),
            "alarms": [{"id": error_id, "message": error} for error_id, error in self._errors.items()],
        }

    def _handle_update(self, node_id: int, errors: dict[int, str]) -> None:
        """Handle alarm update callbacks."""
        self._node_id = node_id
        self._errors = errors
        self._update_state()
        self.schedule_update_ha_state()

    def _update_state(self) -> None:
        """Update the active alarm state."""
        self._attr_is_on = bool(self._errors)
