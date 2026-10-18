"""Sensor for the ComfoConnect integration."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta

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
    SENSOR_COMFOCOOL_CONDENSOR_TEMP,
    SENSOR_COMFOFOND_GHE_STATE,
    SENSOR_COMFOFOND_TEMP_GROUND,
    SENSOR_COMFOFOND_TEMP_OUTDOOR,
    SENSOR_COMFORTCONTROL_MODE,
    SENSOR_DAYS_TO_REPLACE_FILTER,
    SENSOR_FAN_EXHAUST_DUTY,
    SENSOR_FAN_EXHAUST_FLOW,
    SENSOR_FAN_EXHAUST_SPEED,
    SENSOR_FAN_SUPPLY_DUTY,
    SENSOR_FAN_SUPPLY_FLOW,
    SENSOR_FAN_SUPPLY_SPEED,
    SENSOR_HUMIDITY_AFTER_PREHEATER,
    SENSOR_HUMIDITY_EXHAUST,
    SENSOR_HUMIDITY_EXTRACT,
    SENSOR_HUMIDITY_OUTDOOR,
    SENSOR_HUMIDITY_SUPPLY,
    SENSOR_POSTHEATER_STATE,
    SENSOR_POSTHEATER_TEMPERATURE_BEFORE,
    SENSOR_POWER_USAGE,
    SENSOR_POWER_USAGE_TOTAL,
    SENSOR_POWER_USAGE_TOTAL_YEAR,
    SENSOR_PREHEATER_POWER,
    SENSOR_PREHEATER_POWER_TOTAL,
    SENSOR_PREHEATER_POWER_TOTAL_YEAR,
    SENSOR_RMOT,
    SENSOR_TARGET_TEMPERATURE,
    SENSOR_TEMPERATURE_EXHAUST,
    SENSOR_TEMPERATURE_EXTRACT,
    SENSOR_TEMPERATURE_OUTDOOR,
    SENSOR_TEMPERATURE_SUPPLY,
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
from homeassistant.const import (
    PERCENTAGE,
    REVOLUTIONS_PER_MINUTE,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfRatio,
    UnitOfTemperature,
    UnitOfTime,
    UnitOfVolumeFlowRate,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import (
    SIGNAL_COMFOCONNECT_UPDATE_RECEIVED,
    ComfoConnectBridge,
    ComfoConnectConfigEntry,
    co2_sensor_identifier,
)
from .entity import ComfoConnectEntity

_LOGGER = logging.getLogger(__name__)

# Push only: the entities subscribe to their sensor once, they never poll or send commands.
PARALLEL_UPDATES = 0

MIN_TIME_BETWEEN_UPDATES = timedelta(seconds=10)


COMFORT_CONTROL_STATE = {
    0: "disabled",
    1: "active",
    2: "overruling",
}


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
        key=SENSOR_HUMIDITY_AFTER_PREHEATER,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        name="Outside humidity after preheater",
        native_unit_of_measurement=PERCENTAGE,
        ccb_sensor=SENSORS.get(SENSOR_HUMIDITY_AFTER_PREHEATER),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
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
        device_class=SensorDeviceClass.VOLUME_FLOW_RATE,
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
        device_class=SensorDeviceClass.VOLUME_FLOW_RATE,
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
        device_class=SensorDeviceClass.DURATION,
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
        entity_registry_enabled_default=False,
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
        entity_registry_enabled_default=False,
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
        entity_registry_enabled_default=False,
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
        entity_registry_enabled_default=False,
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
        key=SENSOR_POSTHEATER_STATE,
        state_class=SensorStateClass.MEASUREMENT,
        name="Postheater state",
        native_unit_of_measurement=PERCENTAGE,
        icon="mdi:radiator",
        ccb_sensor=SENSORS.get(SENSOR_POSTHEATER_STATE),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ComfoconnectSensorEntityDescription(
        key=SENSOR_POSTHEATER_TEMPERATURE_BEFORE,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        name="Temperature before postheater",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        ccb_sensor=SENSORS.get(SENSOR_POSTHEATER_TEMPERATURE_BEFORE),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ComfoconnectSensorEntityDescription(
        key=SENSOR_COMFORTCONTROL_MODE,
        device_class=SensorDeviceClass.ENUM,
        options=list(COMFORT_CONTROL_STATE.values()),
        name="Sensor based ventilation state",
        icon="mdi:auto-fix",
        ccb_sensor=SENSORS.get(SENSOR_COMFORTCONTROL_MODE),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
        # An enum sensor only accepts its options, so an unknown state is shown as unknown.
        mapping=COMFORT_CONTROL_STATE.get,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ComfoConnectConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the ComfoConnect sensors."""
    ccb = config_entry.runtime_data

    sensors = [ComfoConnectSensor(ccb=ccb, config_entry=config_entry, description=description) for description in SENSOR_TYPES]
    sensors += [ComfoConnectCO2Sensor(ccb, config_entry, node_id, sensor_id) for node_id, sensor_id in ccb.co2_sensors]

    async_add_entities(sensors)


