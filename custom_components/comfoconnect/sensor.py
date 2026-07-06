"""Sensor for the ComfoConnect integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Callable

from aiocomfoconnect.sensors import (
    SENSOR_AIRFLOW_CONSTRAINTS,
    SENSOR_ANALOG_INPUT_1,
    SENSOR_ANALOG_INPUT_2,
    SENSOR_ANALOG_INPUT_3,
    SENSOR_ANALOG_INPUT_4,
    SENSOR_AVOIDED_COOLING,
    SENSOR_AVOIDED_COOLING_TOTAL,
    SENSOR_AVOIDED_COOLING_TOTAL_YEAR,
    SENSOR_AVOIDED_HEATING,
    SENSOR_AVOIDED_HEATING_TOTAL,
    SENSOR_AVOIDED_HEATING_TOTAL_YEAR,
    SENSOR_BYPASS_STATE,
    SENSOR_CHANGING_FILTERS,
    SENSOR_COMFOCOOL_CONDENSOR_TEMP,
    SENSOR_COMFOFOND_GHE_STATE,
    SENSOR_COMFOFOND_TEMP_GROUND,
    SENSOR_COMFOFOND_TEMP_OUTDOOR,
    SENSOR_COMFORTCONTROL_MODE,
    SENSOR_DAYS_TO_REPLACE_FILTER,
    SENSOR_DEVICE_STATE,
    SENSOR_FAN_EXHAUST_DUTY,
    SENSOR_FAN_EXHAUST_FLOW,
    SENSOR_FAN_EXHAUST_SPEED,
    SENSOR_FAN_SPEED_MODE_MODULATED,
    SENSOR_FAN_SUPPLY_DUTY,
    SENSOR_FAN_SUPPLY_FLOW,
    SENSOR_FAN_SUPPLY_SPEED,
    SENSOR_HUMIDITY_AFTER_PREHEATER,
    SENSOR_HUMIDITY_EXHAUST,
    SENSOR_HUMIDITY_EXTRACT,
    SENSOR_HUMIDITY_OUTDOOR,
    SENSOR_HUMIDITY_SUPPLY,
    SENSOR_NEXT_CHANGE_BYPASS,
    SENSOR_NEXT_CHANGE_FAN,
    SENSOR_NEXT_CHANGE_FAN_EXHAUST,
    SENSOR_NEXT_CHANGE_FAN_SUPPLY,
    SENSOR_POWER_USAGE,
    SENSOR_POWER_USAGE_TOTAL,
    SENSOR_POWER_USAGE_TOTAL_YEAR,
    SENSOR_PREHEATER_POWER,
    SENSOR_PREHEATER_POWER_TOTAL,
    SENSOR_PREHEATER_POWER_TOTAL_YEAR,
    SENSOR_RF_PAIRING_MODE,
    SENSOR_RMOT,
    SENSOR_TARGET_TEMPERATURE,
    SENSOR_TEMPERATURE_EXHAUST,
    SENSOR_TEMPERATURE_EXTRACT,
    SENSOR_TEMPERATURE_OUTDOOR,
    SENSOR_TEMPERATURE_SUPPLY,
    SENSOR_UNIT_AIRFLOW,
    SENSOR_UNIT_TEMPERATURE,
    SENSORS,
)
from aiocomfoconnect.sensors import (
    Sensor as AioComfoConnectSensor,
)
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    REVOLUTIONS_PER_MINUTE,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
    UnitOfVolumeFlowRate,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import Throttle

from . import DOMAIN, SIGNAL_COMFOCONNECT_UPDATE_RECEIVED, ComfoConnectBridge

_LOGGER = logging.getLogger(__name__)

MIN_TIME_BETWEEN_UPDATES = timedelta(seconds=10)
NO_SCHEDULED_CHANGE_VALUES = {-1, 0xFFFFFFFF}

DEVICE_STATE = {
    0: "init",
    1: "normal",
    2: "filter_wizard",
    3: "commissioning",
    4: "supplier_factory",
    5: "zehnder_factory",
    6: "standby",
    7: "away",
    8: "dfc",
}
CHANGING_FILTERS_STATE = {
    0: "idle",
    1: "active",
    2: "changing_filter",
}
RF_PAIRING_STATE = {
    0: "not_running",
    1: "running",
    2: "done",
    3: "failed",
    4: "aborted",
}
COMFORT_CONTROL_STATE = {
    0: "disabled",
    1: "active",
    2: "overruling",
}


def _next_change_value(value: int) -> int | None:
    """Map the bridge no-change sentinel to an unknown HA duration."""
    return None if value in NO_SCHEDULED_CHANGE_VALUES else value


@dataclass
class ComfoconnectRequiredKeysMixin:
    """Mixin for required keys."""

    ccb_sensor: AioComfoConnectSensor


@dataclass
class ComfoconnectSensorEntityDescription(SensorEntityDescription, ComfoconnectRequiredKeysMixin):
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
        key=SENSOR_DEVICE_STATE,
        name="Device state",
        icon="mdi:list-status",
        ccb_sensor=SENSORS.get(SENSOR_DEVICE_STATE),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
        mapping=lambda x: DEVICE_STATE.get(x, x),
    ),
    ComfoconnectSensorEntityDescription(
        key=SENSOR_CHANGING_FILTERS,
        name="Changing filters",
        icon="mdi:air-filter",
        ccb_sensor=SENSORS.get(SENSOR_CHANGING_FILTERS),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
        mapping=lambda x: CHANGING_FILTERS_STATE.get(x, x),
    ),
    ComfoconnectSensorEntityDescription(
        key=SENSOR_TARGET_TEMPERATURE,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        name="Target temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        ccb_sensor=SENSORS.get(SENSOR_TARGET_TEMPERATURE),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ComfoconnectSensorEntityDescription(
        key=SENSOR_UNIT_TEMPERATURE,
        name="Temperature unit",
        icon="mdi:thermometer",
        ccb_sensor=SENSORS.get(SENSOR_UNIT_TEMPERATURE),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ComfoconnectSensorEntityDescription(
        key=SENSOR_UNIT_AIRFLOW,
        name="Airflow unit",
        icon="mdi:fan",
        ccb_sensor=SENSORS.get(SENSOR_UNIT_AIRFLOW),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ComfoconnectSensorEntityDescription(
        key=SENSOR_COMFORTCONTROL_MODE,
        name="Sensor based ventilation state",
        icon="mdi:auto-fix",
        ccb_sensor=SENSORS.get(SENSOR_COMFORTCONTROL_MODE),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
        mapping=lambda x: COMFORT_CONTROL_STATE.get(x, x),
    ),
    ComfoconnectSensorEntityDescription(
        key=SENSOR_FAN_SPEED_MODE_MODULATED,
        state_class=SensorStateClass.MEASUREMENT,
        name="Modulated fan speed",
        native_unit_of_measurement=PERCENTAGE,
        icon="mdi:fan-clock",
        ccb_sensor=SENSORS.get(SENSOR_FAN_SPEED_MODE_MODULATED),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
        mapping=lambda x: x / 3,
        throttle=True,
    ),
    ComfoconnectSensorEntityDescription(
        key=SENSOR_NEXT_CHANGE_FAN,
        device_class=SensorDeviceClass.DURATION,
        name="Fan speed next change",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        icon="mdi:timer-outline",
        ccb_sensor=SENSORS.get(SENSOR_NEXT_CHANGE_FAN),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
        mapping=_next_change_value,
    ),
    ComfoconnectSensorEntityDescription(
        key=SENSOR_NEXT_CHANGE_BYPASS,
        device_class=SensorDeviceClass.DURATION,
        name="Bypass next change",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        icon="mdi:timer-outline",
        ccb_sensor=SENSORS.get(SENSOR_NEXT_CHANGE_BYPASS),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
        mapping=_next_change_value,
    ),
    ComfoconnectSensorEntityDescription(
        key=SENSOR_NEXT_CHANGE_FAN_SUPPLY,
        device_class=SensorDeviceClass.DURATION,
        name="Supply fan next change",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        icon="mdi:timer-outline",
        ccb_sensor=SENSORS.get(SENSOR_NEXT_CHANGE_FAN_SUPPLY),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
        mapping=_next_change_value,
    ),
    ComfoconnectSensorEntityDescription(
        key=SENSOR_NEXT_CHANGE_FAN_EXHAUST,
        device_class=SensorDeviceClass.DURATION,
        name="Exhaust fan next change",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        icon="mdi:timer-outline",
        ccb_sensor=SENSORS.get(SENSOR_NEXT_CHANGE_FAN_EXHAUST),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
        mapping=_next_change_value,
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
        key=SENSOR_POWER_USAGE_TOTAL_YEAR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        name="Ventilation year energy usage",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        ccb_sensor=SENSORS.get(SENSOR_POWER_USAGE_TOTAL_YEAR),
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
        key=SENSOR_PREHEATER_POWER_TOTAL_YEAR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        name="Preheater year energy usage",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        ccb_sensor=SENSORS.get(SENSOR_PREHEATER_POWER_TOTAL_YEAR),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
        throttle=True,
    ),
    ComfoconnectSensorEntityDescription(
        key=SENSOR_AVOIDED_HEATING,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        name="Avoided heating power",
        native_unit_of_measurement=UnitOfPower.WATT,
        ccb_sensor=SENSORS.get(SENSOR_AVOIDED_HEATING),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
        mapping=lambda x: x / 100,
        throttle=True,
    ),
    ComfoconnectSensorEntityDescription(
        key=SENSOR_AVOIDED_HEATING_TOTAL_YEAR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        name="Avoided heating year energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        ccb_sensor=SENSORS.get(SENSOR_AVOIDED_HEATING_TOTAL_YEAR),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
        throttle=True,
    ),
    ComfoconnectSensorEntityDescription(
        key=SENSOR_AVOIDED_HEATING_TOTAL,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        name="Avoided heating total energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        ccb_sensor=SENSORS.get(SENSOR_AVOIDED_HEATING_TOTAL),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
        throttle=True,
    ),
    ComfoconnectSensorEntityDescription(
        key=SENSOR_AVOIDED_COOLING,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        name="Avoided cooling power",
        native_unit_of_measurement=UnitOfPower.WATT,
        ccb_sensor=SENSORS.get(SENSOR_AVOIDED_COOLING),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
        mapping=lambda x: x / 100,
        throttle=True,
    ),
    ComfoconnectSensorEntityDescription(
        key=SENSOR_AVOIDED_COOLING_TOTAL_YEAR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        name="Avoided cooling year energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        ccb_sensor=SENSORS.get(SENSOR_AVOIDED_COOLING_TOTAL_YEAR),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
        throttle=True,
    ),
    ComfoconnectSensorEntityDescription(
        key=SENSOR_AVOIDED_COOLING_TOTAL,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        name="Avoided cooling total energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        ccb_sensor=SENSORS.get(SENSOR_AVOIDED_COOLING_TOTAL),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
        throttle=True,
    ),
    ComfoconnectSensorEntityDescription(
        key=SENSOR_HUMIDITY_AFTER_PREHEATER,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        name="Outdoor humidity after preheater",
        native_unit_of_measurement=PERCENTAGE,
        ccb_sensor=SENSORS.get(SENSOR_HUMIDITY_AFTER_PREHEATER),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ComfoconnectSensorEntityDescription(
        key=SENSOR_RF_PAIRING_MODE,
        name="RF pairing mode",
        icon="mdi:radio-tower",
        ccb_sensor=SENSORS.get(SENSOR_RF_PAIRING_MODE),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
        mapping=lambda x: RF_PAIRING_STATE.get(x, x),
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

    sensors = [ComfoConnectSensor(ccb=ccb, config_entry=config_entry, description=description) for description in SENSOR_TYPES]

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
                SIGNAL_COMFOCONNECT_UPDATE_RECEIVED.format(self._ccb.uuid, self.entity_description.key),
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
