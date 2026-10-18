"""Failed connects and setup reads release the bridge and allow Home Assistant to retry."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from aiocomfoconnect.exceptions import (
    AioComfoConnectNotConnected,
    AioComfoConnectTimeout,
    ComfoConnectNotAllowed,
    ComfoConnectOtherSession,
    ComfoConnectRmiError,
    VentilationUnitNotFoundException,
)
from custom_components.comfoconnect import DOMAIN, async_setup_entry
from custom_components.comfoconnect.const import CONF_LOCAL_UUID, CONF_UUID
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady


@pytest.mark.parametrize(
    "error",
    [
        VentilationUnitNotFoundException("No ventilation unit"),
        AioComfoConnectNotConnected("Connection closed"),
        ComfoConnectOtherSession("The app has the session"),
    ],
)
def test_failed_connect_requests_retry(error):
    """A bridge without a unit yet, a dropped connection or a session taken by the app is retried later."""

    async def scenario():
        hass = SimpleNamespace(data={})
        entry = SimpleNamespace(entry_id="entry", data={"host": "127.0.0.1", CONF_UUID: "bridge", CONF_LOCAL_UUID: "local"})
        bridge = SimpleNamespace(connect=AsyncMock(side_effect=error))
        with patch("custom_components.comfoconnect.ComfoConnectBridge", return_value=bridge), pytest.raises(ConfigEntryNotReady) as failure:
            await async_setup_entry(hass, entry)
        assert failure.value.__cause__ is error

    asyncio.run(scenario())


def test_refused_connect_starts_reauth():
    """A bridge that doesn't know our UUID asks the user to register again."""

    async def scenario():
        hass = SimpleNamespace(data={})
        entry = SimpleNamespace(entry_id="entry", data={"host": "127.0.0.1", CONF_UUID: "bridge", CONF_LOCAL_UUID: "local"})
        bridge = SimpleNamespace(connect=AsyncMock(side_effect=ComfoConnectNotAllowed("Not registered")))
        with patch("custom_components.comfoconnect.ComfoConnectBridge", return_value=bridge), pytest.raises(ConfigEntryAuthFailed):
            await async_setup_entry(hass, entry)

    asyncio.run(scenario())


@pytest.mark.parametrize("error", [ComfoConnectRmiError("Busy"), AioComfoConnectTimeout("Timed out")])
def test_failed_device_read_closes_session_and_requests_retry(error):
    """A connected bridge cannot survive a recoverable setup read failure."""

    async def scenario():
        hass = SimpleNamespace(loop=asyncio.get_running_loop(), data={})
        entry = SimpleNamespace(entry_id="entry", data={"host": "127.0.0.1", CONF_UUID: "bridge", CONF_LOCAL_UUID: "local"})
        bridge = SimpleNamespace(
            connect=AsyncMock(),
            disconnect=AsyncMock(),
            cmd_version_request=AsyncMock(return_value=Mock()),
            get_node_info=AsyncMock(side_effect=error),
        )
        with patch("custom_components.comfoconnect.ComfoConnectBridge", return_value=bridge), pytest.raises(ConfigEntryNotReady) as failure:
            await async_setup_entry(hass, entry)
        assert failure.value.__cause__ is error
        bridge.disconnect.assert_awaited_once()
        assert entry.entry_id not in hass.data[DOMAIN]

    asyncio.run(scenario())


def test_cancelled_setup_read_closes_session_and_propagates_cancellation():
    """Stopping setup releases its connection without converting cancellation to retry."""

    async def scenario():
        hass = SimpleNamespace(loop=asyncio.get_running_loop(), data={})
        entry = SimpleNamespace(entry_id="entry", data={"host": "127.0.0.1", CONF_UUID: "bridge", CONF_LOCAL_UUID: "local"})
        bridge = SimpleNamespace(connect=AsyncMock(), disconnect=AsyncMock(), cmd_version_request=AsyncMock(side_effect=asyncio.CancelledError()))
        with patch("custom_components.comfoconnect.ComfoConnectBridge", return_value=bridge), pytest.raises(asyncio.CancelledError):
            await async_setup_entry(hass, entry)
        bridge.disconnect.assert_awaited_once()
        assert entry.entry_id not in hass.data[DOMAIN]

    asyncio.run(scenario())
