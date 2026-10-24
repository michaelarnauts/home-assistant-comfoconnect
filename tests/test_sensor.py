"""Test the sensor platform."""

from datetime import timedelta

import pytest
from aiocomfoconnect.sensors import SENSOR_COMFORTCONTROL_MODE, SENSOR_FAN_SUPPLY_SPEED, SENSOR_TEMPERATURE_EXTRACT
from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN
from homeassistant.components.button import SERVICE_PRESS
from homeassistant.components.fan import ATTR_PERCENTAGE, SERVICE_SET_PERCENTAGE
from homeassistant.components.fan import DOMAIN as FAN_DOMAIN
from homeassistant.components.number import ATTR_VALUE, SERVICE_SET_VALUE
from homeassistant.components.number import DOMAIN as NUMBER_DOMAIN
from homeassistant.components.select import ATTR_OPTION, SERVICE_SELECT_OPTION
from homeassistant.components.select import DOMAIN as SELECT_DOMAIN
from homeassistant.const import ATTR_ENTITY_ID, STATE_UNKNOWN, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed, snapshot_platform
from syrupy.assertion import SnapshotAssertion
from tests.conftest import push_sensor

SUPPLY_FAN_SPEED = "sensor.comfoairq_supply_fan_speed"
BOOST_MODE = "select.comfoairq_boost_mode"
HEATING_RMOT_THRESHOLD = "number.comfoairq_heating_rmot_threshold"


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


@pytest.mark.parametrize(
    ("platforms", "domain", "service", "data"),
    [
        ([Platform.SENSOR, Platform.FAN], FAN_DOMAIN, SERVICE_SET_PERCENTAGE, {ATTR_ENTITY_ID: "fan.comfoairq", ATTR_PERCENTAGE: 66}),
        (
            [Platform.SENSOR, Platform.SELECT],
            SELECT_DOMAIN,
            SERVICE_SELECT_OPTION,
            {ATTR_ENTITY_ID: BOOST_MODE, ATTR_OPTION: "20"},
        ),
        ([Platform.SENSOR, Platform.BUTTON], BUTTON_DOMAIN, SERVICE_PRESS, {ATTR_ENTITY_ID: "button.comfoairq_cancel_boost"}),
        (
            [Platform.SENSOR, Platform.NUMBER],
            NUMBER_DOMAIN,
            SERVICE_SET_VALUE,
            {ATTR_ENTITY_ID: HEATING_RMOT_THRESHOLD, ATTR_VALUE: 12},
        ),
    ],
)
@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_busy_sensor_writes_every_value_after_a_command(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, init_integration: MockConfigEntry, domain: str, service: str, data: dict
) -> None:
    """Test that a busy sensor writes every value for a minute after a command from Home Assistant, then is throttled again."""
    await hass.services.async_call(domain, service, data, blocking=True)

    for value in (1330, 1340):
        push_sensor(init_integration, SENSOR_FAN_SUPPLY_SPEED, value)
        await hass.async_block_till_done()
        assert hass.states.get(SUPPLY_FAN_SPEED).state == str(value)

    freezer.tick(timedelta(seconds=60))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    # The first value after the minute is written at once, the next one waits for the cooldown again.
    push_sensor(init_integration, SENSOR_FAN_SUPPLY_SPEED, 1350)
    push_sensor(init_integration, SENSOR_FAN_SUPPLY_SPEED, 1360)
    await hass.async_block_till_done()
    assert hass.states.get(SUPPLY_FAN_SPEED).state == "1350"


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
