"""Registration names fit the bridge's UTF-8 buffer."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from custom_components.comfoconnect.config_flow import ComfoConnectConfigFlow
from homeassistant.core import HomeAssistant


@pytest.mark.parametrize("location_name", ["Home", "Chalet Bergblick", "ą" * 8, "A" * 14 + "🏠"])
def test_registration_name_fits_bridge_buffer(tmp_path, location_name):
    """Long or multibyte location names cannot produce an oversized registration."""

    async def scenario():
        hass = HomeAssistant(str(tmp_path))
        hass.config.location_name = location_name
        flow = ComfoConnectConfigFlow()
        flow.hass = hass
        flow.local_uuid = "mock-local"
        flow.bridge = SimpleNamespace(host="127.0.0.1", uuid="mock-bridge", register=AsyncMock(), disconnect=AsyncMock())
        flow.async_create_entry = Mock(return_value={"type": "create_entry"})

        await flow._register()

        device_name = flow.bridge.register.await_args.args[1]
        assert len(device_name.encode("utf-8")) <= 31
        assert device_name.startswith("Home Assistant (")
        if location_name == "Home":
            assert device_name == "Home Assistant (Home)"
        flow.bridge.disconnect.assert_awaited_once()
        flow.async_create_entry.assert_called_once()

    asyncio.run(scenario())
