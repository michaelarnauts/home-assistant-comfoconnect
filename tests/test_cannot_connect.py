"""A bridge that can't be reached shows cannot_connect in the form, or aborts when there is no form."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from aiocomfoconnect.exceptions import AioComfoConnectTimeout, ComfoConnectNotAllowed, ComfoConnectOtherSession
from custom_components.comfoconnect.config_flow import ComfoConnectConfigFlow
from custom_components.comfoconnect.const import CONF_LOCAL_UUID, CONF_UUID
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PIN
from homeassistant.core import HomeAssistant

ERRORS = [AioComfoConnectTimeout("timeout"), ComfoConnectOtherSession("busy")]


def _bridge(error):
    return SimpleNamespace(host="127.0.0.1", uuid="mock-bridge", register=AsyncMock(side_effect=error), disconnect=AsyncMock())


def _flow(tmp_path, source, bridge):
    hass = HomeAssistant(str(tmp_path))
    flow = ComfoConnectConfigFlow()
    flow.hass = hass
    flow.handler = "comfoconnect"
    flow.flow_id = "mock-flow"
    flow.context = {"source": source}
    flow.local_uuid = "mock-local"
    flow.bridge = bridge
    flow.async_set_unique_id = AsyncMock()
    flow._abort_if_unique_id_configured = Mock()
    flow._async_current_ids = Mock(return_value=set())
    return flow


def _discover(bridge):
    return patch("custom_components.comfoconnect.config_flow.aiocomfoconnect.discover_bridges", AsyncMock(return_value=[bridge]))


@pytest.mark.parametrize("error", ERRORS)
def test_user_step_shows_cannot_connect(tmp_path, error):
    """Picking a discovered bridge that can't be reached shows the bridge list again."""

    async def scenario():
        bridge = _bridge(error)
        flow = _flow(tmp_path, config_entries.SOURCE_USER, None)
        flow.discovered_bridges = {bridge.uuid: bridge}
        with (
            _discover(bridge),
            patch("custom_components.comfoconnect.config_flow.network.async_get_ipv4_broadcast_addresses", AsyncMock(return_value=[])),
        ):
            result = await flow.async_step_user({CONF_UUID: bridge.uuid})
        assert result["type"] == "form"
        assert result["step_id"] == "user"
        assert result["errors"] == {"base": "cannot_connect"}
        bridge.disconnect.assert_awaited_once()

    asyncio.run(scenario())


@pytest.mark.parametrize("error", ERRORS)
def test_manual_step_shows_cannot_connect(tmp_path, error):
    """A manually entered bridge that can't be reached shows the host form again, with the host filled in."""

    async def scenario():
        bridge = _bridge(error)
        flow = _flow(tmp_path, config_entries.SOURCE_USER, None)
        with _discover(bridge):
            result = await flow.async_step_manual({CONF_HOST: "127.0.0.1"})
        assert result["type"] == "form"
        assert result["step_id"] == "manual"
        assert result["errors"] == {"base": "cannot_connect"}
        (key,) = result["data_schema"].schema
        assert key.description == {"suggested_value": "127.0.0.1"}

    asyncio.run(scenario())


def test_enter_pin_step_shows_cannot_connect(tmp_path):
    """Losing the bridge after entering a PIN shows the PIN form again."""

    async def scenario():
        bridge = _bridge(AioComfoConnectTimeout("timeout"))
        flow = _flow(tmp_path, config_entries.SOURCE_USER, bridge)
        result = await flow.async_step_enter_pin({CONF_PIN: 1234})
        assert result["type"] == "form"
        assert result["step_id"] == "enter_pin"
        assert result["errors"] == {"base": "cannot_connect"}

    asyncio.run(scenario())


def test_not_allowed_still_asks_for_pin(tmp_path):
    """A refused PIN keeps asking for the PIN instead of reporting cannot_connect."""

    async def scenario():
        bridge = _bridge(ComfoConnectNotAllowed("refused"))
        flow = _flow(tmp_path, config_entries.SOURCE_USER, bridge)
        result = await flow.async_step_enter_pin({CONF_PIN: 1234})
        assert result["type"] == "form"
        assert result["step_id"] == "enter_pin"
        assert result["errors"] == {"base": "invalid_pin"}

    asyncio.run(scenario())


def test_reauth_aborts_with_cannot_connect(tmp_path):
    """Reauth has no form to return to, so it aborts."""

    async def scenario():
        bridge = _bridge(AioComfoConnectTimeout("timeout"))
        flow = _flow(tmp_path, config_entries.SOURCE_REAUTH, None)
        with _discover(bridge):
            result = await flow.async_step_reauth({CONF_HOST: "127.0.0.1", CONF_UUID: bridge.uuid, CONF_LOCAL_UUID: "mock-local"})
        assert result["type"] == "abort"
        assert result["reason"] == "cannot_connect"

    asyncio.run(scenario())


def test_import_aborts_with_cannot_connect(tmp_path):
    """A YAML import has no form to return to, so it aborts."""

    async def scenario():
        bridge = _bridge(AioComfoConnectTimeout("timeout"))
        flow = _flow(tmp_path, config_entries.SOURCE_IMPORT, None)
        with _discover(bridge):
            result = await flow.async_step_import({CONF_HOST: "127.0.0.1", "token": "mock-local"})
        assert result["type"] == "abort"
        assert result["reason"] == "cannot_connect"

    asyncio.run(scenario())
