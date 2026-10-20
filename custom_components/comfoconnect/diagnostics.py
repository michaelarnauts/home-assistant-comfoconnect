"""Diagnostics support for Zehnder ComfoConnect."""

from __future__ import annotations

from typing import Any

from aiocomfoconnect.bridge import Node
from aiocomfoconnect.exceptions import AioComfoConnectError
from aiocomfoconnect.sensors import SENSORS
from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from . import ComfoConnectBridge, ComfoConnectConfigEntry
from .const import CONF_LOCAL_UUID, CONF_UUID

# These files get posted publicly, so leave out what identifies the bridge, the unit or the network.
TO_REDACT = {CONF_HOST, CONF_UUID, CONF_LOCAL_UUID, "serial_number"}


async def _node_diagnostics(bridge: ComfoConnectBridge, node: Node) -> dict[str, Any]:
    """Return what we know about a node, and what it tells about itself."""
    data: dict[str, Any] = {"node_id": node.node_id, "product_id": node.product_id, "zone": node.zone_id}
    try:
        data["info"] = vars(await bridge.get_node_info(node.node_id))
    except AioComfoConnectError as err:
        data["info"] = {"error": repr(err)}
    data["active_alarms"] = bridge.active_alarms.get(node.node_id)
    return data


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ComfoConnectConfigEntry) -> dict[str, Any]:
    """Return the diagnostics of a config entry."""
    bridge = entry.runtime_data
    data = {
        "entry": entry.data,
        "bridge": {
            "type": bridge.model,
            "gateway_version": bridge.gateway_version,
            "available": bridge.is_available,
            "connection_state": bridge.connection_state,
        },
        "nodes": [await _node_diagnostics(bridge, node) for node in bridge.nodes.values()],
        "sensors": {
            sensor_id: {"name": SENSORS[sensor_id].name if sensor_id in SENSORS else None, "value": value}
            for sensor_id, value in sorted(bridge.sensor_values.items())
        },
    }
    return async_redact_data(data, TO_REDACT)
