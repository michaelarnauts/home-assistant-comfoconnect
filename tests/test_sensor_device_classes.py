"""Sensors have a device class where Home Assistant has one for them."""

from types import SimpleNamespace

import pytest
from aiocomfoconnect.sensors import SENSOR_COMFORTCONTROL_MODE
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


@pytest.mark.parametrize(("value", "expected"), [(2, "overruling"), (7, "unknown")])
async def test_sensor_based_ventilation_state_is_an_enum(hass: HomeAssistant, value: int, expected: str) -> None:
    """A known state shows its option; an unknown one is unknown, since an enum only accepts its options."""
    state = write_state(hass, SENSOR_COMFORTCONTROL_MODE, value)
    assert state.state == expected
    assert state.attributes["device_class"] == SensorDeviceClass.ENUM
    assert state.attributes["options"] == ["disabled", "active", "overruling"]
