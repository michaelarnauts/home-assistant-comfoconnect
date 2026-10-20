"""RMOT numbers load through integration setup and use the device's property values."""

from contextlib import ExitStack
from unittest.mock import AsyncMock, patch

import pytest
from aiocomfoconnect.comfoconnect import NodeInfo
from aiocomfoconnect.exceptions import ComfoConnectNotReachable, ComfoConnectRmiError
from aiocomfoconnect.properties import (
    PROPERTY_PROFILE_TEMPERATURE_COOL,
    PROPERTY_PROFILE_TEMPERATURE_NORMAL,
    PROPERTY_PROFILE_TEMPERATURE_WARM,
    PROPERTY_RMOT_COOLING_THRESHOLD,
    PROPERTY_RMOT_HEATING_THRESHOLD,
    PropertyConstraints,
)
from custom_components.comfoconnect import ComfoConnectBridge
from custom_components.comfoconnect.const import CONF_LOCAL_UUID, CONF_UUID, DOMAIN
from homeassistant.components.number import NumberDeviceClass
from homeassistant.const import CONF_HOST, STATE_UNAVAILABLE, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_component import async_update_entity
from pytest_homeassistant_custom_component.common import MockConfigEntry, snapshot_platform
from syrupy.assertion import SnapshotAssertion
from tests.nodes import UNIT, announcing

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")
BRIDGE = "custom_components.comfoconnect.ComfoConnectBridge"
UNIT_UUID = "00" * 16
HEATING = "number.test_unit_heating_rmot_threshold"
COOLING = "number.test_unit_cooling_rmot_threshold"


@pytest.fixture
def entry(hass: HomeAssistant) -> MockConfigEntry:
    """Create an entry with network access supplied by the protocol mocks."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Test unit",
        data={CONF_HOST: "192.0.2.10", CONF_UUID: UNIT_UUID, CONF_LOCAL_UUID: "11" * 16},
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def protocol():
    """Mock the device boundary; the integration and number platform load normally."""
    heating = PROPERTY_RMOT_HEATING_THRESHOLD
    cooling = PROPERTY_RMOT_COOLING_THRESHOLD
    profiles = (PROPERTY_PROFILE_TEMPERATURE_WARM, PROPERTY_PROFILE_TEMPERATURE_NORMAL, PROPERTY_PROFILE_TEMPERATURE_COOL)
    values = {heating.property_id: 11.0, cooling.property_id: 20.0}
    ranges = {heating.property_id: (0.0, 15.0), cooling.property_id: (15.0, 40.0)}
    # The profile temperatures and their ranges as read from a real unit.
    values |= {prop.property_id: value for prop, value in zip(profiles, (23.0, 21.0, 19.0), strict=True)}
    ranges |= {prop.property_id: limits for prop, limits in zip(profiles, ((23.0, 28.9), (18.9, 23.3), (17.8, 19.0)), strict=True)}

    async def get_property_constraints(prop):
        assert prop in (heating, cooling, *profiles)
        return PropertyConstraints(values[prop.property_id], *ranges[prop.property_id], 1.0)

    async def set_property(prop, value):
        values[prop.property_id] = value

    with ExitStack() as stack:
        stack.enter_context(patch(f"{BRIDGE}.connect", autospec=True, side_effect=announcing(UNIT)))
        stack.enter_context(patch(f"{BRIDGE}.disconnect", new_callable=AsyncMock))
        stack.enter_context(patch(f"{BRIDGE}.set_property", new_callable=AsyncMock, side_effect=set_property))
        stack.enter_context(
            patch(f"{BRIDGE}.get_node_info", new_callable=AsyncMock, return_value=NodeInfo("Test unit", None, None, None, None, None, None))
        )
        stack.enter_context(patch(f"{BRIDGE}.get_property_constraints", new_callable=AsyncMock, side_effect=get_property_constraints))
        # Other platforms are unrelated; do not mock async_forward_entry_setups or the number platform.
        for platform in ("fan", "sensor", "binary_sensor", "select", "button"):
            stack.enter_context(patch(f"custom_components.comfoconnect.{platform}.async_setup_entry", new_callable=AsyncMock))
        yield values, ranges


def enable_numbers(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Opt into both configuration entities before setup, as a user can do in the UI."""
    registry = er.async_get(hass)
    for key in ("rmot_heating", "rmot_cooling"):
        name = "heating_rmot_threshold" if key == "rmot_heating" else "cooling_rmot_threshold"
        registry.async_get_or_create(
            "number", DOMAIN, f"{UNIT_UUID}-{key}", config_entry=entry, disabled_by=None, suggested_object_id=f"test_unit_{name}"
        )


