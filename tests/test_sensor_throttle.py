"""Busy sensors are written at most once per cooldown, but always end with their latest value."""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiocomfoconnect.sensors import SENSOR_FAN_SUPPLY_SPEED, SENSOR_TEMPERATURE_EXTRACT
from custom_components.comfoconnect.sensor import SENSOR_TYPES, ComfoConnectSensor
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

async_fire_time_changed = pytest.importorskip("pytest_homeassistant_custom_component.common").async_fire_time_changed


async def add_sensor(hass: HomeAssistant, key: int) -> ComfoConnectSensor:
    """Add a sensor as the platform would and return it."""
    description = next(item for item in SENSOR_TYPES if item.key == key)
    entity = ComfoConnectSensor(SimpleNamespace(uuid="test", is_available=True, register_sensor=AsyncMock()), SimpleNamespace(), description)
    entity.hass = hass
    entity.entity_id = f"sensor.test_{key}"
    await entity.async_added_to_hass()
    return entity


async def test_throttled_sensor_ends_with_its_latest_value(hass: HomeAssistant, freezer) -> None:
    """The first value is written at once, the ones in the cooldown wait, and the last of them is written after it."""
    entity = await add_sensor(hass, SENSOR_FAN_SUPPLY_SPEED)
    assert entity.entity_description.throttle

    entity._handle_update(1000)
    assert hass.states.get(entity.entity_id).state == "1000"

    entity._handle_update(1010)
    entity._handle_update(1020)
    assert hass.states.get(entity.entity_id).state == "1000"

    freezer.tick(timedelta(seconds=10))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    assert hass.states.get(entity.entity_id).state == "1020"

    await entity.async_remove()


async def test_other_sensors_write_every_update(hass: HomeAssistant) -> None:
    """A sensor that isn't throttled writes each value at once."""
    entity = await add_sensor(hass, SENSOR_TEMPERATURE_EXTRACT)
    assert not entity.entity_description.throttle

    for value in (21.0, 21.1, 21.2):
        entity._handle_update(value)
        assert hass.states.get(entity.entity_id).state == str(value)
