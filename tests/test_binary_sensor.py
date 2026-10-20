"""Test the binary sensor platform."""

from unittest.mock import MagicMock, patch

import pytest
from aiocomfoconnect import ComfoConnect
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
from tests.nodes import LAN_C, UNIT, announcing

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
async def test_alarms_reported_while_connecting(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    mock_config_entry: MockConfigEntry,
    mock_comfoconnect: dict[str, MagicMock],
    alarms: dict[int, str] | None,
    expected: str,
) -> None:
    """Test that the alarm sensor shows the alarms reported before it was added, and is unknown until the unit reports them."""
    announce = announcing(UNIT, LAN_C)

    async def connect(bridge: ComfoConnect, uuid: str) -> None:
        await announce(bridge, uuid)
        if alarms is not None:
            bridge._alarm_callback_fn(UNIT.node_id, alarms)

    mock_comfoconnect["connect"].side_effect = connect
    mock_config_entry.add_to_hass(hass)
    with patch("custom_components.comfoconnect.PLATFORMS", [Platform.BINARY_SENSOR]):
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

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


async def test_alarm_event_while_connecting(
    hass: HomeAssistant, enable_custom_integrations: None, mock_config_entry: MockConfigEntry, mock_comfoconnect: dict[str, MagicMock]
) -> None:
    """Test that an alarm reported while connecting, before the unit's device exists, fires an event without a device."""
    announce = announcing(UNIT, LAN_C)

    async def connect(bridge: ComfoConnect, uuid: str) -> None:
        await announce(bridge, uuid)
        bridge._alarm_callback_fn(UNIT.node_id, {79: "Replace filters"})

    mock_comfoconnect["connect"].side_effect = connect
    events = async_capture_events(hass, EVENT_COMFOCONNECT_ALARM)
    mock_config_entry.add_to_hass(hass)
    with patch("custom_components.comfoconnect.PLATFORMS", [Platform.BINARY_SENSOR]):
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

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