@pytest.fixture
def platforms() -> list[Platform]:
    """Set up only the number platform."""
    return [Platform.NUMBER]


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_entities(
    hass: HomeAssistant, entity_registry: er.EntityRegistry, snapshot: SnapshotAssertion, init_integration: MockConfigEntry
) -> None:
    """Test the number entities of the unit, with the values and limits the unit reports."""
    await snapshot_platform(hass, entity_registry, snapshot, init_integration.entry_id)


@pytest.mark.parametrize("entity_id,prop,value", [(HEATING, PROPERTY_RMOT_HEATING_THRESHOLD, 12), (COOLING, PROPERTY_RMOT_COOLING_THRESHOLD, 21)])
async def test_write_uses_degrees_and_reads_back_the_device(hass: HomeAssistant, entry: MockConfigEntry, protocol, entity_id, prop, value) -> None:
    """A write uses the library property, and the state shows what the unit reports right after."""
    enable_numbers(hass, entry)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    bridge = entry.runtime_data

    await hass.services.async_call("number", "set_value", {"entity_id": entity_id, "value": value}, blocking=True)
    await hass.async_block_till_done()
    bridge.set_property.assert_awaited_once_with(prop, value)
    assert float(hass.states.get(entity_id).state) == value


async def test_failed_write_raises_a_home_assistant_error(hass: HomeAssistant, entry: MockConfigEntry, protocol) -> None:
    """A write the unit refuses is reported to the user instead of failing with a library exception."""
    enable_numbers(hass, entry)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    bridge = entry.runtime_data
    bridge.set_property.side_effect = ComfoConnectRmiError("refused")

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call("number", "set_value", {"entity_id": HEATING, "value": 12}, blocking=True)


async def test_a_poll_reads_the_value_and_limits_in_one_request(hass: HomeAssistant, entry: MockConfigEntry, protocol) -> None:
    """Every poll refreshes the value and the limits with a single request."""
    enable_numbers(hass, entry)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    bridge = entry.runtime_data
    reads = bridge.get_property_constraints.await_count

    protocol[0][PROPERTY_RMOT_HEATING_THRESHOLD.property_id] = 13.0
    protocol[1][PROPERTY_RMOT_HEATING_THRESHOLD.property_id] = (5.0, 20.0)
    await async_update_entity(hass, HEATING)
    assert bridge.get_property_constraints.await_count == reads + 1
    state = hass.states.get(HEATING)
    assert state.state == "13.0"
    assert (state.attributes["min"], state.attributes["max"]) == (5, 20)


async def test_unavailable_number_recovers_with_fresh_limits(hass: HomeAssistant, entry: MockConfigEntry, protocol) -> None:
    """Dispatcher recovery polls values and constraints rather than exposing stale controls."""
    enable_numbers(hass, entry)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    bridge: ComfoConnectBridge = entry.runtime_data
    bridge.set_available(False)
    await hass.async_block_till_done()
    assert hass.states.get(HEATING).state == STATE_UNAVAILABLE

    protocol[1][PROPERTY_RMOT_HEATING_THRESHOLD.property_id] = (5.0, 20.0)
    protocol[0][PROPERTY_RMOT_HEATING_THRESHOLD.property_id] = 13.0
    bridge.set_available(True)
    await hass.async_block_till_done()
    state = hass.states.get(HEATING)
    assert state.state == "13.0"
    assert (state.attributes["min"], state.attributes["max"]) == (5, 20)


async def test_invalid_limits_disable_the_control(hass: HomeAssistant, entry: MockConfigEntry, protocol) -> None:
    """A failed metadata read must not leave a writable control with guessed limits."""
    enable_numbers(hass, entry)
    protocol[1][PROPERTY_RMOT_HEATING_THRESHOLD.property_id] = (20.0, 5.0)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(HEATING).state == STATE_UNAVAILABLE


