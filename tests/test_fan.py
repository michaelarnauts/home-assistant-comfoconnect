"""Test the fan platform."""

from unittest.mock import ANY, MagicMock

import pytest
import voluptuous as vol
from aiocomfoconnect.exceptions import AioComfoConnectTimeout
from aiocomfoconnect.sensors import SENSOR_FAN_SPEED_MODE, SENSOR_OPERATING_MODE
from custom_components.comfoconnect.const import ATTR_DURATION, DOMAIN, SERVICE_START_BOOST
from homeassistant.components.fan import ATTR_PERCENTAGE, ATTR_PRESET_MODE, SERVICE_SET_PERCENTAGE, SERVICE_SET_PRESET_MODE
from homeassistant.components.fan import DOMAIN as FAN_DOMAIN
from homeassistant.const import ATTR_ENTITY_ID, SERVICE_TURN_OFF, SERVICE_TURN_ON, STATE_OFF, STATE_ON, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry, snapshot_platform
from syrupy.assertion import SnapshotAssertion
from tests.conftest import push_sensor

FAN = "fan.comfoairq"


@pytest.fixture
def platforms() -> list[Platform]:
    """Set up only the fan platform."""
    return [Platform.FAN]


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_entities(
    hass: HomeAssistant, entity_registry: er.EntityRegistry, snapshot: SnapshotAssertion, init_integration: MockConfigEntry
) -> None:
    """Test the fan entities of the unit, with what the unit reports."""
    await snapshot_platform(hass, entity_registry, snapshot, init_integration.entry_id)


@pytest.mark.parametrize(
    ("service", "data", "speed"),
    [
        (SERVICE_TURN_ON, {}, "low"),
        (SERVICE_TURN_ON, {ATTR_PERCENTAGE: 100}, "high"),
        (SERVICE_TURN_OFF, {}, "away"),
        (SERVICE_SET_PERCENTAGE, {ATTR_PERCENTAGE: 0}, "away"),
        (SERVICE_SET_PERCENTAGE, {ATTR_PERCENTAGE: 33}, "low"),
        (SERVICE_SET_PERCENTAGE, {ATTR_PERCENTAGE: 66}, "medium"),
        (SERVICE_SET_PERCENTAGE, {ATTR_PERCENTAGE: 100}, "high"),
    ],
)
async def test_set_speed(
    hass: HomeAssistant, mock_comfoconnect: dict[str, MagicMock], init_integration: MockConfigEntry, service: str, data: dict, speed: str
) -> None:
    """Test that turning the fan on or off, or setting a percentage, sets the speed of the unit; off is away."""
    await hass.services.async_call(FAN_DOMAIN, service, {ATTR_ENTITY_ID: FAN, **data}, blocking=True)

    mock_comfoconnect["set_speed"].assert_awaited_once_with(ANY, speed)


@pytest.mark.parametrize("service", [SERVICE_TURN_ON, SERVICE_SET_PRESET_MODE])
async def test_set_preset_mode(hass: HomeAssistant, mock_comfoconnect: dict[str, MagicMock], init_integration: MockConfigEntry, service: str) -> None:
    """Test that a preset mode sets the mode of the unit, also when turning on, without changing the speed."""
    await hass.services.async_call(FAN_DOMAIN, service, {ATTR_ENTITY_ID: FAN, ATTR_PRESET_MODE: "manual"}, blocking=True)

    mock_comfoconnect["set_mode"].assert_awaited_once_with(ANY, "manual")
    mock_comfoconnect["set_speed"].assert_not_awaited()


