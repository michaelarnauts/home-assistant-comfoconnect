"""ComfoNet CO2 sensors in zone 1 get their own device, with the CO2 level of their node."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from aiocomfoconnect.bridge import Node
from aiocomfoconnect.comfoconnect import NodeInfo
from aiocomfoconnect.const import ProductId
from aiocomfoconnect.exceptions import ComfoConnectRmiError
from aiocomfoconnect.sensors import SENSOR_CO2_1, SENSOR_CO2_2
from custom_components.comfoconnect import async_remove_config_entry_device, find_co2_sensors
from custom_components.comfoconnect.const import CONF_LOCAL_UUID, CONF_UUID, DOMAIN
from custom_components.comfoconnect.sensor import ComfoConnectCO2Sensor
from custom_components.comfoconnect.sensor import async_setup_entry as async_setup_sensors
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import CONF_HOST, UnitOfRatio
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from tests.nodes import LAN_C, announcing

MockConfigEntry = pytest.importorskip("pytest_homeassistant_custom_component.common").MockConfigEntry

BRIDGE = "custom_components.comfoconnect.ComfoConnectBridge"
UNIT_UUID = "00" * 16
UNIT = Node(1, ProductId.COMFOAIRQ, 1, 0)
# What the nodes tell about themselves: node 7 has a name ending with a space, node 54 has no name or model, node 60
# can't be read.
NODE_INFO = {
    None: NodeInfo("ComfoAirQ", "ComfoAir Q450", "DEMO-ART-Q", "DEMO0001", "R1.4.0", 3, 2),
    7: NodeInfo("Living ", "CO2 demo", "DEMO-ART-CO2", "DEMO0007", "1.2.3", 1, 0),
    54: NodeInfo(None, None, None, "DEMO0054", "1.2.4", None, None),
    LAN_C.node_id: NodeInfo("ComfoConnect LAN C", None, None, "DEMO0001", "R1.5.1", 1, 0),
}


async def get_node_info(node_id=None):
    """Return what a node tells about itself, or fail like a node that can't be read."""
    if node_id not in NODE_INFO:
        raise ComfoConnectRmiError("No answer")
    return NODE_INFO[node_id]


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
        (
            [UNIT, LAN_C, co2_node(7), co2_node(54), co2_node(60)],
            [
                (SENSOR_CO2_1, ("Living", "CO2 demo", "DEMO-ART-CO2", "DEMO0007", "1.2.3", "1")),
                # Without a model, the device gets the model of its product, and without a name, it's named after its model.
                (SENSOR_CO2_2, ("CO2 Sensor C", "CO2 Sensor C", None, "DEMO0054", "1.2.4", None)),
                # A sensor that can't be read, so without a serial number, gets no device or entity (yet).
            ],
        ),
        ([UNIT, LAN_C], []),
    ],
)
async def test_co2_sensor_devices_and_entities(hass: HomeAssistant, nodes: list[Node], expected: list) -> None:
    """Each CO2 sensor is a device behind the bridge with its device info and a CO2 entity, by its serial number."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="192.0.2.10",
        data={CONF_HOST: "192.0.2.10", CONF_UUID: UNIT_UUID, CONF_LOCAL_UUID: "11" * 16},
    )
    entry.add_to_hass(hass)

    with (
        patch(f"{BRIDGE}.connect", autospec=True, side_effect=announcing(*nodes)),
        patch(f"{BRIDGE}.disconnect", new_callable=AsyncMock),
        patch(
            f"{BRIDGE}.cmd_version_request",
            new_callable=AsyncMock,
            return_value=SimpleNamespace(serialNumber="DEMO0001", gatewayVersion=0),
        ),
        patch(f"{BRIDGE}.get_node_info", side_effect=get_node_info),
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

    for entity, (sensor_id, device_info) in zip(co2_entities, expected, strict=True):
        serial_number = device_info[3]
        device = registry.async_get_device_by_identifier((DOMAIN, serial_number), entry.entry_id)
        assert (device.name, device.model, device.model_id, device.serial_number, device.sw_version, device.hw_version) == device_info
        assert device.via_device_id == bridge_device.id

        assert entity.entity_description.ccb_sensor.id == sensor_id
        assert entity.unique_id == f"{serial_number}-co2"
        assert entity.device_info["identifiers"] == device.identifiers
        assert entity.device_class == SensorDeviceClass.CO2
        assert entity.state_class == SensorStateClass.MEASUREMENT
        assert entity.native_unit_of_measurement == UnitOfRatio.PARTS_PER_MILLION
        assert entity.entity_registry_enabled_default is True


@pytest.mark.parametrize(
    ("device_id", "available", "removable"),
    [
        ("old-device", True, True),
        ("node-device", True, False),
        # The nodes aren't known while the bridge is reconnecting.
        ("old-device", False, False),
        ("unit-device", True, False),
    ],
)
async def test_only_a_device_of_no_node_on_the_bus_can_be_removed(hass: HomeAssistant, device_id: str, available: bool, removable: bool) -> None:
    """The device of a node on the bus stays; another one, e.g. of a node that left the bus, can be removed."""
    bridge = SimpleNamespace(is_available=available, device_id="unit-device", node_devices={7: (co2_node(7), "node-device", "DEMO0007")})
    device = SimpleNamespace(id=device_id)

    assert await async_remove_config_entry_device(hass, SimpleNamespace(runtime_data=bridge), device) is removable
