"""ComfoNet CO2 sensors in zone 1 get their own device, with the CO2 level of their node."""

from __future__ import annotations

import pytest
from aiocomfoconnect.bridge import Node
from aiocomfoconnect.comfoconnect import NodeInfo
from aiocomfoconnect.const import ProductId
from aiocomfoconnect.sensors import SENSOR_CO2_1, SENSOR_CO2_2
from custom_components.comfoconnect.const import DOMAIN
from homeassistant.const import STATE_UNAVAILABLE, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry
from tests.conftest import NODE_INFO, announce_node, push_sensor
from tests.nodes import LAN_C, UNIT


def co2_node(node_id: int, zone_id: int = 1, mode: int = 0) -> Node:
    """Return a CO2 sensor node, offline with mode 1."""
    return Node(node_id, ProductId.CO2SENSOR, zone_id, mode)


@pytest.fixture
def platforms() -> list[Platform]:
    """Set up only the sensor platform."""
    return [Platform.SENSOR]


@pytest.fixture
def node_info() -> dict[int | None, NodeInfo]:
    """Return what the nodes tell about themselves: node 7 has a name ending with a space, node 54 has no name or model, node 60 can't be read."""
    return {
        **NODE_INFO,
        7: NodeInfo("Living ", "CO2 demo", "DEMO-ART-CO2", "DEMO0007", "1.2.3", 1, 0),
        54: NodeInfo(None, None, None, "DEMO0054", "1.2.4", None, None),
        **{node_id: NodeInfo(None, None, None, f"DEMO{node_id:04}", "1.2.5", None, None) for node_id in range(10, 20)},
    }


def co2_entities(entity_registry: er.EntityRegistry, entry: MockConfigEntry) -> dict[str, str]:
    """Return the entity id of each CO2 sensor, by its unique id."""
    return {
        entity.unique_id: entity.entity_id
        for entity in er.async_entries_for_config_entry(entity_registry, entry.entry_id)
        if entity.unique_id.endswith("-co2")
    }


@pytest.mark.parametrize("nodes", [[UNIT, LAN_C, co2_node(54), co2_node(7), co2_node(60), co2_node(61, zone_id=2)]])
async def test_co2_sensors(
    hass: HomeAssistant, device_registry: dr.DeviceRegistry, entity_registry: er.EntityRegistry, init_integration: MockConfigEntry
) -> None:
    """Test that each CO2 sensor in zone 1 is a device behind the bridge with a CO2 entity, identified by its serial number."""
    bridge = device_registry.async_get_device_by_identifier((DOMAIN, "DEMO0001"), init_integration.entry_id)
    living = device_registry.async_get_device_by_identifier((DOMAIN, "DEMO0007"), init_integration.entry_id)
    assert (living.name, living.model, living.model_id, living.serial_number, living.sw_version, living.hw_version) == (
        "Living",
        "CO2 demo",
        "DEMO-ART-CO2",
        "DEMO0007",
        "1.2.3",
        "1",
    )
    assert living.via_device_id == bridge.id
    # Without a model, the device gets the model of its product, and without a name, it's named after its model.
    other = device_registry.async_get_device_by_identifier((DOMAIN, "DEMO0054"), init_integration.entry_id)
    assert (other.name, other.model, other.serial_number) == ("CO2 Sensor C", "CO2 Sensor C", "DEMO0054")

    # A sensor that can't be read gets no device or entity (yet), and one in another zone none at all.
    entities = co2_entities(entity_registry, init_integration)
    assert entities == {"DEMO0007-co2": "sensor.living", "DEMO0054-co2": "sensor.co2_sensor_c"}
    assert entity_registry.async_get("sensor.living").device_id == living.id

    state = hass.states.get("sensor.living")
    assert state.state == "650"
    assert state.attributes["device_class"] == "carbon_dioxide"
    assert state.attributes["unit_of_measurement"] == "ppm"


@pytest.mark.parametrize("nodes", [[UNIT, LAN_C, co2_node(54), co2_node(7)]])
async def test_co2_sensors_are_numbered_by_node_id(hass: HomeAssistant, init_integration: MockConfigEntry) -> None:
    """Test that the n-th CO2 sensor in zone 1, by node id, reports on the n-th CO2 sensor of the unit."""
    push_sensor(init_integration, SENSOR_CO2_1, 700)
    push_sensor(init_integration, SENSOR_CO2_2, 900)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.living").state == "700"
    assert hass.states.get("sensor.co2_sensor_c").state == "900"


@pytest.mark.parametrize("nodes", [[UNIT, LAN_C, *(co2_node(node_id) for node_id in range(10, 20))]])
async def test_at_most_eight_co2_sensors(hass: HomeAssistant, entity_registry: er.EntityRegistry, init_integration: MockConfigEntry) -> None:
    """Test that only the first eight CO2 sensors get an entity, since the unit has eight CO2 sensors."""
    assert sorted(co2_entities(entity_registry, init_integration)) == [f"DEMO{node_id:04}-co2" for node_id in range(10, 18)]


@pytest.mark.parametrize("nodes", [[UNIT, LAN_C, co2_node(7)]])
async def test_co2_sensor_follows_its_node(hass: HomeAssistant, init_integration: MockConfigEntry) -> None:
    """Test that a CO2 sensor is unavailable while its node is off the bus, and available again once it's back."""
    announce_node(init_integration, co2_node(7, mode=1))
    await hass.async_block_till_done()
    assert hass.states.get("sensor.living").state == STATE_UNAVAILABLE

    announce_node(init_integration, co2_node(7))
    await hass.async_block_till_done()
    assert hass.states.get("sensor.living").state == "650"