@pytest.mark.parametrize(
    ("service", "data", "method", "translation_key"),
    [
        (SERVICE_SET_PERCENTAGE, {ATTR_PERCENTAGE: 100}, "set_speed", "set_speed_failed"),
        (SERVICE_SET_PRESET_MODE, {ATTR_PRESET_MODE: "manual"}, "set_mode", "set_preset_mode_failed"),
    ],
)
async def test_set_failed(
    hass: HomeAssistant,
    mock_comfoconnect: dict[str, MagicMock],
    init_integration: MockConfigEntry,
    service: str,
    data: dict,
    method: str,
    translation_key: str,
) -> None:
    """Test that a speed or mode the unit doesn't take raises an error."""
    mock_comfoconnect[method].side_effect = AioComfoConnectTimeout("No answer")

    with pytest.raises(HomeAssistantError) as failure:
        await hass.services.async_call(FAN_DOMAIN, service, {ATTR_ENTITY_ID: FAN, **data}, blocking=True)

    assert failure.value.translation_domain == DOMAIN
    assert failure.value.translation_key == translation_key
    assert failure.value.translation_placeholders["error"] == "No answer"


@pytest.mark.parametrize(("value", "state", "percentage"), [(0, STATE_OFF, 0), (1, STATE_ON, 33), (2, STATE_ON, 66), (3, STATE_ON, 100)])
async def test_speed_follows_the_unit(hass: HomeAssistant, init_integration: MockConfigEntry, value: int, state: str, percentage: int) -> None:
    """Test that the fan shows the speed the unit pushes; away is off."""
    push_sensor(init_integration, SENSOR_FAN_SPEED_MODE, value)
    await hass.async_block_till_done()

    assert hass.states.get(FAN).state == state
    assert hass.states.get(FAN).attributes[ATTR_PERCENTAGE] == percentage


@pytest.mark.parametrize(("value", "preset_mode"), [(255, "auto"), (1, "manual")])
async def test_preset_mode_follows_the_unit(hass: HomeAssistant, init_integration: MockConfigEntry, value: int, preset_mode: str) -> None:
    """Test that the fan shows auto mode when the unit pushes an operating mode of all ones."""
    push_sensor(init_integration, SENSOR_OPERATING_MODE, value)
    await hass.async_block_till_done()

    assert hass.states.get(FAN).attributes[ATTR_PRESET_MODE] == preset_mode


@pytest.mark.parametrize(
    ("duration", "seconds"),
    [
        ({"hours": 2, "minutes": 30}, 9000),
        ("00:01:30", 90),
        ({"hours": 24}, 86400),
    ],
)
async def test_start_boost(
    hass: HomeAssistant, mock_comfoconnect: dict[str, MagicMock], init_integration: MockConfigEntry, duration, seconds: int
) -> None:
    """Test that the start_boost action passes the duration on to the unit in seconds."""
    await hass.services.async_call(DOMAIN, SERVICE_START_BOOST, {ATTR_ENTITY_ID: FAN, ATTR_DURATION: duration}, blocking=True)

    mock_comfoconnect["set_boost"].assert_awaited_once_with(ANY, True, seconds)


@pytest.mark.parametrize("duration", ["00:00:00", {"days": 30000}])
async def test_start_boost_invalid_duration(
    hass: HomeAssistant, mock_comfoconnect: dict[str, MagicMock], init_integration: MockConfigEntry, duration
) -> None:
    """Test that a zero duration, or one that doesn't fit the unit's 32-bit timer, is rejected."""
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(DOMAIN, SERVICE_START_BOOST, {ATTR_ENTITY_ID: FAN, ATTR_DURATION: duration}, blocking=True)

    mock_comfoconnect["set_boost"].assert_not_awaited()


async def test_start_boost_failed(hass: HomeAssistant, mock_comfoconnect: dict[str, MagicMock], init_integration: MockConfigEntry) -> None:
    """Test that a boost the unit doesn't answer raises an error with the translated message."""
    mock_comfoconnect["set_boost"].side_effect = AioComfoConnectTimeout("No answer")

    with pytest.raises(HomeAssistantError) as failure:
        await hass.services.async_call(DOMAIN, SERVICE_START_BOOST, {ATTR_ENTITY_ID: FAN, ATTR_DURATION: "00:10:00"}, blocking=True)

    assert failure.value.translation_key == "start_boost_failed"
    assert str(failure.value) == "Failed to start boost: No answer"
