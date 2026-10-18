"""Changed alarms reach the diagnostic binary sensor through HA's dispatcher."""

import asyncio
from unittest.mock import Mock, patch

import pytest
from custom_components.comfoconnect import ComfoConnectBridge
from custom_components.comfoconnect.binary_sensor import ComfoConnectAlarmBinarySensor
from custom_components.comfoconnect.const import CONF_UUID
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_setup as setup_loader


def test_alarm_changes_and_clear_publish_sensor_state(tmp_path):
    """Alarm content and attributes remain correct across changes and clears."""

    async def scenario():
        hass = HomeAssistant(str(tmp_path))
        setup_loader(hass)
        bridge = ComfoConnectBridge(hass, Mock(data={CONF_UUID: "test-bridge"}), "127.0.0.1")
        entity = ComfoConnectAlarmBinarySensor(bridge)
        entity.hass = hass
        entity.entity_id = "binary_sensor.alarms"
        await entity.async_added_to_hass()
        entity.async_write_ha_state()
        try:
            incoming = {79: "Replace filters"}
            bridge.alarm_callback(1, incoming)
            incoming[79] = "Mutated after callback"
            await hass.async_block_till_done()
            state = hass.states.get(entity.entity_id)
            assert state.state == "on"
            assert state.attributes["alarms"] == [{"node_id": 1, "id": 79, "message": "Replace filters"}]
            # Another node reporting no alarms must not clear the alarm of node 1.
            bridge.alarm_callback(2, {})
            await hass.async_block_till_done()
            assert hass.states.get(entity.entity_id).state == "on"
            bridge.alarm_callback(2, {79: "Check node 2"})
            await hass.async_block_till_done()
            state = hass.states.get(entity.entity_id)
            assert state.attributes["alarm_count"] == 2
            assert {alarm["node_id"] for alarm in state.attributes["alarms"]} == {1, 2}
            bridge.alarm_callback(1, {})
            await hass.async_block_till_done()
            state = hass.states.get(entity.entity_id)
            assert state.state == "on"
            assert state.attributes["alarms"] == [{"node_id": 2, "id": 79, "message": "Check node 2"}]
            bridge.alarm_callback(2, {})
            await hass.async_block_till_done()
            state = hass.states.get(entity.entity_id)
            assert state.state == "off"
            assert state.attributes["alarm_count"] == 0
            bridge.set_available(False)
            assert hass.states.get(entity.entity_id).state == "unavailable"
        finally:
            await entity.async_will_remove_from_hass()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "initial,current,expected",
    [(None, None, "unknown"), (None, {79: "Replace filters"}, "on"), ({79: "Replace filters"}, {}, "off")],
)
def test_alarm_subscription_uses_the_current_snapshot(tmp_path, initial, current, expected):
    """An unreceived snapshot is unknown; subscription uses the latest known alarms."""

    async def scenario():
        hass = HomeAssistant(str(tmp_path))
        setup_loader(hass)
        bridge = ComfoConnectBridge(hass, Mock(data={CONF_UUID: "test-bridge"}), "127.0.0.1")
        if initial is not None:
            bridge.alarm_callback(1, initial)
        entity = ComfoConnectAlarmBinarySensor(bridge)
        entity.hass = hass
        entity.entity_id = "binary_sensor.alarms"
        if current is not None:
            bridge.alarm_callback(1, current)
        await hass.async_block_till_done()
        await entity.async_added_to_hass()
        try:
            entity.async_write_ha_state()
            state = hass.states.get(entity.entity_id)
            assert state.state == expected
            assert state.attributes["alarm_count"] == len(current or {})
        finally:
            await entity.async_will_remove_from_hass()

    asyncio.run(scenario())


def test_identical_alarms_do_not_repeat_dispatch(tmp_path):
    """Node and content changes are observable; duplicate callbacks are suppressed."""

    async def scenario():
        hass = HomeAssistant(str(tmp_path))
        bridge = ComfoConnectBridge(hass, Mock(data={CONF_UUID: "test-bridge"}), "127.0.0.1")
        with patch("custom_components.comfoconnect.dispatcher_send", new=Mock()) as send:
            bridge.alarm_callback(1, {79: "Replace filters"})
            bridge.alarm_callback(1, {79: "Replace filters"})
            assert send.call_count == 1
            bridge.alarm_callback(2, {79: "Replace filters"})
            bridge.alarm_callback(2, {})
            bridge.alarm_callback(2, {})
            assert send.call_count == 3

    asyncio.run(scenario())
