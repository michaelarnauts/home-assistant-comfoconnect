"""Test the sensor platform."""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from aiocomfoconnect import ComfoConnect
from aiocomfoconnect.bridge import Node
from aiocomfoconnect.comfoconnect import NodeInfo
from aiocomfoconnect.const import ProductId
from aiocomfoconnect.sensors import SENSOR_COMFORTCONTROL_MODE, SENSOR_FAN_SUPPLY_SPEED, SENSOR_TEMPERATURE_EXTRACT
from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed, snapshot_platform
from syrupy.assertion import SnapshotAssertion
from tests.conftest import NODE_INFO, push_sensor
from tests.nodes import LAN_C, UNIT

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


async def test_co2_sensor_follows_its_node(
    hass: HomeAssistant, enable_custom_integrations: None, mock_config_entry: MockConfigEntry, mock_comfoconnect: dict[str, MagicMock]
) -> None:
    """Test that a CO2 sensor is unavailable while its node is off the bus, and available again once it's back."""
    co2_sensor = Node(7, ProductId.CO2SENSOR, 1, 0)

    async def connect(bridge: ComfoConnect, uuid: str) -> None:
        for node in (UNIT, LAN_C, co2_sensor):
            announce(bridge, node)

    async def get_node_info(bridge: ComfoConnect, node_id: int | None = None) -> NodeInfo:
        if node_id == co2_sensor.node_id:
            return NodeInfo("Living", None, None, "DEMO0007", "1.2.3", 1, 0)
        return NODE_INFO[node_id]

    mock_comfoconnect["connect"].side_effect = connect
    mock_comfoconnect["get_node_info"].side_effect = get_node_info
    mock_config_entry.add_to_hass(hass)
    with patch("custom_components.comfoconnect.PLATFORMS", [Platform.SENSOR]):
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()
    assert hass.states.get("sensor.living").state == "650"

    announce(mock_config_entry.runtime_data, Node(7, ProductId.CO2SENSOR, 1, 1))
    await hass.async_block_till_done()
    assert hass.states.get("sensor.living").state == STATE_UNAVAILABLE

    announce(mock_config_entry.runtime_data, co2_sensor)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.living").state == "650"


def announce(bridge: ComfoConnect, node: Node) -> None:
    """Announce a node on the bus, or that it went offline, like the bridge does."""
    bridge._process_node_notification(SimpleNamespace(nodeId=node.node_id, productId=node.product_id, zoneId=node.zone_id, mode=node.mode))
