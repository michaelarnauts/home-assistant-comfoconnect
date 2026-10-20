"""The diagnostics describe the bridge, its nodes and sensors, without what identifies them."""

from unittest.mock import AsyncMock, Mock

from aiocomfoconnect.bridge import Node
from aiocomfoconnect.comfoconnect import NodeInfo
from aiocomfoconnect.const import ConnectionState
from aiocomfoconnect.exceptions import AioComfoConnectTimeout
from custom_components.comfoconnect.diagnostics import async_get_config_entry_diagnostics
from homeassistant.components.diagnostics import REDACTED
from homeassistant.core import HomeAssistant


async def test_config_entry_diagnostics(hass: HomeAssistant) -> None:
    """Report the bridge, each node with its info or error, the alarms and the last sensor values."""
    entry = Mock(data={"host": "192.0.2.1", "uuid": "00" * 16, "local_uuid": "11" * 16})
    info = NodeInfo("ComfoAirQ", "ComfoAirQ 350", "471502004", "SERIAL123", "R1.12.0", 2, 1)
    bridge = Mock(
        is_available=True,
        connection_state=ConnectionState.CONNECTED,
        nodes={1: Node(1, 1, 1, 1), 2: Node(2, 5, 1, 1)},
        get_node_info=AsyncMock(side_effect=[info, AioComfoConnectTimeout("no answer")]),
        active_alarms={1: {79: "Replace filters"}},
        sensor_values={276: 12.3, 117: 34, 221: None},
    )
    entry.runtime_data = bridge

    data = await async_get_config_entry_diagnostics(hass, entry)

    assert data == {
        "entry": {"host": REDACTED, "uuid": REDACTED, "local_uuid": REDACTED},
        "bridge": {"available": True, "connection_state": "connected"},
        "nodes": [
            {
                "node_id": 1,
                "product_id": 1,
                "zone": 1,
                "info": {
                    "name": "ComfoAirQ",
                    "model": "ComfoAirQ 350",
                    "article_number": "471502004",
                    "serial_number": REDACTED,
                    "firmware": "R1.12.0",
                    "hardware_version": 2,
                    "product_variant": 1,
                },
                "active_alarms": {79: "Replace filters"},
            },
            {"node_id": 2, "product_id": 5, "zone": 1, "info": {"error": "AioComfoConnectTimeout('no answer')"}, "active_alarms": None},
        ],
        "sensors": {
            117: {"name": "Exhaust Fan Duty", "value": 34},
            221: {"name": "Supply Air Temperature", "value": None},
            276: {"name": "Outdoor Air Temperature", "value": 12.3},
        },
    }
