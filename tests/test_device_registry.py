"""Every node on the bus is a device, linked to the bridge through which we reach it."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from aiocomfoconnect.bridge import Node
from aiocomfoconnect.comfoconnect import NodeInfo
from aiocomfoconnect.const import ProductId
from aiocomfoconnect.exceptions import ComfoConnectRmiError
from custom_components.comfoconnect import EVENT_COMFOCONNECT_ALARM
from custom_components.comfoconnect.const import CONF_LOCAL_UUID, CONF_UUID, DOMAIN
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from tests.nodes import LAN_C, UNIT, announcing

# These tests set up the integration in a real Home Assistant instance. They need
# pytest-homeassistant-custom-component (and asyncio_mode = "auto"), which the dev
# dependencies don't include yet, so skip them where it isn't installed. Taken from
# importorskip's return value, since an import after it trips E402 on older ruff.
MockConfigEntry = pytest.importorskip("pytest_homeassistant_custom_component.common").MockConfigEntry

BRIDGE = "custom_components.comfoconnect.ComfoConnectBridge"
UNIT_UUID = "00" * 16
PRO = Node(20, ProductId.COMFOCONNECTPRO, 255, 2)
FLEX_WIFI = Node(41, ProductId.COMFOAIRFLEXCONNECTIONBOARD, 1, 2)
SWITCH = Node(43, ProductId.COMFOSWITCH, 1, 2)
UNKNOWN = Node(11, 25, 1, 2)
# What the nodes tell about themselves; the unknown node can't be read.
NODE_INFO = {
    None: NodeInfo("ComfoAirQ", "ComfoAir Q450", "DEMO-ART-Q", "BEA0000000001", "R1.4.0", 3, 2),
    LAN_C.node_id: NodeInfo("ComfoConnect LAN C", None, None, "DEMO0001", "R1.5.1", 1, 0),
    PRO.node_id: NodeInfo(None, None, None, "DEMO0020", "R2.0.0", 1, 0),
    FLEX_WIFI.node_id: NodeInfo(None, None, None, "DEMO0041", "R1.0.0", 1, 0),
    SWITCH.node_id: NodeInfo("ComfoSwitch", None, None, "DEMO0043", "R9.0.0", 16, 0),
}


async def get_node_info(node_id=None):
    """Return what a node tells about itself, or fail like a node that can't be read."""
    if node_id not in NODE_INFO:
        raise ComfoConnectRmiError("No answer")
    return NODE_INFO[node_id]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load the integration from custom_components."""
    return


async def setup_entry(hass: HomeAssistant, *nodes: Node) -> MockConfigEntry:
    """Set up the integration with these nodes on the bus."""
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
        await hass.async_block_till_done()
    return entry


def devices(hass: HomeAssistant, entry: MockConfigEntry) -> dict[str, tuple]:
    """Return the name, model, versions, serial number and the name of the via device of each device, by identifier."""
    registry = dr.async_get(hass)
    result = {}
    for device in dr.async_entries_for_config_entry(registry, entry.entry_id):
        via = registry.async_get(device.via_device_id).name if device.via_device_id else None
        [(_domain, identifier)] = device.identifiers
        result[identifier] = (device.name, device.model, device.sw_version, device.hw_version, device.serial_number, via)
    return result


async def test_every_node_is_a_device(hass: HomeAssistant) -> None:
    """Each node is a device with what it tells about itself and its product as model, linked to the bridge."""
    with patch.object(
        dr.DeviceRegistry,
        "async_get_or_create",
        autospec=True,
        side_effect=dr.DeviceRegistry.async_get_or_create,
    ) as get_or_create:
        entry = await setup_entry(hass, UNIT, LAN_C, SWITCH)

    # Deprecated since Home Assistant 2026.7, stops working in 2027.8.
    assert all("via_device" not in call.kwargs for call in get_or_create.call_args_list)

    assert devices(hass, entry) == {
        # A node is identified by its serial number, the unit by the uuid of the bridge.
        "DEMO0001": ("ComfoConnect LAN C", "ComfoConnect LAN C", "R1.5.1", "1", "DEMO0001", None),
        UNIT_UUID: ("ComfoAirQ", "ComfoAir Q450", "R1.4.0", "3", "BEA0000000001", "ComfoConnect LAN C"),
        "DEMO0043": ("ComfoSwitch", "ComfoSwitch C", "R9.0.0", "16", "DEMO0043", "ComfoConnect LAN C"),
    }

    # Alarm automations must identify the registered unit, rather than the LAN bridge.
    unit_device = dr.async_get(hass).async_get_device_by_identifier((DOMAIN, UNIT_UUID), entry.entry_id)
    events = []
    hass.bus.async_listen(EVENT_COMFOCONNECT_ALARM, callback(lambda event: events.append(event.data)))
    entry.runtime_data.alarm_callback(1, {79: "Replace filters"})
    await hass.async_block_till_done()
    assert events[0]["device_id"] == unit_device.id


@pytest.mark.parametrize(
    ("bridge_nodes", "expected"),
    [
        # A node that doesn't tell its name is named after its product.
        ([PRO], {"DEMO0020": ("ComfoConnect Pro", "ComfoConnect Pro", "R2.0.0", "1", "DEMO0020", None)}),
        ([FLEX_WIFI], {"DEMO0041": ("ComfoAir WiFi Connection Module", "ComfoAir WiFi Connection Module", "R1.0.0", "1", "DEMO0041", None)}),
        # A ComfoAir Flex with a LAN C: we reach the unit through the LAN C.
        (
            [FLEX_WIFI, LAN_C],
            {
                "DEMO0041": ("ComfoAir WiFi Connection Module", "ComfoAir WiFi Connection Module", "R1.0.0", "1", "DEMO0041", None),
                "DEMO0001": ("ComfoConnect LAN C", "ComfoConnect LAN C", "R1.5.1", "1", "DEMO0001", None),
            },
        ),
    ],
)
async def test_bridges(hass: HomeAssistant, bridge_nodes: list[Node], expected: dict) -> None:
    """A ComfoConnect Pro and the WiFi module of a ComfoAir Flex are bridges too."""
    entry = await setup_entry(hass, UNIT, *bridge_nodes)

    via = next(name for name, *_rest in expected.values()) if len(expected) == 1 else "ComfoConnect LAN C"
    assert devices(hass, entry) == {**expected, UNIT_UUID: ("ComfoAirQ", "ComfoAir Q450", "R1.4.0", "3", "BEA0000000001", via)}


async def test_node_announced_after_setup(hass: HomeAssistant) -> None:
    """A node that the bridge announces after setup gets a device too, and the bridge links the others to it."""
    entry = await setup_entry(hass, UNIT)
    assert devices(hass, entry)[UNIT_UUID][-1] is None

    with patch(f"{BRIDGE}.get_node_info", side_effect=get_node_info):
        entry.runtime_data._nodes[LAN_C.node_id] = LAN_C
        entry.runtime_data.node_callback(LAN_C)
        await hass.async_block_till_done()

    assert devices(hass, entry)[UNIT_UUID][-1] == "ComfoConnect LAN C"


async def test_node_that_cant_be_read(hass: HomeAssistant) -> None:
    """A node that doesn't tell its serial number gets no device, until it does when the bridge announces it again."""
    with patch.dict(NODE_INFO, {LAN_C.node_id: NodeInfo(None, None, None, None, None, None, None)}):
        entry = await setup_entry(hass, UNIT, LAN_C, UNKNOWN)
    assert list(devices(hass, entry)) == [UNIT_UUID]

    with patch(f"{BRIDGE}.get_node_info", side_effect=get_node_info):
        entry.runtime_data.node_callback(LAN_C)
        await hass.async_block_till_done()

    assert devices(hass, entry)[UNIT_UUID][-1] == "ComfoConnect LAN C"
