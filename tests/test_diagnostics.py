"""Test the diagnostics."""

from unittest.mock import PropertyMock, patch

import pytest
from aiocomfoconnect import ComfoConnect
from aiocomfoconnect.bridge import Node
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.diagnostics import get_diagnostics_for_config_entry
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator
from syrupy.assertion import SnapshotAssertion
from tests.conftest import push_alarms
from tests.nodes import LAN_C, UNIT


@pytest.mark.parametrize("nodes", [[UNIT, LAN_C, Node(11, 25, 1, 2)]])
async def test_config_entry_diagnostics(
    hass: HomeAssistant, hass_client: ClientSessionGenerator, snapshot: SnapshotAssertion, init_integration: MockConfigEntry
) -> None:
    """
    Test the diagnostics: the bridge, each node with what it tells about itself, the alarms and the last sensor values.

    They leave out what identifies the bridge, the unit or the network.
    """
    push_alarms(init_integration, UNIT.node_id, {79: "Replace filters"})
    # The library keeps the last value of each sensor; one the bridge didn't send yet is None.
    sensor_values = {276: 13.0, 117: 38, 221: None}

    with patch.object(ComfoConnect, "sensor_values", new_callable=PropertyMock, return_value=sensor_values):
        diagnostics = await get_diagnostics_for_config_entry(hass, hass_client, init_integration)

    assert diagnostics == snapshot
