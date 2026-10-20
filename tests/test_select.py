"""Test the select platform."""

from datetime import timedelta
from unittest.mock import ANY, MagicMock

import pytest
from aiocomfoconnect.exceptions import AioComfoConnectTimeout
from aiocomfoconnect.properties import (
    PROPERTY_SENSOR_VENTILATION_HUMIDITY_COMFORT,
    PROPERTY_SENSOR_VENTILATION_HUMIDITY_PROTECTION,
    PROPERTY_SENSOR_VENTILATION_TEMP_PASSIVE,
    PROPERTY_TEMPERATURE_PROFILE_MODE,
)
from aiocomfoconnect.sensors import (
    SENSOR_BYPASS_ACTIVATION_STATE,
    SENSOR_COMFOCOOL_STATE,
    SENSOR_OPERATING_MODE,
    SENSOR_PRESET_TIMERS,
    SENSOR_PROFILE_TEMPERATURE,
)
from custom_components.comfoconnect.const import DOMAIN
from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.select import ATTR_OPTION, SERVICE_SELECT_OPTION
from homeassistant.components.select import DOMAIN as SELECT_DOMAIN
from homeassistant.const import ATTR_ENTITY_ID, STATE_UNKNOWN, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed, snapshot_platform
from syrupy.assertion import SnapshotAssertion
from tests.conftest import push_sensor


@pytest.fixture
def platforms() -> list[Platform]:
    """Set up only the select platform."""
    return [Platform.SELECT]


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_entities(
    hass: HomeAssistant, entity_registry: er.EntityRegistry, snapshot: SnapshotAssertion, init_integration: MockConfigEntry
) -> None:
    """Test the select entities of the unit, with what the unit reports."""
    await snapshot_platform(hass, entity_registry, snapshot, init_integration.entry_id)


@pytest.mark.parametrize(
    ("entity_id", "option", "method", "args"),
    [
        ("select.comfoairq_ventilation_mode", "manual", "set_mode", ("manual",)),
        ("select.comfoairq_bypass_mode", "on", "set_bypass", ("on",)),
        ("select.comfoairq_balance_mode", "supply_only", "set_balance_mode", ("supply_only",)),
        ("select.comfoairq_temperature_profile", "warm", "set_temperature_profile", ("warm",)),
        ("select.comfoairq_comfocool_mode", "auto", "set_comfocool_mode", ("auto",)),
        ("select.comfoairq_temperature_profile_mode", "fixed", "set_property", (PROPERTY_TEMPERATURE_PROFILE_MODE, "fixed")),
        ("select.comfoairq_temperature_sensor_ventilation", "on", "set_property", (PROPERTY_SENSOR_VENTILATION_TEMP_PASSIVE, "on")),
        ("select.comfoairq_humidity_comfort_ventilation", "auto", "set_property", (PROPERTY_SENSOR_VENTILATION_HUMIDITY_COMFORT, "auto")),
        ("select.comfoairq_humidity_protection_ventilation", "off", "set_property", (PROPERTY_SENSOR_VENTILATION_HUMIDITY_PROTECTION, "off")),
        ("select.comfoairq_boost_mode", "10", "set_boost", (True, 600)),
        ("select.comfoairq_boost_mode", "off", "set_boost", (False,)),
        ("select.comfoairq_away_mode", "20160", "set_away", (True, 1209600)),
        ("select.comfoairq_away_mode", "off", "set_away", (False,)),
        ("select.comfoairq_bypass_timer", "60", "set_bypass", ("on", 3600)),
        ("select.comfoairq_bypass_timer", "off", "set_bypass", ("auto",)),
    ],
)
@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_select_option(
    hass: HomeAssistant,
    mock_comfoconnect: dict[str, MagicMock],
    init_integration: MockConfigEntry,
    entity_id: str,
    option: str,
    method: str,
    args: tuple,
) -> None:
    """Test that an option is sent to the unit, and shown at once."""
    await hass.services.async_call(SELECT_DOMAIN, SERVICE_SELECT_OPTION, {ATTR_ENTITY_ID: entity_id, ATTR_OPTION: option}, blocking=True)

    mock_comfoconnect[method].assert_awaited_once_with(ANY, *args)
    expected = option if option in ("off", "auto", "on") or not option.isdigit() else "active"
    assert hass.states.get(entity_id).state == expected


@pytest.mark.parametrize(("running", "expected"), [(False, "off"), (True, "active")])
@pytest.mark.parametrize(("entity_id", "getter"), [("select.comfoairq_boost_mode", "get_boost"), ("select.comfoairq_away_mode", "get_away")])
async def test_select_active_reads_the_timer(
    hass: HomeAssistant,
    mock_comfoconnect: dict[str, MagicMock],
    init_integration: MockConfigEntry,
    entity_id: str,
    getter: str,
    running: bool,
    expected: str,
) -> None:
    """Test that choosing active only shows whether the timer runs, without starting one."""
    mock_comfoconnect[getter].return_value = running

    await hass.services.async_call(SELECT_DOMAIN, SERVICE_SELECT_OPTION, {ATTR_ENTITY_ID: entity_id, ATTR_OPTION: "active"}, blocking=True)

    assert hass.states.get(entity_id).state == expected
    mock_comfoconnect["set_boost"].assert_not_awaited()
    mock_comfoconnect["set_away"].assert_not_awaited()


