"""Test the binary sensor platform."""

import pytest
from aiocomfoconnect.sensors import SENSOR_SEASON_COOLING_ACTIVE
from custom_components.comfoconnect import EVENT_COMFOCONNECT_ALARM
from custom_components.comfoconnect.const import DOMAIN
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNKNOWN, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_capture_events, snapshot_platform
from syrupy.assertion import SnapshotAssertion
from tests.conftest import BRIDGE_UUID, push_alarms, push_sensor

ALARMS = "binary_sensor.comfoairq_active_alarms"


@pytest.fixture
def platforms() -> list[Platform]:
    """Set up only the binary sensor platform."""
    return [Platform.BINARY_SENSOR]


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_entities(
    hass: HomeAssistant, entity_registry: er.EntityRegistry, snapshot: SnapshotAssertion, init_integration: MockConfigEntry
) -> None:
    """Test the binary sensor entities of the unit, with what the unit reports."""
    await snapshot_platform(hass, entity_registry, snapshot, init_integration.entry_id)


async def test_alarms(hass: HomeAssistant, init_integration: MockConfigEntry) -> None:
    """Test that the alarm sensor shows the alarms of every node, until each node clears its own."""
    push_alarms(init_integration, 1, {79: "Replace filters"})
    await hass.async_block_till_done()
    state = hass.states.get(ALARMS)
    assert state.state == STATE_ON
    assert state.attributes["alarms"] == [{"node_id": 1, "id": 79, "message": "Replace filters"}]

    # Another node without alarms doesn't clear the alarm of node 1.
    push_alarms(init_integration, 2, {})
    await hass.async_block_till_done()
    assert hass.states.get(ALARMS).state == STATE_ON

    push_alarms(init_integration, 2, {21: "Sensor error"})
    await hass.async_block_till_done()
    state = hass.states.get(ALARMS)
    assert state.attributes["alarm_count"] == 2
    assert state.attributes["alarms"] == [
        {"node_id": 1, "id": 79, "message": "Replace filters"},
        {"node_id": 2, "id": 21, "message": "Sensor error"},
    ]

    push_alarms(init_integration, 1, {})
    await hass.async_block_till_done()
    assert hass.states.get(ALARMS).state == STATE_ON
    assert hass.states.get(ALARMS).attributes["alarms"] == [{"node_id": 2, "id": 21, "message": "Sensor error"}]

    push_alarms(init_integration, 2, {})
    await hass.async_block_till_done()
    state = hass.states.get(ALARMS)
    assert state.state == STATE_OFF
    assert state.attributes["alarm_count"] == 0


@pytest.mark.parametrize(("alarms", "expected"), [(None, STATE_UNKNOWN), ({}, STATE_OFF), ({79: "Replace filters"}, STATE_ON)])
async def test_alarms_reported_while_connecting(hass: HomeAssistant, init_integration: MockConfigEntry, expected: str) -> None:
    """Test that the alarm sensor shows the alarms reported before it was added, and is unknown until the unit reports them."""
    assert hass.states.get(ALARMS).state == expected


async def test_alarm_events(hass: HomeAssistant, device_registry: dr.DeviceRegistry, init_integration: MockConfigEntry) -> None:
    """Test that an event is fired for each node whose alarms change, and that a node without alarms at the start fires none."""
    events = async_capture_events(hass, EVENT_COMFOCONNECT_ALARM)

    push_alarms(init_integration, 1, {79: "Replace filters"})
    push_alarms(init_integration, 2, {})
    push_alarms(init_integration, 1, {79: "Replace filters"})
    push_alarms(init_integration, 2, {21: "Sensor error"})
    push_alarms(init_integration, 1, {})
    push_alarms(init_integration, 2, {})
    await hass.async_block_till_done()

    unit = device_registry.async_get_device_by_identifier((DOMAIN, BRIDGE_UUID), init_integration.entry_id)
    base = {"device_id": unit.id, "bridge_uuid": BRIDGE_UUID}
    assert [event.data for event in events] == [
        {**base, "node_id": 1, "errors": [{"id": 79, "message": "Replace filters"}]},
        {**base, "node_id": 2, "errors": [{"id": 21, "message": "Sensor error"}]},
        {**base, "node_id": 1, "errors": []},
        {**base, "node_id": 2, "errors": []},
    ]


@pytest.fixture
def events(hass: HomeAssistant) -> list:
    """Capture the alarm events, from before the integration is set up."""
    return async_capture_events(hass, EVENT_COMFOCONNECT_ALARM)


@pytest.mark.parametrize("alarms", [{79: "Replace filters"}])
async def test_alarm_event_while_connecting(hass: HomeAssistant, events: list, init_integration: MockConfigEntry) -> None:
    """Test that an alarm reported while connecting, before the unit's device exists, fires an event without a device."""
    assert [event.data for event in events] == [
        {"device_id": None, "bridge_uuid": BRIDGE_UUID, "node_id": 1, "errors": [{"id": 79, "message": "Replace filters"}]},
    ]


@pytest.mark.parametrize(("value", "expected"), [(True, STATE_ON), (False, STATE_OFF)])
@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_binary_sensor_follows_the_unit(hass: HomeAssistant, init_integration: MockConfigEntry, value: bool, expected: str) -> None:
    """Test that a binary sensor shows what the unit pushes."""
    push_sensor(init_integration, SENSOR_SEASON_COOLING_ACTIVE, value)
    await hass.async_block_till_done()

    assert hass.states.get("binary_sensor.comfoairq_cooling_season_active").state == expected


async def test_alarms_are_logged(hass: HomeAssistant, caplog: pytest.LogCaptureFixture, init_integration: MockConfigEntry) -> None:
    """Test that an alarm is logged, but not a report without alarms, which every node sends when a session starts."""
    push_alarms(init_integration, 2, {})
    push_alarms(init_integration, 1, {79: "Replace filters"})
    push_alarms(init_integration, 1, {})
    await hass.async_block_till_done()

    assert [record.getMessage() for record in caplog.records if record.name == "custom_components.comfoconnect"] == [
        "Alarm received for Node 1:\n* 79: Replace filters\n"
    ]
