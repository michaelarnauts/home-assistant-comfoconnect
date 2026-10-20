"""Every node on the bus is a device, linked to the bridge through which we reach it."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import patch

import pytest
from aiocomfoconnect.bridge import Node
from aiocomfoconnect.comfoconnect import NodeInfo
from aiocomfoconnect.const import ConnectionState, ProductId
from custom_components.comfoconnect.const import DOMAIN
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.typing import WebSocketGenerator
from tests.conftest import BRIDGE_UUID, NODE_INFO, announce_node, set_connection_state
from tests.nodes import LAN_C, UNIT

PRO = Node(20, ProductId.COMFOCONNECTPRO, 255, 2)
FLEX_WIFI = Node(41, ProductId.COMFOAIRFLEXCONNECTIONBOARD, 1, 2)
SWITCH = Node(43, ProductId.COMFOSWITCH, 1, 2)
UNKNOWN = Node(11, 25, 1, 2)
UNIT_DEVICE = ("ComfoAirQ", "ComfoAir Q450", "R1.4.0", "3", "BEA0000000001")
LAN_C_DEVICE = ("ComfoConnect LAN C", "ComfoConnect LAN C", "R1.5.1", "1", "DEMO0001", None)


@pytest.fixture
def platforms() -> list[Platform]:
    """Set up no platforms, the devices come from setting up the entry."""
    return []


@pytest.fixture
def node_info() -> dict[int | None, NodeInfo]:
    """Return what the nodes tell about themselves; the unknown node can't be read."""
    return {
        **NODE_INFO,
        PRO.node_id: NodeInfo(None, None, None, "DEMO0020", "R2.0.0", 1, 0),
        FLEX_WIFI.node_id: NodeInfo(None, None, None, "DEMO0041", "R1.0.0", 1, 0),
        SWITCH.node_id: NodeInfo("ComfoSwitch", None, None, "DEMO0043", "R9.0.0", 16, 0),
    }


@pytest.fixture
def no_via_device() -> Generator[None]:
    """Check that no device is created with via_device, which is deprecated since Home Assistant 2026.7 and stops working in 2027.8."""
    with patch.object(dr.DeviceRegistry, "async_get_or_create", autospec=True, side_effect=dr.DeviceRegistry.async_get_or_create) as get_or_create:
        yield
    assert all("via_device" not in call.kwargs for call in get_or_create.call_args_list)


def devices(device_registry: dr.DeviceRegistry, entry: MockConfigEntry) -> dict[str, tuple]:
    """Return the name, model, versions, serial number and the name of the via device of each device, by identifier."""
    result = {}
    for device in dr.async_entries_for_config_entry(device_registry, entry.entry_id):
        via = device_registry.async_get(device.via_device_id).name if device.via_device_id else None
        [(_domain, identifier)] = device.identifiers
        result[identifier] = (device.name, device.model, device.sw_version, device.hw_version, device.serial_number, via)
    return result


@pytest.mark.parametrize("nodes", [[UNIT, LAN_C, SWITCH]])
@pytest.mark.usefixtures("no_via_device")
async def test_every_node_is_a_device(hass: HomeAssistant, device_registry: dr.DeviceRegistry, init_integration: MockConfigEntry) -> None:
    """Test that each node is a device with what it tells about itself and its product as model, linked to the bridge."""
    assert devices(device_registry, init_integration) == {
        # A node is identified by its serial number, the unit by the uuid of the bridge.
        "DEMO0001": LAN_C_DEVICE,
        BRIDGE_UUID: (*UNIT_DEVICE, "ComfoConnect LAN C"),
        "DEMO0043": ("ComfoSwitch", "ComfoSwitch C", "R9.0.0", "16", "DEMO0043", "ComfoConnect LAN C"),
    }


@pytest.mark.parametrize(
    ("nodes", "expected"),
    [
        # A node that doesn't tell its name is named after its product.
        ([UNIT, PRO], {"DEMO0020": ("ComfoConnect Pro", "ComfoConnect Pro", "R2.0.0", "1", "DEMO0020", None)}),
        ([UNIT, FLEX_WIFI], {"DEMO0041": ("ComfoAir WiFi Connection Module", "ComfoAir WiFi Connection Module", "R1.0.0", "1", "DEMO0041", None)}),
        # A ComfoAir Flex with a LAN C: we reach the unit through the LAN C.
        (
            [UNIT, FLEX_WIFI, LAN_C],
            {
                "DEMO0041": ("ComfoAir WiFi Connection Module", "ComfoAir WiFi Connection Module", "R1.0.0", "1", "DEMO0041", None),
                "DEMO0001": LAN_C_DEVICE,
            },
        ),
    ],
)
async def test_bridges(hass: HomeAssistant, device_registry: dr.DeviceRegistry, init_integration: MockConfigEntry, expected: dict) -> None:
    """Test that a ComfoConnect Pro and the WiFi module of a ComfoAir Flex are bridges too."""
    via = next(name for name, *_rest in expected.values()) if len(expected) == 1 else "ComfoConnect LAN C"
    assert devices(device_registry, init_integration) == {**expected, BRIDGE_UUID: (*UNIT_DEVICE, via)}


