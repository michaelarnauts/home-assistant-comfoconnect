"""ComfoNet CO2 sensors in zone 1 get their own device, with the CO2 level of their node."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, PropertyMock, patch

import pytest
from aiocomfoconnect.bridge import Node
from aiocomfoconnect.const import ProductId
from aiocomfoconnect.sensors import SENSOR_CO2_1, SENSOR_CO2_2
from custom_components.comfoconnect import find_co2_sensors
from custom_components.comfoconnect.const import CONF_LOCAL_UUID, CONF_UUID, DOMAIN
from custom_components.comfoconnect.sensor import ComfoConnectCO2Sensor
from custom_components.comfoconnect.sensor import async_setup_entry as async_setup_sensors
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import CONCENTRATION_PARTS_PER_MILLION, CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

MockConfigEntry = pytest.importorskip("pytest_homeassistant_custom_component.common").MockConfigEntry

BRIDGE = "custom_components.comfoconnect.ComfoConnectBridge"
UNIT_UUID = "00" * 16
UNIT = Node(1, ProductId.COMFOAIRQ, 1, 0)


def co2_node(node_id: int, zone_id: int = 1) -> Node:
    """Return a CO2 sensor node."""
    return Node(node_id, ProductId.CO2SENSOR, zone_id, 0)


def test_co2_sensors_are_numbered_by_node_id_in_zone_1() -> None:
    """The n-th CO2 sensor in zone 1 reports on SENSOR_CO2_n; other zones and products are skipped."""
    nodes = [UNIT, co2_node(54), co2_node(7), co2_node(60, zone_id=2)]
    bridge = SimpleNamespace(nodes={node.node_id: node for node in nodes})

    assert find_co2_sensors(bridge) == [(7, SENSOR_CO2_1), (54, SENSOR_CO2_2)]


def test_at_most_eight_co2_sensors() -> None:
    """There are only eight CO2 sensor PDOs."""
    bridge = SimpleNamespace(nodes={node_id: co2_node(node_id) for node_id in range(10, 20)})

    assert [node_id for node_id, _ in find_co2_sensors(bridge)] == list(range(10, 18))


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load the integration from custom_components."""
    return


@pytest.mark.parametrize(
    ("nodes", "expected"),
    [
        ([UNIT, co2_node(7), co2_node(54)], [(7, SENSOR_CO2_1, "CO2 sensor 1"), (54, SENSOR_CO2_2, "CO2 sensor 2")]),
        ([UNIT], []),
    ],
)
async def test_co2_sensor_devices_and_entities(hass: HomeAssistant, nodes: list[Node], expected: list) -> None:
    """Each CO2 sensor is a device behind the bridge with one CO2 entity; without CO2 sensors there are none."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="192.0.2.10",
        data={CONF_HOST: "192.0.2.10", CONF_UUID: UNIT_UUID, CONF_LOCAL_UUID: "11" * 16},
    )
    entry.add_to_hass(hass)

    with (
        patch(f"{BRIDGE}.connect", new_callable=AsyncMock),
        patch(f"{BRIDGE}.disconnect", new_callable=AsyncMock),
        patch(f"{BRIDGE}.nodes", new_callable=PropertyMock, return_value={node.node_id: node for node in nodes}),
        patch(
            f"{BRIDGE}.cmd_version_request",
            new_callable=AsyncMock,
            return_value=SimpleNamespace(serialNumber="DEMO0001", gatewayVersion=0),
        ),
        patch(f"{BRIDGE}.get_property", new_callable=AsyncMock, return_value="demo"),
        patch("custom_components.comfoconnect.version_decode", return_value="1.0.0"),
        patch(
            "homeassistant.config_entries.ConfigEntries.async_forward_entry_setups",
            new_callable=AsyncMock,
            return_value=True,
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)

    registry = dr.async_get(hass)
    bridge_device = registry.async_get_device_by_identifier((DOMAIN, "DEMO0001"), entry.entry_id)
    devices = dr.async_entries_for_config_entry(registry, entry.entry_id)
    # The bridge and the unit, plus one device per CO2 sensor.
    assert len(devices) == 2 + len(expected)

    entities = []
    await async_setup_sensors(hass, entry, lambda new, update_before_add=False: entities.extend(new))
    co2_entities = [entity for entity in entities if isinstance(entity, ComfoConnectCO2Sensor)]
    assert len(co2_entities) == len(expected)

    for entity, (node_id, sensor_id, name) in zip(co2_entities, expected, strict=True):
        device = registry.async_get_device_by_identifier((DOMAIN, f"{UNIT_UUID}-{node_id}"), entry.entry_id)
        assert device.name == name
        assert device.via_device_id == bridge_device.id

        assert entity.entity_description.ccb_sensor.id == sensor_id
        assert entity.unique_id == f"{UNIT_UUID}-co2-{node_id}"
        assert entity.device_info["identifiers"] == device.identifiers
        assert entity.device_class == SensorDeviceClass.CO2
        assert entity.state_class == SensorStateClass.MEASUREMENT
        assert entity.native_unit_of_measurement == CONCENTRATION_PARTS_PER_MILLION
        assert entity.entity_registry_enabled_default is True
