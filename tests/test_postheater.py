"""Postheater option-box values are exposed with the right units and stay opt-in."""

import asyncio
from types import SimpleNamespace

import pytest
from aiocomfoconnect.sensors import (
    SENSOR_POSTHEATER_PRESENT,
    SENSOR_POSTHEATER_STATE,
    SENSOR_POSTHEATER_TEMPERATURE_BEFORE,
)
from custom_components.comfoconnect.binary_sensor import SENSOR_TYPES as BINARY_SENSOR_TYPES
from custom_components.comfoconnect.binary_sensor import ComfoConnectBinarySensor
from custom_components.comfoconnect.sensor import SENSOR_TYPES, ComfoConnectSensor
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_setup as setup_loader


@pytest.mark.parametrize(
    "key,value,state,unit",
    [
        (SENSOR_POSTHEATER_STATE, 25, "25", "%"),
        (SENSOR_POSTHEATER_TEMPERATURE_BEFORE, 21.7, "21.7", "°C"),
    ],
)
def test_postheater_sensors_report_value_and_unit(tmp_path, key, value, state, unit):
    """The library already decodes the raw PDO value, so HA must not rescale it."""

    async def scenario():
        hass = HomeAssistant(str(tmp_path))
        setup_loader(hass)
        bridge = SimpleNamespace(uuid="test", is_available=True)
        description = next(item for item in SENSOR_TYPES if item.key == key)
        entity = ComfoConnectSensor(bridge, SimpleNamespace(), description)
        entity.hass = hass
        entity.entity_id = f"sensor.postheater_{key}"
        entity._handle_update(value)
        current = hass.states.get(entity.entity_id)
        assert current.state == state
        assert current.attributes["unit_of_measurement"] == unit
        assert not entity.entity_registry_enabled_default

    asyncio.run(scenario())


def test_postheater_present_is_a_disabled_by_default_binary_sensor(tmp_path):
    """Units without the option box must not get a visible entity."""

    async def scenario():
        hass = HomeAssistant(str(tmp_path))
        setup_loader(hass)
        bridge = SimpleNamespace(uuid="test", is_available=True)
        description = next(item for item in BINARY_SENSOR_TYPES if item.key == SENSOR_POSTHEATER_PRESENT)
        entity = ComfoConnectBinarySensor(bridge, SimpleNamespace(), description)
        entity.hass = hass
        entity.entity_id = "binary_sensor.postheater_present"
        entity._handle_update(True)
        assert hass.states.get(entity.entity_id).state == "on"
        assert not entity.entity_registry_enabled_default

    asyncio.run(scenario())
