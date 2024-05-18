"""Sensor for the ComfoConnect integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Callable

from aiocomfoconnect.sensors import (
    SENSOR_ANALOG_INPUT_1,
    SENSOR_ANALOG_INPUT_2,
    SENSOR_ANALOG_INPUT_3,
    SENSOR_ANALOG_INPUT_4,
    SENSOR_BYPASS_STATE,
    SENSOR_COMFOFOND_GHE_STATE,
    SENSOR_COMFOFOND_TEMP_GROUND,
    SENSOR_COMFOFOND_TEMP_OUTDOOR,
    SENSOR_COMFOCOOL_CONDENSOR_TEMP,
    SENSOR_DAYS_TO_REPLACE_FILTER,
    SENSOR_FAN_EXHAUST_DUTY,
    SENSOR_FAN_EXHAUST_FLOW,
    SENSOR_FAN_EXHAUST_SPEED,
    SENSOR_FAN_SUPPLY_DUTY,
    SENSOR_FAN_SUPPLY_FLOW,
    SENSOR_FAN_SUPPLY_SPEED,
    SENSOR_HUMIDITY_EXHAUST,
    SENSOR_HUMIDITY_EXTRACT,
    SENSOR_HUMIDITY_OUTDOOR,
    SENSOR_HUMIDITY_SUPPLY,
    SENSOR_POWER_USAGE,
    SENSOR_POWER_USAGE_TOTAL,
    SENSOR_PREHEATER_POWER,
    SENSOR_PREHEATER_POWER_TOTAL,
    SENSOR_RMOT,
    SENSOR_TEMPERATURE_EXHAUST,
    SENSOR_TEMPERATURE_EXTRACT,
    SENSOR_TEMPERATURE_OUTDOOR,
    SENSOR_TEMPERATURE_SUPPLY,
    SENSORS,
    Sensor as AioComfoConnectSensor,
    SENSOR_AIRFLOW_CONSTRAINTS,
)
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfEnergy,
    PERCENTAGE,
    UnitOfPower,
    REVOLUTIONS_PER_MINUTE,
    UnitOfTemperature,
    UnitOfTime,
    UnitOfVolumeFlowRate,
    UnitOfElectricPotential,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import Throttle

from . import DOMAIN, SIGNAL_COMFOCONNECT_UPDATE_RECEIVED, ComfoConnectBridge

_LOGGER = logging.getLogger(__name__)

MIN_TIME_BETWEEN_UPDATES = timedelta(seconds=10)


@dataclass
class ComfoconnectRequiredKeysMixin:
    """Mixin for required keys."""

    ccb_sensor: AioComfoConnectSensor


@dataclass
class ComfoconnectSensorEntityDescription(
    SensorEntityDescription, ComfoconnectRequiredKeysMixin
):
    """Describes ComfoConnect sensor entity."""

    throttle: bool = False
    mapping: Callable = None


SENSOR_TYPES = (
    ComfoconnectSensorEntityDescription(
        key=SENSOR_TEMPERATURE_EXTRACT,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        name="Inside temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        ccb_sensor=SENSORS.get(SENSOR_TEMPERATURE_EXTRACT),
    ),
    ComfoconnectSensorEntityDescription(
        key=SENSOR_HUMIDITY_EXTRACT,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        name="Inside humidity",
        native_unit_of_measurement=PERCENTAGE,
        ccb_sensor=SENSORS.get(SENSOR_HUMIDITY_EXTRACT),
    ),
    ComfoconnectSensorEntityDescription(
        key=SENSOR_RMOT,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        name="Current RMOT",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        ccb_sensor=SENSORS.get(SENSOR_RMOT),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ComfoconnectSensorEntityDescription(
        key=SENSOR_TEMPERATURE_OUTDOOR,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        name="Outside temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        ccb_sensor=SENSORS.get(SENSOR_TEMPERATURE_OUTDOOR),
    ),
    ComfoconnectSensorEntityDescription(
        key=SENSOR_HUMIDITY_OUTDOOR,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        name="Outside humidity",
        native_unit_of_measurement=PERCENTAGE,
        ccb_sensor=SENSORS.get(SENSOR_HUMIDITY_OUTDOOR),
    ),
    ComfoconnectSensorEntityDescription(
        key=SENSOR_TEMPERATURE_SUPPLY,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        name="Supply temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        ccb_sensor=SENSORS.get(SENSOR_TEMPERATURE_SUPPLY),
    ),
    ComfoconnectSensorEntityDescription(
        key=SENSOR_HUMIDITY_SUPPLY,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        name="Supply humidity",
        native_unit_of_measurement=PERCENTAGE,
        ccb_sensor=SENSORS.get(SENSOR_HUMIDITY_SUPPLY),
    ),
    ComfoconnectSensorEntityDescription(
        key=SENSOR_FAN_SUPPLY_SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        name="Supply fan speed",
        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
        icon="mdi:fan-plus",
        ccb_sensor=SENSORS.get(SENSOR_FAN_SUPPLY_SPEED),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
        throttle=True,
    ),
    ComfoconnectSensorEntityDescription(
        key=SENSOR_FAN_SUPPLY_DUTY,
        state_class=SensorStateClass.MEASUREMENT,
        name="Supply fan duty",
        native_unit_of_measurement=PERCENTAGE,
        icon="mdi:fan-plus",
        ccb_sensor=SENSORS.get(SENSOR_FAN_SUPPLY_DUTY),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
        throttle=True,
    ),
    ComfoconnectSensorEntityDescription(
        key=SENSOR_FAN_EXHAUST_SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        name="Exhaust fan speed",
        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
        icon="mdi:fan-minus",
        ccb_sensor=SENSORS.get(SENSOR_FAN_EXHAUST_SPEED),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
        throttle=True,
    ),
    ComfoconnectSensorEntityDescription(
        key=SENSOR_FAN_EXHAUST_DUTY,
        state_class=SensorStateClass.MEASUREMENT,
        name="Exhaust fan duty",
        native_unit_of_measurement=PERCENTAGE,
        icon="mdi:fan-minus",
        ccb_sensor=SENSORS.get(SENSOR_FAN_EXHAUST_DUTY),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
        throttle=True,
    ),
    ComfoconnectSensorEntityDescription(
        key=SENSOR_TEMPERATURE_EXHAUST,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        name="Exhaust temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        ccb_sensor=SENSORS.get(SENSOR_TEMPERATURE_EXHAUST),
    ),
    ComfoconnectSensorEntityDescription(
        key=SENSOR_HUMIDITY_EXHAUST,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        name="Exhaust humidity",
        native_unit_of_measurement=PERCENTAGE,
        ccb_sensor=SENSORS.get(SENSOR_HUMIDITY_EXHAUST),
    ),
    ComfoconnectSensorEntityDescription(
        key=SENSOR_FAN_SUPPLY_FLOW,
        state_class=SensorStateClass.MEASUREMENT,
        name="Supply airflow",
        native_unit_of_measurement=UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR,
        icon="mdi:fan-plus",
        ccb_sensor=SENSORS.get(SENSOR_FAN_SUPPLY_FLOW),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
        throttle=True,
    ),
    ComfoconnectSensorEntityDescription(
        key=SENSOR_FAN_EXHAUST_FLOW,
        state_class=SensorStateClass.MEASUREMENT,
        name="Exhaust airflow",
        native_unit_of_measurement=UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR,
        icon="mdi:fan-minus",
        ccb_sensor=SENSORS.get(SENSOR_FAN_EXHAUST_FLOW),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
        throttle=True,
    ),
    ComfoconnectSensorEntityDescription(
        key=SENSOR_BYPASS_STATE,
        state_class=SensorStateClass.MEASUREMENT,
        name="Bypass state",
        native_unit_of_measurement=PERCENTAGE,
        icon="mdi:camera-iris",
        ccb_sensor=SENSORS.get(SENSOR_BYPASS_STATE),
    ),
    ComfoconnectSensorEntityDescription(
        key=SENSOR_DAYS_TO_REPLACE_FILTER,
        name="Days to replace filter",
        native_unit_of_measurement=UnitOfTime.DAYS,
        icon="mdi:calendar",
        ccb_sensor=SENSORS.get(SENSOR_DAYS_TO_REPLACE_FILTER),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ComfoconnectSensorEntityDescription(
        key=SENSOR_POWER_USAGE,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        name="Ventilation current power usage",
        native_unit_of_measurement=UnitOfPower.WATT,
        ccb_sensor=SENSORS.get(SENSOR_POWER_USAGE),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
        throttle=True,
    ),
    ComfoconnectSensorEntityDescription(
        key=SENSOR_POWER_USAGE_TOTAL,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        name="Ventilation total energy usage",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        ccb_sensor=SENSORS.get(SENSOR_POWER_USAGE_TOTAL),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
        throttle=True,
    ),
    ComfoconnectSensorEntityDescription(
        key=SENSOR_PREHEATER_POWER,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        name="Preheater current power usage",
        native_unit_of_measurement=UnitOfPower.WATT,
        ccb_sensor=SENSORS.get(SENSOR_PREHEATER_POWER),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
        throttle=True,
    ),
    ComfoconnectSensorEntityDescription(
        key=SENSOR_PREHEATER_POWER_TOTAL,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        name="Preheater total energy usage",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        ccb_sensor=SENSORS.get(SENSOR_PREHEATER_POWER_TOTAL),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
        throttle=True,
    ),
    ComfoconnectSensorEntityDescription(
        key=SENSOR_ANALOG_INPUT_1,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        name="Analog Input 1",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        ccb_sensor=SENSORS.get(SENSOR_ANALOG_INPUT_1),
        entity_category=EntityCategory.DIAGNOSTIC,
        throttle=True,
    ),
    ComfoconnectSensorEntityDescription(
        key=SENSOR_ANALOG_INPUT_2,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        name="Analog Input 2",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        ccb_sensor=SENSORS.get(SENSOR_ANALOG_INPUT_2),
        entity_category=EntityCategory.DIAGNOSTIC,
        throttle=True,
    ),
    ComfoconnectSensorEntityDescription(
        key=SENSOR_ANALOG_INPUT_3,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        name="Analog Input 3",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        ccb_sensor=SENSORS.get(SENSOR_ANALOG_INPUT_3),
        entity_category=EntityCategory.DIAGNOSTIC,
        throttle=True,
    ),
    ComfoconnectSensorEntityDescription(
        key=SENSOR_ANALOG_INPUT_4,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        name="Analog Input 4",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        ccb_sensor=SENSORS.get(SENSOR_ANALOG_INPUT_4),
        entity_category=EntityCategory.DIAGNOSTIC,
        throttle=True,
    ),
    ComfoconnectSensorEntityDescription(
        key=SENSOR_AIRFLOW_CONSTRAINTS,
        icon="mdi:fan-alert",
        name="Airflow Constraint",
        ccb_sensor=SENSORS.get(SENSOR_AIRFLOW_CONSTRAINTS),
        entity_category=EntityCategory.DIAGNOSTIC,
        mapping=lambda x: x[0] if x else "",
    ),
    ComfoconnectSensorEntityDescription(
        key=SENSOR_COMFOFOND_GHE_STATE,
        state_class=SensorStateClass.MEASUREMENT,
        name="ComfoFond GHE state",
        native_unit_of_measurement=PERCENTAGE,
        ccb_sensor=SENSORS.get(SENSOR_COMFOFOND_GHE_STATE),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ComfoconnectSensorEntityDescription(
        key=SENSOR_COMFOFOND_TEMP_GROUND,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        name="ComfoFond ground temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        ccb_sensor=SENSORS.get(SENSOR_COMFOFOND_TEMP_GROUND),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ComfoconnectSensorEntityDescription(
        key=SENSOR_COMFOFOND_TEMP_OUTDOOR,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        name="ComfoFond outdoor air temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        ccb_sensor=SENSORS.get(SENSOR_COMFOFOND_TEMP_OUTDOOR),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ComfoconnectSensorEntityDescription(
        key=SENSOR_COMFOCOOL_CONDENSOR_TEMP,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        name="ComfoCool condensor temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        ccb_sensor=SENSORS.get(SENSOR_COMFOCOOL_CONDENSOR_TEMP),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the ComfoConnect sensors."""
    ccb = hass.data[DOMAIN][config_entry.entry_id]

    sensors = [
        ComfoConnectSensor(ccb=ccb, config_entry=config_entry, description=description)
        for description in SENSOR_TYPES
    ]

    async_add_entities(sensors, True)


class ComfoConnectSensor(SensorEntity):
    """Representation of a ComfoConnect sensor."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    entity_description: ComfoconnectSensorEntityDescription

    def __init__(
        self,
        ccb: ComfoConnectBridge,
        config_entry: ConfigEntry,
        description: ComfoconnectSensorEntityDescription,
    ) -> None:
        """Initialize the ComfoConnect sensor."""
        self._ccb = ccb
        self.entity_description = description
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

        # If the sensor should be throttled, pass it through the Throttle utility
        if self.entity_description.throttle:
            update_handler = Throttle(MIN_TIME_BETWEEN_UPDATES)(self._handle_update)
        else:
            update_handler = self._handle_update

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_COMFOCONNECT_UPDATE_RECEIVED.format(
                    self._ccb.uuid, self.entity_description.key
                ),
                update_handler,
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

        if self.entity_description.mapping:
            self._attr_native_value = self.entity_description.mapping(value)
        else:
            self._attr_native_value = value
        self.schedule_update_ha_state()
