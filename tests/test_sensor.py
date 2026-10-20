"""Test the sensor platform."""

from datetime import timedelta

import pytest
from aiocomfoconnect.sensors import SENSOR_COMFORTCONTROL_MODE, SENSOR_FAN_SUPPLY_SPEED, SENSOR_TEMPERATURE_EXTRACT
from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import STATE_UNKNOWN, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed, snapshot_platform
from syrupy.assertion import SnapshotAssertion
from tests.conftest import push_sensor

SUPPLY_FAN_SPEED = "sensor.comfoairq_supply_fan_speed"


@pytest.fixture
def platforms() -> list[Platform]:
    """Set up only the sensor platform."""
    return [Platform.SENSOR]


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_entities(
    hass: HomeAssistant, entity_registry: er.EntityRegistry, snapshot: SnapshotAssertion, init_integration: MockConfigEntry
) -> None:
    """Test the sensor entities of the unit, with what the unit reports."""
    await snapshot_platform(hass, entity_registry, snapshot, init_integration.entry_id)


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_busy_sensor_is_throttled(hass: HomeAssistant, freezer: FrozenDateTimeFactory, init_integration: MockConfigEntry) -> None:
    """Test that a busy sensor writes its first value at once, and the latest of the values in the cooldown after it."""
    # The value the unit pushed at setup was the first.
    assert hass.states.get(SUPPLY_FAN_SPEED).state == "1325"

    push_sensor(init_integration, SENSOR_FAN_SUPPLY_SPEED, 1330)
    push_sensor(init_integration, SENSOR_FAN_SUPPLY_SPEED, 1340)
    await hass.async_block_till_done()
    assert hass.states.get(SUPPLY_FAN_SPEED).state == "1325"

    freezer.tick(timedelta(seconds=10))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(SUPPLY_FAN_SPEED).state == "1340"


async def test_other_sensors_write_every_value(hass: HomeAssistant, init_integration: MockConfigEntry) -> None:
    """Test that a sensor that isn't throttled writes each value at once."""
    for value in (21.0, 21.1, 21.2):
        push_sensor(init_integration, SENSOR_TEMPERATURE_EXTRACT, value)
        await hass.async_block_till_done()
        assert hass.states.get("sensor.comfoairq_inside_temperature").state == str(value)


@pytest.mark.parametrize(("value", "expected"), [(0, "disabled"), (2, "overruling"), (7, STATE_UNKNOWN)])
@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_sensor_based_ventilation_state(hass: HomeAssistant, init_integration: MockConfigEntry, value: int, expected: str) -> None:
    """Test that a known state of the sensor based ventilation shows its option, and an unknown one is unknown."""
    push_sensor(init_integration, SENSOR_COMFORTCONTROL_MODE, value)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.comfoairq_sensor_based_ventilation_state").state == expected
