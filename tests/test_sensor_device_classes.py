"""Sensors have a device class where Home Assistant has one for them."""

from types import SimpleNamespace

import pytest
from aiocomfoconnect.sensors import SENSOR_COMFORTCONTROL_MODE, SENSOR_DAYS_TO_REPLACE_FILTER, SENSOR_FAN_EXHAUST_FLOW, SENSOR_FAN_SUPPLY_FLOW
from custom_components.comfoconnect.sensor import SENSOR_TYPES, ComfoConnectSensor
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.core import HomeAssistant


def write_state(hass: HomeAssistant, key: int, value) -> str:
    """Push a value to the sensor and return the state Home Assistant accepted."""
    description = next(item for item in SENSOR_TYPES if item.key == key)
    entity = ComfoConnectSensor(SimpleNamespace(uuid="test", is_available=True), SimpleNamespace(), description)
    entity.hass = hass
    entity.entity_id = f"sensor.test_{key}"
    entity._handle_update(value)
    return hass.states.get(entity.entity_id)


@pytest.mark.parametrize(
    ("key", "value", "device_class", "unit"),
    [
        (SENSOR_FAN_SUPPLY_FLOW, 150, SensorDeviceClass.VOLUME_FLOW_RATE, "m³/h"),
        (SENSOR_FAN_EXHAUST_FLOW, 150, SensorDeviceClass.VOLUME_FLOW_RATE, "m³/h"),
        (SENSOR_DAYS_TO_REPLACE_FILTER, 90, SensorDeviceClass.DURATION, "d"),
    ],
)
async def test_measurements_have_a_device_class(hass: HomeAssistant, key: int, value: int, device_class: str, unit: str) -> None:
    """Airflows and the filter countdown keep their unit."""
    state = write_state(hass, key, value)
    assert state.state == str(value)
    assert state.attributes["device_class"] == device_class
    assert state.attributes["unit_of_measurement"] == unit


@pytest.mark.parametrize(("value", "expected"), [(2, "overruling"), (7, "unknown")])
async def test_sensor_based_ventilation_state_is_an_enum(hass: HomeAssistant, value: int, expected: str) -> None:
    """A known state shows its option; an unknown one is unknown, since an enum only accepts its options."""
    state = write_state(hass, SENSOR_COMFORTCONTROL_MODE, value)
    assert state.state == expected
    assert state.attributes["device_class"] == SensorDeviceClass.ENUM
    assert state.attributes["options"] == ["disabled", "active", "overruling"]
