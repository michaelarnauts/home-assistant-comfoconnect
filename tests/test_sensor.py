"""Test the sensor platform."""

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from aiocomfoconnect.sensors import (
    SENSOR_COMFORTCONTROL_MODE,
    SENSOR_FAN_SUPPLY_FLOW,
    SENSOR_FAN_SUPPLY_SPEED,
    SENSOR_TEMPERATURE_EXTRACT,
    SENSOR_UNIT_AIRFLOW,
)
from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import STATE_UNKNOWN, Platform, UnitOfVolumeFlowRate
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed, snapshot_platform
from syrupy.assertion import SnapshotAssertion
from tests.conftest import push_sensor

SUPPLY_FAN_SPEED = "sensor.comfoairq_supply_fan_speed"
SUPPLY_AIRFLOW = "sensor.comfoairq_supply_airflow"
EXHAUST_AIRFLOW = "sensor.comfoairq_exhaust_airflow"


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


async def setup_with_airflow_unit(hass: HomeAssistant, entry: MockConfigEntry, mock_comfoconnect: dict[str, MagicMock], airflow_unit) -> None:
    """Set up the sensors with a unit that reports this airflow unit when it's registered, or none for None."""
    register_sensor = mock_comfoconnect["register_sensor"].side_effect

    async def register_sensor_with_airflow_unit(bridge, sensor):
        if sensor.id != SENSOR_UNIT_AIRFLOW:
            await register_sensor(bridge, sensor)
        elif airflow_unit is not None:
            bridge._sensor_callback_fn(sensor, airflow_unit)

    mock_comfoconnect["register_sensor"].side_effect = register_sensor_with_airflow_unit
    entry.add_to_hass(hass)
    with patch("custom_components.comfoconnect.PLATFORMS", [Platform.SENSOR]):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()


@pytest.mark.parametrize(
    ("airflow_unit", "expected"),
    [
        ("lps", UnitOfVolumeFlowRate.LITERS_PER_SECOND),
        ("m3ph", UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR),
        # Home Assistant has no unit for kg/h.
        ("kgph", UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR),
    ],
)
@pytest.mark.usefixtures("entity_registry_enabled_by_default", "enable_custom_integrations")
async def test_airflow_unit(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    mock_config_entry: MockConfigEntry,
    mock_comfoconnect: dict[str, MagicMock],
    airflow_unit: str,
    expected: str,
) -> None:
    """Test that the airflow sensors show the airflow in the airflow unit the unit reports, without converting it."""
    await setup_with_airflow_unit(hass, mock_config_entry, mock_comfoconnect, airflow_unit)
    for entity_id, value in ((SUPPLY_AIRFLOW, "108"), (EXHAUST_AIRFLOW, "109")):
        state = hass.states.get(entity_id)
        assert (state.state, state.attributes["unit_of_measurement"]) == (value, expected)

    # Later airflows are shown too, after the throttle's cooldown.
    push_sensor(mock_config_entry, SENSOR_FAN_SUPPLY_FLOW, 30)
    freezer.tick(timedelta(seconds=10))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    state = hass.states.get(SUPPLY_AIRFLOW)
    assert (state.state, state.attributes["unit_of_measurement"]) == ("30", expected)


@pytest.mark.parametrize("airflow", [108, 0])
@pytest.mark.usefixtures("entity_registry_enabled_by_default", "enable_custom_integrations")
async def test_airflow_waits_for_its_unit(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_comfoconnect: dict[str, MagicMock], airflow: int
) -> None:
    """Test that an airflow is only shown once its unit is known, so it's never shown in the wrong unit, also a 0."""
    await setup_with_airflow_unit(hass, mock_config_entry, mock_comfoconnect, None)
    push_sensor(mock_config_entry, SENSOR_FAN_SUPPLY_FLOW, airflow)
    await hass.async_block_till_done()
    assert hass.states.get(SUPPLY_AIRFLOW).state == STATE_UNKNOWN

    push_sensor(mock_config_entry, SENSOR_UNIT_AIRFLOW, "lps")
    await hass.async_block_till_done()
    state = hass.states.get(SUPPLY_AIRFLOW)
    assert (state.state, state.attributes["unit_of_measurement"]) == (str(airflow), UnitOfVolumeFlowRate.LITERS_PER_SECOND)