class ComfoConnectSensor(ComfoConnectEntity, SensorEntity):
    """Representation of a ComfoConnect sensor."""

    _attr_should_poll = False
    entity_description: ComfoconnectSensorEntityDescription

    def __init__(
        self,
        ccb: ComfoConnectBridge,
        config_entry: ComfoConnectConfigEntry,
        description: ComfoconnectSensorEntityDescription,
    ) -> None:
        """Initialize the ComfoConnect sensor."""
        super().__init__(ccb)
        self.entity_description = description
        self._attr_unique_id = f"{self._ccb.uuid}-{description.key}"
        self._debouncer: Debouncer | None = None

    async def async_added_to_hass(self) -> None:
        """Register for sensor updates."""
        await super().async_added_to_hass()
        _LOGGER.debug(
            "Registering for sensor %s (%d)",
            self.entity_description.name,
            self.entity_description.key,
        )

        # A throttled sensor writes its first update at once, then at most once per cooldown, and always ends with its latest value.
        if self.entity_description.throttle:
            self._debouncer = Debouncer(
                self.hass,
                _LOGGER,
                cooldown=MIN_TIME_BETWEEN_UPDATES.total_seconds(),
                immediate=True,
                function=self.async_write_ha_state,
            )
            self.async_on_remove(self._debouncer.async_shutdown)

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
            self.entity_description.name,
            self.entity_description.key,
            value,
        )

        if self.entity_description.mapping:
            self._attr_native_value = self.entity_description.mapping(value)
        else:
            self._attr_native_value = value
        if self._debouncer:
            self._debouncer.async_schedule_call()
        else:
            self.async_write_ha_state()


class ComfoConnectCO2Sensor(ComfoConnectSensor):
    """The CO2 level of a ComfoNet CO2 sensor, on the sensor's own device."""

    def __init__(self, ccb: ComfoConnectBridge, config_entry: ComfoConnectConfigEntry, node_id: int, sensor_id: int) -> None:
        """Initialize the CO2 sensor of a node."""
        super().__init__(
            ccb,
            config_entry,
            ComfoconnectSensorEntityDescription(
                key=sensor_id,
                name=None,
                device_class=SensorDeviceClass.CO2,
                state_class=SensorStateClass.MEASUREMENT,
                native_unit_of_measurement=UnitOfRatio.PARTS_PER_MILLION,
                ccb_sensor=SENSORS[sensor_id],
            ),
        )
        # Follow the node, since its sensor id shifts when a sensor with a lower node id is removed.
        self._attr_unique_id = f"{ccb.uuid}-co2-{node_id}"
        self._attr_device_info = DeviceInfo(identifiers={co2_sensor_identifier(ccb, node_id)})
