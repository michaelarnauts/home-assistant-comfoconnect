"""Test the sensor platform."""

import asyncio
from datetime import timedelta
from unittest.mock import ANY, MagicMock, patch

import pytest
from aiocomfoconnect.comfoconnect import TimerEntry
from aiocomfoconnect.const import SCHEDULE_PRESET
from aiocomfoconnect.exceptions import AioComfoConnectTimeout
from aiocomfoconnect.sensors import (
    SENSOR_COMFORTCONTROL_MODE,
    SENSOR_FAN_SUPPLY_FLOW,
    SENSOR_FAN_SUPPLY_SPEED,
    SENSOR_OPERATING_MODE_2,
    SENSOR_TEMPERATURE_EXTRACT,
    SENSOR_UNIT_AIRFLOW,
)
from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import STATE_UNKNOWN, Platform, UnitOfVolumeFlowRate
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed, snapshot_platform
from syrupy.assertion import SnapshotAssertion
from tests.conftest import push_sensor

SUPPLY_FAN_SPEED = "sensor.comfoairq_supply_fan_speed"
SUPPLY_AIRFLOW = "sensor.comfoairq_supply_airflow"
EXHAUST_AIRFLOW = "sensor.comfoairq_exhaust_airflow"
ACTIVE_PRESET = "sensor.comfoairq_active_preset"
ACTIVE_PRESET_END = "sensor.comfoairq_active_preset_end"


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


@pytest.mark.parametrize(
    ("value", "expected"),
    [(255, "auto"), (1, "temporary_override"), (5, "manual"), (6, "boost"), (8, "boost_switch"), (11, "away"), (2, STATE_UNKNOWN)],
)
async def test_active_preset(hass: HomeAssistant, init_integration: MockConfigEntry, value: int, expected: str) -> None:
    """Test that the active preset shows the timer the unit reports, and a timer we don't name as unknown."""
    push_sensor(init_integration, SENSOR_OPERATING_MODE_2, value)
    await hass.async_block_till_done()

    assert hass.states.get(ACTIVE_PRESET).state == expected


@pytest.mark.parametrize(("preset", "remaining"), [(1, 27941), (6, 1180), (11, 586)])
async def test_active_preset_end(
    hass: HomeAssistant, mock_comfoconnect: dict[str, MagicMock], init_integration: MockConfigEntry, preset: int, remaining: int
) -> None:
    """Test that the end of a preset is read from its timer once, when the unit pushes the preset."""
    mock_comfoconnect["get_timer"].return_value = TimerEntry(True, 0, remaining + 20, remaining, 3)

    push_sensor(init_integration, SENSOR_OPERATING_MODE_2, preset)
    await hass.async_block_till_done()

    mock_comfoconnect["get_timer"].assert_called_once_with(ANY, SCHEDULE_PRESET, preset)
    end = dt_util.utcnow().replace(microsecond=0) + timedelta(seconds=remaining)
    assert hass.states.get(ACTIVE_PRESET_END).state == end.isoformat()


@pytest.mark.parametrize(
    ("preset", "timer"),
    [
        # Manual mode runs until it is cancelled.
        (5, TimerEntry(True, 0, -1, -1, 1)),
        # The timer ended before it was read.
        (6, TimerEntry(False, 0, 1200, 0, 3)),
    ],
)
async def test_active_preset_without_end(
    hass: HomeAssistant, mock_comfoconnect: dict[str, MagicMock], init_integration: MockConfigEntry, preset: int, timer: TimerEntry
) -> None:
    """Test that a preset whose timer has no end shows no end."""
    mock_comfoconnect["get_timer"].return_value = TimerEntry(True, 0, 1200, 1180, 3)
    push_sensor(init_integration, SENSOR_OPERATING_MODE_2, 6)
    await hass.async_block_till_done()
    assert hass.states.get(ACTIVE_PRESET_END).state != STATE_UNKNOWN

    mock_comfoconnect["get_timer"].return_value = timer
    push_sensor(init_integration, SENSOR_OPERATING_MODE_2, preset)
    await hass.async_block_till_done()

    assert hass.states.get(ACTIVE_PRESET_END).state == STATE_UNKNOWN


async def test_auto_has_no_end(hass: HomeAssistant, mock_comfoconnect: dict[str, MagicMock], init_integration: MockConfigEntry) -> None:
    """Test that auto mode shows no end, without reading a timer."""
    mock_comfoconnect["get_timer"].return_value = TimerEntry(True, 0, 1200, 1180, 3)
    push_sensor(init_integration, SENSOR_OPERATING_MODE_2, 6)
    await hass.async_block_till_done()
    mock_comfoconnect["get_timer"].reset_mock()

    push_sensor(init_integration, SENSOR_OPERATING_MODE_2, 255)
    await hass.async_block_till_done()

    mock_comfoconnect["get_timer"].assert_not_called()
    assert hass.states.get(ACTIVE_PRESET_END).state == STATE_UNKNOWN


async def test_active_preset_end_read_failed(
    hass: HomeAssistant, mock_comfoconnect: dict[str, MagicMock], init_integration: MockConfigEntry, caplog: pytest.LogCaptureFixture
) -> None:
    """Test that the end is unknown when its timer can't be read."""
    mock_comfoconnect["get_timer"].side_effect = AioComfoConnectTimeout

    push_sensor(init_integration, SENSOR_OPERATING_MODE_2, 6)
    await hass.async_block_till_done()

    assert hass.states.get(ACTIVE_PRESET_END).state == STATE_UNKNOWN
    assert "Could not read the end of the active preset" in caplog.text


async def test_active_preset_end_of_latest_preset(
    hass: HomeAssistant, mock_comfoconnect: dict[str, MagicMock], init_integration: MockConfigEntry
) -> None:
    """Test that the end of a preset that was replaced while its timer was read is not shown."""
    release = asyncio.Event()

    async def get_timer(self, subunit: int, timer: int) -> TimerEntry:
        # The boost timer answers only after the away timer.
        if timer == 6:
            await release.wait()
            return TimerEntry(True, 0, 1200, 1180, 3)
        return TimerEntry(True, 0, 600, 586, 0)

    mock_comfoconnect["get_timer"].side_effect = get_timer
    push_sensor(init_integration, SENSOR_OPERATING_MODE_2, 6)
    push_sensor(init_integration, SENSOR_OPERATING_MODE_2, 11)
    await hass.async_block_till_done(wait_background_tasks=False)
    away_end = (dt_util.utcnow().replace(microsecond=0) + timedelta(seconds=586)).isoformat()
    assert hass.states.get(ACTIVE_PRESET_END).state == away_end

    release.set()
    await hass.async_block_till_done(wait_background_tasks=True)

    assert hass.states.get(ACTIVE_PRESET_END).state == away_end
