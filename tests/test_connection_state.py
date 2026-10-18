"""Availability and reauthentication follow the connection state the library reports."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from aiocomfoconnect.const import ConnectionState
from aiocomfoconnect.exceptions import AioComfoConnectTimeout
from custom_components.comfoconnect import SIGNAL_COMFOCONNECT_AVAILABILITY, ComfoConnectBridge, async_unload_entry
from custom_components.comfoconnect.const import DOMAIN
from custom_components.comfoconnect.select import SELECT_TYPES, ComfoConnectSelect
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect


async def test_availability_follows_the_session(hass: HomeAssistant) -> None:
    """Entities become unavailable while the library reconnects, and available again once the session is up."""
    bridge = ComfoConnectBridge(hass, "192.0.2.10", "test-bridge")
    changes = []
    async_dispatcher_connect(hass, SIGNAL_COMFOCONNECT_AVAILABILITY.format(bridge.uuid), callback(lambda available: changes.append(available)))

    bridge.connection_state_callback(ConnectionState.DISCONNECTED)
    assert not bridge.is_available
    bridge.connection_state_callback(ConnectionState.CONNECTED)
    assert bridge.is_available
    assert changes == [False, True]


async def test_refused_session_starts_reauth(hass: HomeAssistant) -> None:
    """When the bridge no longer knows us, the library stops reconnecting and the user is asked to register again."""
    bridge = ComfoConnectBridge(hass, "192.0.2.10", "test-bridge")
    bridge.entry = Mock()

    bridge.connection_state_callback(ConnectionState.NOT_ALLOWED)
    assert not bridge.is_available
    bridge.entry.async_start_reauth.assert_called_once_with(hass)


async def test_unload_entry_disconnects_the_bridge(hass: HomeAssistant) -> None:
    """Unloading stops the library's session and its reconnects."""
    bridge = SimpleNamespace(disconnect=AsyncMock())
    hass.data[DOMAIN] = {"entry": bridge}
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    assert await async_unload_entry(hass, SimpleNamespace(entry_id="entry"))
    bridge.disconnect.assert_awaited_once()
    assert "entry" not in hass.data[DOMAIN]


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
