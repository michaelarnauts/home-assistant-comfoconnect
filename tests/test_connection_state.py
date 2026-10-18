"""Availability and reauthentication follow the connection state the library reports."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from aiocomfoconnect.const import ConnectionState
from aiocomfoconnect.exceptions import AioComfoConnectTimeout
from aiocomfoconnect.sensors import SENSOR_CO2_1, SENSOR_COMFOCOOL_STATE, SENSOR_TEMPERATURE_EXTRACT
from custom_components.comfoconnect import SIGNAL_COMFOCONNECT_AVAILABILITY, ComfoConnectBridge, async_unload_entry
from custom_components.comfoconnect.binary_sensor import SENSOR_TYPES as BINARY_SENSOR_TYPES
from custom_components.comfoconnect.binary_sensor import ComfoConnectAlarmBinarySensor, ComfoConnectBinarySensor
from custom_components.comfoconnect.button import BUTTON_TYPES, ComfoConnectButton
from custom_components.comfoconnect.const import CONF_UUID
from custom_components.comfoconnect.fan import ComfoConnectFan
from custom_components.comfoconnect.select import SELECT_TYPES, ComfoConnectSelect
from custom_components.comfoconnect.sensor import SENSOR_TYPES, ComfoConnectCO2Sensor, ComfoConnectSensor
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect, async_dispatcher_send


async def test_availability_follows_the_session(hass: HomeAssistant) -> None:
    """Entities become unavailable while the library reconnects, and available again once the session is up."""
    bridge = ComfoConnectBridge(hass, Mock(data={CONF_UUID: "test-bridge"}), "192.0.2.10")
    changes = []
    async_dispatcher_connect(hass, SIGNAL_COMFOCONNECT_AVAILABILITY.format(bridge.uuid), callback(lambda available: changes.append(available)))

    bridge.connection_state_callback(ConnectionState.DISCONNECTED)
    assert not bridge.is_available
    bridge.connection_state_callback(ConnectionState.CONNECTED)
    assert bridge.is_available
    assert changes == [False, True]


async def test_refused_session_starts_reauth(hass: HomeAssistant) -> None:
    """When the bridge no longer knows us, the library stops reconnecting and the user is asked to register again."""
    entry = Mock(data={CONF_UUID: "test-bridge"})
    bridge = ComfoConnectBridge(hass, entry, "192.0.2.10")

    bridge.connection_state_callback(ConnectionState.NOT_ALLOWED)
    assert not bridge.is_available
    entry.async_start_reauth.assert_called_once_with(hass)


async def test_unload_entry_disconnects_the_bridge(hass: HomeAssistant) -> None:
    """Unloading stops the library's session and its reconnects."""
    bridge = SimpleNamespace(disconnect=AsyncMock())
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    assert await async_unload_entry(hass, SimpleNamespace(runtime_data=bridge))
    bridge.disconnect.assert_awaited_once()


async def test_polled_select_waits_for_the_session(hass: HomeAssistant) -> None:
    """A polled select doesn't send requests while the bridge reconnects, and keeps its state when a request fails."""
    description = next(item for item in SELECT_TYPES if item.key == "balance_mode")
    bridge = SimpleNamespace(uuid="test", is_available=False, get_balance_mode=AsyncMock(return_value="balance"))
    entity = ComfoConnectSelect(bridge, SimpleNamespace(), description)

    await entity.async_update()
    bridge.get_balance_mode.assert_not_awaited()

    bridge.is_available = True
    await entity.async_update()
    assert entity.current_option == "balance"

    entity._last_update = None
    bridge.get_balance_mode.side_effect = AioComfoConnectTimeout("Timed out")
    await entity.async_update()
    assert entity.current_option == "balance"


def _entities(bridge):
    """Return one entity of each platform, and the CO2 sensor that has its own device."""
    entry = SimpleNamespace()
    return [
        ComfoConnectSensor(bridge, entry, next(item for item in SENSOR_TYPES if item.key == SENSOR_TEMPERATURE_EXTRACT)),
        ComfoConnectCO2Sensor(bridge, entry, 7, SENSOR_CO2_1),
        ComfoConnectBinarySensor(bridge, entry, next(item for item in BINARY_SENSOR_TYPES if item.key == SENSOR_COMFOCOOL_STATE)),
        ComfoConnectAlarmBinarySensor(bridge),
        ComfoConnectSelect(bridge, entry, next(item for item in SELECT_TYPES if item.key == "balance_mode")),
        ComfoConnectButton(bridge, entry, next(item for item in BUTTON_TYPES if item.key == "cancel_boost")),
        ComfoConnectFan(bridge, entry),
    ]


async def test_entities_follow_the_bridge_availability(hass: HomeAssistant) -> None:
    """Every platform's entities go unavailable and come back with the bridge."""
    bridge = SimpleNamespace(uuid="test", is_available=True, active_alarms={}, register_sensor=AsyncMock(), get_mode=AsyncMock(return_value="auto"))
    entities = _entities(bridge)
    for index, entity in enumerate(entities):
        entity.hass = hass
        entity.entity_id = f"test.entity_{index}"
        await entity.async_added_to_hass()

    async_dispatcher_send(hass, SIGNAL_COMFOCONNECT_AVAILABILITY.format("test"), False)
    assert [hass.states.get(entity.entity_id).state for entity in entities] == [STATE_UNAVAILABLE] * len(entities)
    async_dispatcher_send(hass, SIGNAL_COMFOCONNECT_AVAILABILITY.format("test"), True)
    assert STATE_UNAVAILABLE not in [hass.states.get(entity.entity_id).state for entity in entities]


def test_entities_keep_their_unique_id_and_device() -> None:
    """The unit's entities stay on the unit's device, the CO2 sensor on its own."""
    bridge = SimpleNamespace(uuid="test", is_available=True, active_alarms={})
    unique_ids = [entity.unique_id for entity in _entities(bridge)]
    assert unique_ids == ["test-274", "test-co2-7", "test-784", "test-active_alarms", "test-balance_mode", "test-cancel_boost", "test"]
    devices = [entity.device_info["identifiers"] for entity in _entities(bridge)]
    assert devices == [{("comfoconnect", "test")}] + [{("comfoconnect", "test-7")}] + [{("comfoconnect", "test")}] * 5