async def test_gateway_failure_keeps_numbers_registered_for_recovery(hass: HomeAssistant, entry: MockConfigEntry, protocol) -> None:
    """A reachable gateway's NOT_REACHABLE reply must leave a retryable unavailable entity."""
    enable_numbers(hass, entry)
    with patch(f"{BRIDGE}.get_property_constraints", new_callable=AsyncMock, side_effect=ComfoConnectNotReachable("Unit cannot be reached")):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    state = hass.states.get(HEATING)
    assert state is not None
    assert state.state == STATE_UNAVAILABLE

    await async_update_entity(hass, HEATING)
    assert hass.states.get(HEATING).state == "11.0"

    bridge = entry.runtime_data
    normal_reads = bridge.get_property_constraints.side_effect
    bridge.get_property_constraints.side_effect = ComfoConnectNotReachable("Unit cannot be reached")
    await async_update_entity(hass, HEATING)
    assert hass.states.get(HEATING).state == STATE_UNAVAILABLE

    bridge.get_property_constraints.side_effect = normal_reads
    protocol[0][PROPERTY_RMOT_HEATING_THRESHOLD.property_id] = 13.0
    await async_update_entity(hass, HEATING)
    assert hass.states.get(HEATING).state == "13.0"


PROFILE_TEMPERATURES = {
    "profile_temperature_warm": ("number.test_unit_warm_profile_temperature", PROPERTY_PROFILE_TEMPERATURE_WARM, "23.0", 23.0, 28.9),
    "profile_temperature_normal": ("number.test_unit_normal_profile_temperature", PROPERTY_PROFILE_TEMPERATURE_NORMAL, "21.0", 18.9, 23.3),
    "profile_temperature_cool": ("number.test_unit_cool_profile_temperature", PROPERTY_PROFILE_TEMPERATURE_COOL, "19.0", 17.8, 19.0),
}


def enable_profile_temperatures(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Opt into the profile temperature entities before setup."""
    registry = er.async_get(hass)
    for key, (entity_id, *_) in PROFILE_TEMPERATURES.items():
        registry.async_get_or_create(
            "number", DOMAIN, f"{UNIT_UUID}-{key}", config_entry=entry, disabled_by=None, suggested_object_id=entity_id.removeprefix("number.")
        )


async def test_profile_temperatures_load_with_device_limits(hass: HomeAssistant, entry: MockConfigEntry, protocol) -> None:
    """The warm, normal and cool temperatures use the ranges the unit reports."""
    enable_profile_temperatures(hass, entry)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    for entity_id, _, value, minimum, maximum in PROFILE_TEMPERATURES.values():
        state = hass.states.get(entity_id)
        assert state.state == value
        assert state.attributes["device_class"] == NumberDeviceClass.TEMPERATURE
        assert (state.attributes["min"], state.attributes["max"], state.attributes["step"]) == (minimum, maximum, 1)


async def test_profile_temperatures_are_disabled_configuration_entities(hass: HomeAssistant, entry: MockConfigEntry, protocol) -> None:
    """Like the RMOT thresholds, the profile temperatures are opt-in."""
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    for key in PROFILE_TEMPERATURES:
        entity = registry.async_get(registry.async_get_entity_id("number", DOMAIN, f"{UNIT_UUID}-{key}"))
        assert entity.disabled_by == er.RegistryEntryDisabler.INTEGRATION
        assert entity.entity_category == EntityCategory.CONFIG


async def test_write_a_profile_temperature(hass: HomeAssistant, entry: MockConfigEntry, protocol) -> None:
    """A profile temperature is written in degrees to its own property."""
    enable_profile_temperatures(hass, entry)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    bridge = entry.runtime_data
    entity_id, prop, *_ = PROFILE_TEMPERATURES["profile_temperature_normal"]

    await hass.services.async_call("number", "set_value", {"entity_id": entity_id, "value": 22}, blocking=True)
    await hass.async_block_till_done()

    bridge.set_property.assert_awaited_once_with(prop, 22)
    assert hass.states.get(entity_id).state == "22.0"
