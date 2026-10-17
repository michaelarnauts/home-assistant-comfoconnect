"""Alarm automation events retain their payload and change-only delivery contract."""

from custom_components.comfoconnect import EVENT_COMFOCONNECT_ALARM, ComfoConnectBridge
from homeassistant.core import HomeAssistant, callback


async def test_changed_and_cleared_alarm_events_keep_the_public_payload(hass: HomeAssistant) -> None:
    """Real HA listeners receive one event per changed node/content snapshot."""
    bridge = ComfoConnectBridge(hass, "127.0.0.1", "test-bridge")
    bridge.device_id = "unit-device"
    events = []

    @callback
    def received(event):
        events.append(event.data)

    hass.bus.async_listen(EVENT_COMFOCONNECT_ALARM, received)

    bridge.alarm_callback(1, {79: "Replace filters"})
    bridge.alarm_callback(2, {})  # The first report without alarms clears nothing.
    bridge.alarm_callback(1, {79: "Replace filters"})
    bridge.alarm_callback(2, {})
    bridge.alarm_callback(2, {21: "Sensor error"})
    bridge.alarm_callback(1, {})
    bridge.alarm_callback(2, {})
    await hass.async_block_till_done()

    base = {"device_id": "unit-device", "bridge_uuid": "test-bridge"}
    assert events == [
        {**base, "node_id": 1, "errors": [{"id": 79, "message": "Replace filters"}]},
        {**base, "node_id": 2, "errors": [{"id": 21, "message": "Sensor error"}]},
        {**base, "node_id": 1, "errors": []},
        {**base, "node_id": 2, "errors": []},
    ]


async def test_alarm_event_before_the_device_is_registered(hass: HomeAssistant) -> None:
    """Alarms reported while connecting, before setup registered the device, fire without a device_id."""
    bridge = ComfoConnectBridge(hass, "127.0.0.1", "test-bridge")
    events = []

    @callback
    def received(event):
        events.append(event.data)

    hass.bus.async_listen(EVENT_COMFOCONNECT_ALARM, received)

    bridge.alarm_callback(1, {79: "Replace filters"})
    await hass.async_block_till_done()

    assert events == [
        {"device_id": None, "bridge_uuid": "test-bridge", "node_id": 1, "errors": [{"id": 79, "message": "Replace filters"}]},
    ]
