"""Binary Sensor for the ComfoConnect integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from aiocomfoconnect.sensors import (
    SENSOR_COMFOCOOL_STATE,
    SENSOR_COMFOFOND_GHE_PRESENT,
    SENSOR_POSTHEATER_PRESENT,
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
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import (
    SIGNAL_COMFOCONNECT_ALARM_RECEIVED,
    SIGNAL_COMFOCONNECT_UPDATE_RECEIVED,
    ComfoConnectBridge,
    ComfoConnectConfigEntry,
)
from .entity import ComfoConnectEntity

_LOGGER = logging.getLogger(__name__)

# Push only: the entities subscribe to their sensor once, they never poll or send commands.
PARALLEL_UPDATES = 0


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
        translation_key="heating_season_active",
        ccb_sensor=SENSORS.get(SENSOR_SEASON_HEATING_ACTIVE),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ComfoconnectBinarySensorEntityDescription(
        key=SENSOR_SEASON_COOLING_ACTIVE,
        translation_key="cooling_season_active",
        ccb_sensor=SENSORS.get(SENSOR_SEASON_COOLING_ACTIVE),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ComfoconnectBinarySensorEntityDescription(
        key=SENSOR_COMFOFOND_GHE_PRESENT,
        translation_key="comfofond_ghe_present",
        ccb_sensor=SENSORS.get(SENSOR_COMFOFOND_GHE_PRESENT),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ComfoconnectBinarySensorEntityDescription(
        key=SENSOR_POSTHEATER_PRESENT,
        translation_key="postheater_present",
        ccb_sensor=SENSORS.get(SENSOR_POSTHEATER_PRESENT),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ComfoconnectBinarySensorEntityDescription(
        key=SENSOR_COMFOCOOL_STATE,
        translation_key="comfocool_state",
        ccb_sensor=SENSORS.get(SENSOR_COMFOCOOL_STATE),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ComfoConnectConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the ComfoConnect binary sensors."""
    ccb = config_entry.runtime_data

    sensors = [ComfoConnectBinarySensor(ccb=ccb, config_entry=config_entry, description=description) for description in SENSOR_TYPES]
    sensors.append(ComfoConnectAlarmBinarySensor(ccb=ccb))

    async_add_entities(sensors)


class ComfoConnectBinarySensor(ComfoConnectEntity, BinarySensorEntity):
    """Representation of a ComfoConnect sensor."""

    _attr_should_poll = False
    entity_description: ComfoconnectBinarySensorEntityDescription

    def __init__(
        self,
        ccb: ComfoConnectBridge,
        config_entry: ComfoConnectConfigEntry,
        description: ComfoconnectBinarySensorEntityDescription,
    ) -> None:
        """Initialize the ComfoConnect sensor."""
        super().__init__(ccb)
        self.entity_description = description
        self._attr_unique_id = f"{self._ccb.uuid}-{description.key}"

    async def async_added_to_hass(self) -> None:
        """Register for sensor updates."""
        await super().async_added_to_hass()
        _LOGGER.debug(
            "Registering for sensor %s (%d)",
            self.entity_id,
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

    @callback
    def _handle_update(self, value):
        """Handle update callbacks."""
        _LOGGER.debug(
            "Handle update for sensor %s (%d): %s",
            self.entity_id,
            self.entity_description.key,
            value,
        )

        self._attr_is_on = bool(value)
        self.async_write_ha_state()


class ComfoConnectAlarmBinarySensor(ComfoConnectEntity, BinarySensorEntity):
    """Representation of active ComfoConnect alarms."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "active_alarms"
    _attr_should_poll = False

    def __init__(self, ccb: ComfoConnectBridge) -> None:
        """Initialize the ComfoConnect alarm sensor."""
        super().__init__(ccb)
        self._attr_unique_id = f"{self._ccb.uuid}-active_alarms"
        self._update_state()

    async def async_added_to_hass(self) -> None:
        """Register for alarm updates."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_COMFOCONNECT_ALARM_RECEIVED.format(self._ccb.uuid),
                self._handle_update,
            )
        )
        # Alarms can arrive before the entity is added, so read the cache again after subscribing.
        self._attr_available = self._ccb.is_available
        self._update_state()

    @callback
    def _handle_update(self) -> None:
        """Handle alarm update callbacks."""
        self._update_state()
        self.async_write_ha_state()

    def _update_state(self) -> None:
        """Update the active alarm state from the bridge cache."""
        alarms = [
            {"node_id": node_id, "id": error_id, "message": error}
            for node_id, errors in sorted(self._ccb.active_alarms.items())
            for error_id, error in errors.items()
        ]
        # Unknown until a node has reported its alarms.
        self._attr_is_on = bool(alarms) if self._ccb.active_alarms else None
        self._attr_extra_state_attributes = {"alarm_count": len(alarms), "alarms": alarms}