@pytest.mark.parametrize("nodes", [[UNIT]])
async def test_node_announced_after_setup(hass: HomeAssistant, device_registry: dr.DeviceRegistry, init_integration: MockConfigEntry) -> None:
    """Test that a node the bridge announces after setup gets a device too, and that the other devices are linked to the bridge then."""
    assert devices(device_registry, init_integration) == {BRIDGE_UUID: (*UNIT_DEVICE, None)}

    announce_node(init_integration, LAN_C)
    await hass.async_block_till_done()

    assert devices(device_registry, init_integration) == {"DEMO0001": LAN_C_DEVICE, BRIDGE_UUID: (*UNIT_DEVICE, "ComfoConnect LAN C")}


async def test_node_announced_again(
    hass: HomeAssistant, device_registry: dr.DeviceRegistry, node_info: dict[int | None, NodeInfo], init_integration: MockConfigEntry
) -> None:
    """Test that a node the bridge announces again, like it does in every new session, keeps its device without being read again."""
    node_info[LAN_C.node_id] = NodeInfo("ComfoConnect LAN C", None, None, "DEMO0002", "R1.5.1", 1, 0)
    announce_node(init_integration, LAN_C)
    await hass.async_block_till_done()
    assert "DEMO0002" not in devices(device_registry, init_integration)


@pytest.fixture
def unreadable_lan_c(node_info: dict[int | None, NodeInfo]) -> None:
    """Let the LAN C answer without a serial number."""
    node_info[LAN_C.node_id] = NodeInfo(None, None, None, None, None, None, None)


@pytest.mark.parametrize("nodes", [[UNIT, LAN_C, UNKNOWN]])
async def test_node_that_cant_be_read(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    node_info: dict[int | None, NodeInfo],
    unreadable_lan_c: None,
    init_integration: MockConfigEntry,
) -> None:
    """Test that a node without a serial number gets no device, until it tells it when the bridge announces it again."""
    # The unknown product that can't be read gets no device either.
    assert devices(device_registry, init_integration) == {BRIDGE_UUID: (*UNIT_DEVICE, None)}

    node_info[LAN_C.node_id] = NODE_INFO[LAN_C.node_id]
    announce_node(init_integration, LAN_C)
    await hass.async_block_till_done()

    assert devices(device_registry, init_integration) == {"DEMO0001": LAN_C_DEVICE, BRIDGE_UUID: (*UNIT_DEVICE, "ComfoConnect LAN C")}


@pytest.mark.parametrize("nodes", [[UNIT, LAN_C, SWITCH]])
@pytest.mark.parametrize(
    ("identifier", "offline", "available", "removable"),
    [
        ("DEMO0043", False, True, False),
        ("DEMO0043", True, True, True),
        # The nodes aren't known while the bridge is reconnecting.
        ("DEMO0043", True, False, False),
        (BRIDGE_UUID, False, True, False),
    ],
)
async def test_remove_device(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    device_registry: dr.DeviceRegistry,
    init_integration: MockConfigEntry,
    identifier: str,
    offline: bool,
    available: bool,
    removable: bool,
) -> None:
    """Test that only the device of a node that's no longer on the bus can be removed, and never the unit's."""
    assert await async_setup_component(hass, "config", {})
    if offline:
        announce_node(init_integration, Node(SWITCH.node_id, SWITCH.product_id, SWITCH.zone_id, 1))
    if not available:
        set_connection_state(init_integration, ConnectionState.DISCONNECTED)
    await hass.async_block_till_done()
    device = device_registry.async_get_device_by_identifier((DOMAIN, identifier), init_integration.entry_id)

    client = await hass_ws_client(hass)
    await client.send_json_auto_id(
        {"type": "config/device_registry/remove_config_entry", "config_entry_id": init_integration.entry_id, "device_id": device.id}
    )
    response = await client.receive_json()

    assert response["success"] is removable
