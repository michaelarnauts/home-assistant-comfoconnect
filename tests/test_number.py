"""Test the number platform."""

from datetime import timedelta
from unittest.mock import ANY, MagicMock

import pytest
from aiocomfoconnect.const import ConnectionState
from aiocomfoconnect.exceptions import ComfoConnectNotReachable, ComfoConnectRmiError
from aiocomfoconnect.properties import (
    PROPERTY_PROFILE_TEMPERATURE_COOL,
    PROPERTY_PROFILE_TEMPERATURE_NORMAL,
    PROPERTY_PROFILE_TEMPERATURE_WARM,
    PROPERTY_RMOT_COOLING_THRESHOLD,
    PROPERTY_RMOT_HEATING_THRESHOLD,
    Property,
    PropertyConstraints,
)
from custom_components.comfoconnect.const import DOMAIN
from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.number import ATTR_MAX, ATTR_MIN, ATTR_VALUE, SERVICE_SET_VALUE
from homeassistant.components.number import DOMAIN as NUMBER_DOMAIN
from homeassistant.const import ATTR_ENTITY_ID, STATE_UNAVAILABLE, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed, snapshot_platform
from syrupy.assertion import SnapshotAssertion
from tests.conftest import PROPERTY_CONSTRAINTS, set_connection_state

HEATING = "number.comfoairq_heating_rmot_threshold"

pytestmark = pytest.mark.usefixtures("entity_registry_enabled_by_default")


@pytest.fixture
def platforms() -> list[Platform]:
    """Set up only the number platform."""
    return [Platform.NUMBER]


def report(mock_comfoconnect: dict[str, MagicMock], constraints: PropertyConstraints | Exception) -> None:
    """Let the unit report these value and limits for the heating threshold from now on, or fail to."""

    async def get_property_constraints(bridge, prop: Property, node_id: int | None = None) -> PropertyConstraints:
        if prop == PROPERTY_RMOT_HEATING_THRESHOLD:
            if isinstance(constraints, Exception):
                raise constraints
            return constraints
        return next(known_constraints for known, known_constraints in PROPERTY_CONSTRAINTS if known == prop)

    mock_comfoconnect["get_property_constraints"].side_effect = get_property_constraints


async def poll(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    """Let the numbers poll the unit."""
    freezer.tick(timedelta(seconds=30))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_entities(
    hass: HomeAssistant, entity_registry: er.EntityRegistry, snapshot: SnapshotAssertion, init_integration: MockConfigEntry
) -> None:
    """Test the number entities of the unit, with the values and limits the unit reports."""
    await snapshot_platform(hass, entity_registry, snapshot, init_integration.entry_id)


@pytest.mark.parametrize(
    ("entity_id", "prop"),
    [
        (HEATING, PROPERTY_RMOT_HEATING_THRESHOLD),
        ("number.comfoairq_cooling_rmot_threshold", PROPERTY_RMOT_COOLING_THRESHOLD),
        ("number.comfoairq_warm_profile_temperature", PROPERTY_PROFILE_TEMPERATURE_WARM),
        ("number.comfoairq_normal_profile_temperature", PROPERTY_PROFILE_TEMPERATURE_NORMAL),
        ("number.comfoairq_cool_profile_temperature", PROPERTY_PROFILE_TEMPERATURE_COOL),
    ],
)
async def test_set_value(
    hass: HomeAssistant, mock_comfoconnect: dict[str, MagicMock], init_integration: MockConfigEntry, entity_id: str, prop: Property
) -> None:
    """Test that a value is written in degrees to its own property, and that the state shows what the unit reports after it."""
    value = hass.states.get(entity_id).attributes[ATTR_MIN]
    mock_comfoconnect["get_property_constraints"].side_effect = None
    mock_comfoconnect["get_property_constraints"].return_value = PropertyConstraints(value, value, 40.0, 1.0)

    await hass.services.async_call(NUMBER_DOMAIN, SERVICE_SET_VALUE, {ATTR_ENTITY_ID: entity_id, ATTR_VALUE: value}, blocking=True)
    await hass.async_block_till_done()

    mock_comfoconnect["set_property"].assert_awaited_once_with(ANY, prop, value)
    assert float(hass.states.get(entity_id).state) == value


async def test_set_value_failed(hass: HomeAssistant, mock_comfoconnect: dict[str, MagicMock], init_integration: MockConfigEntry) -> None:
    """Test that a value the unit refuses raises an error."""
    mock_comfoconnect["set_property"].side_effect = ComfoConnectRmiError("refused")

    with pytest.raises(HomeAssistantError) as failure:
        await hass.services.async_call(NUMBER_DOMAIN, SERVICE_SET_VALUE, {ATTR_ENTITY_ID: HEATING, ATTR_VALUE: 12}, blocking=True)

    assert failure.value.translation_domain == DOMAIN
    assert failure.value.translation_key == "set_failed"


async def test_poll(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, mock_comfoconnect: dict[str, MagicMock], init_integration: MockConfigEntry
) -> None:
    """Test that each poll reads the value and the limits again."""
    report(mock_comfoconnect, PropertyConstraints(13.0, 5.0, 20.0, 1.0))

    await poll(hass, freezer)

    state = hass.states.get(HEATING)
    assert state.state == "13.0"
    assert (state.attributes[ATTR_MIN], state.attributes[ATTR_MAX]) == (5, 20)


async def test_back_with_fresh_limits(hass: HomeAssistant, mock_comfoconnect: dict[str, MagicMock], init_integration: MockConfigEntry) -> None:
    """Test that a number is unavailable while the library reconnects, and reads its value and limits again once it has a session."""
    set_connection_state(init_integration, ConnectionState.DISCONNECTED)
    await hass.async_block_till_done()
    assert hass.states.get(HEATING).state == STATE_UNAVAILABLE

    report(mock_comfoconnect, PropertyConstraints(13.0, 5.0, 20.0, 1.0))
    set_connection_state(init_integration, ConnectionState.CONNECTED)
    await hass.async_block_till_done()

    state = hass.states.get(HEATING)
    assert state.state == "13.0"
    assert (state.attributes[ATTR_MIN], state.attributes[ATTR_MAX]) == (5, 20)


@pytest.mark.parametrize(
    "failure",
    [
        ComfoConnectNotReachable("Unit cannot be reached"),
        # Limits the unit can't mean leave no control to write with.
        PropertyConstraints(15.0, 20.0, 5.0, 1.0),
        PropertyConstraints(15.0, 0.0, 15.0, 0.0),
    ],
)
async def test_poll_failed(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    mock_comfoconnect: dict[str, MagicMock],
    init_integration: MockConfigEntry,
    failure: PropertyConstraints | Exception,
) -> None:
    """Test that a number the unit doesn't answer, or answers with invalid limits, is unavailable until the next poll that works."""
    report(mock_comfoconnect, failure)
    await poll(hass, freezer)
    assert hass.states.get(HEATING).state == STATE_UNAVAILABLE

    report(mock_comfoconnect, PropertyConstraints(13.0, 0.0, 15.0, 1.0))
    await poll(hass, freezer)
    assert hass.states.get(HEATING).state == "13.0"