@pytest.mark.parametrize(("bypass", "expected"), [("on", "active"), ("auto", "off"), ("off", "off")])
async def test_bypass_timer_active_reads_the_bypass(
    hass: HomeAssistant, mock_comfoconnect: dict[str, MagicMock], init_integration: MockConfigEntry, bypass: str, expected: str
) -> None:
    """Test that choosing active on the bypass timer only shows whether bypass is forced on."""
    mock_comfoconnect["get_bypass"].return_value = bypass

    await hass.services.async_call(
        SELECT_DOMAIN, SERVICE_SELECT_OPTION, {ATTR_ENTITY_ID: "select.comfoairq_bypass_timer", ATTR_OPTION: "active"}, blocking=True
    )

    assert hass.states.get("select.comfoairq_bypass_timer").state == expected
    mock_comfoconnect["set_bypass"].assert_not_awaited()


async def test_select_option_failed(hass: HomeAssistant, mock_comfoconnect: dict[str, MagicMock], init_integration: MockConfigEntry) -> None:
    """Test that an option the unit doesn't take raises an error, and keeps the option the unit reported."""
    mock_comfoconnect["set_boost"].side_effect = AioComfoConnectTimeout("No answer")

    with pytest.raises(HomeAssistantError) as failure:
        await hass.services.async_call(
            SELECT_DOMAIN, SERVICE_SELECT_OPTION, {ATTR_ENTITY_ID: "select.comfoairq_boost_mode", ATTR_OPTION: "10"}, blocking=True
        )

    assert failure.value.translation_domain == DOMAIN
    assert failure.value.translation_key == "set_failed"
    assert failure.value.translation_placeholders["error"] == "No answer"
    assert hass.states.get("select.comfoairq_boost_mode").state == "off"


@pytest.mark.parametrize(
    ("value", "boost", "away"),
    [(0, "off", "off"), (64, "active", "off"), (2048, "off", "active"), (2112, "active", "active")],
)
async def test_boost_and_away_follow_the_pushed_timers(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    mock_comfoconnect: dict[str, MagicMock],
    init_integration: MockConfigEntry,
    value: int,
    boost: str,
    away: str,
) -> None:
    """Test that boost and away follow bit 6 and bit 11 of the running preset timers, and are only read at setup."""
    mock_comfoconnect["get_boost"].reset_mock()
    mock_comfoconnect["get_away"].reset_mock()

    push_sensor(init_integration, SENSOR_PRESET_TIMERS, value)
    freezer.tick(timedelta(minutes=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert hass.states.get("select.comfoairq_boost_mode").state == boost
    assert hass.states.get("select.comfoairq_away_mode").state == away
    mock_comfoconnect["get_boost"].assert_not_awaited()
    mock_comfoconnect["get_away"].assert_not_awaited()


@pytest.mark.parametrize(
    ("entity_id", "sensor_id", "value", "expected"),
    [
        ("select.comfoairq_ventilation_mode", SENSOR_OPERATING_MODE, 255, "auto"),
        ("select.comfoairq_ventilation_mode", SENSOR_OPERATING_MODE, 1, "manual"),
        ("select.comfoairq_bypass_mode", SENSOR_BYPASS_ACTIVATION_STATE, 1, "on"),
        ("select.comfoairq_bypass_mode", SENSOR_BYPASS_ACTIVATION_STATE, 2, "off"),
        ("select.comfoairq_bypass_timer", SENSOR_BYPASS_ACTIVATION_STATE, 1, "active"),
        ("select.comfoairq_bypass_timer", SENSOR_BYPASS_ACTIVATION_STATE, 2, "off"),
        ("select.comfoairq_temperature_profile", SENSOR_PROFILE_TEMPERATURE, 1, "cool"),
        ("select.comfoairq_temperature_profile", SENSOR_PROFILE_TEMPERATURE, 2, "warm"),
        ("select.comfoairq_comfocool_mode", SENSOR_COMFOCOOL_STATE, 1, "auto"),
    ],
)
async def test_select_follows_the_pushed_sensor(
    hass: HomeAssistant, init_integration: MockConfigEntry, entity_id: str, sensor_id: int, value: int, expected: str
) -> None:
    """Test that a select shows the state that the unit pushes."""
    push_sensor(init_integration, sensor_id, value)
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == expected


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_settings_are_read_every_five_minutes(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, mock_comfoconnect: dict[str, MagicMock], init_integration: MockConfigEntry
) -> None:
    """Test that a setting that hardly changes is read at most every five minutes, though selects are polled more often."""
    mock_comfoconnect["get_balance_mode"].reset_mock()

    freezer.tick(timedelta(minutes=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    mock_comfoconnect["get_balance_mode"].assert_not_awaited()

    mock_comfoconnect["get_balance_mode"].return_value = "exhaust_only"
    freezer.tick(timedelta(minutes=4))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    mock_comfoconnect["get_balance_mode"].assert_awaited_once()
    assert hass.states.get("select.comfoairq_balance_mode").state == "exhaust_only"


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_setting_read_failed(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, mock_comfoconnect: dict[str, MagicMock], init_integration: MockConfigEntry
) -> None:
    """Test that a setting the unit doesn't answer keeps the value it had."""
    mock_comfoconnect["get_balance_mode"].side_effect = AioComfoConnectTimeout("No answer")

    freezer.tick(timedelta(minutes=5))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert hass.states.get("select.comfoairq_balance_mode").state == "balance"


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_temperature_profile_mode_external_setpoint(
    hass: HomeAssistant, mock_comfoconnect: dict[str, MagicMock], init_integration: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    """Test that the external setpoint mode, which the unit doesn't offer to set, is shown as unknown."""
    mock_comfoconnect["get_property"].side_effect = ValueError("Invalid value: 2")

    freezer.tick(timedelta(minutes=5))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert hass.states.get("select.comfoairq_temperature_profile_mode").state == STATE_UNKNOWN
