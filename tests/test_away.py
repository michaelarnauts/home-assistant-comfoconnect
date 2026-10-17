"""Away timers support holiday durations and both cancellation controls."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from custom_components.comfoconnect.button import BUTTON_TYPES, ComfoConnectButton
from custom_components.comfoconnect.select import SELECT_TYPES, ComfoConnectSelect
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_setup as setup_loader


@pytest.mark.parametrize("option,seconds", [("10 Minutes", 600), ("8 Hours", 28800), ("14 Days", 1209600)])
def test_away_duration_status_and_cancellation(tmp_path, option, seconds):
    """Supported duration units reach the device in seconds and publish Active."""

    async def scenario():
        hass = HomeAssistant(str(tmp_path))
        setup_loader(hass)
        bridge = SimpleNamespace(uuid="test", is_available=True, set_away=AsyncMock(), get_away=AsyncMock(return_value=False))
        description = next(item for item in SELECT_TYPES if item.key == "away_timeout")
        entity = ComfoConnectSelect(bridge, SimpleNamespace(), description)
        entity.hass = hass
        entity.entity_id = "select.away"
        await entity.async_select_option(option)
        bridge.set_away.assert_awaited_once_with(True, seconds)
        assert hass.states.get(entity.entity_id).state == "Active"
        bridge.get_away.return_value = False
        await entity.async_select_option("Active")
        assert bridge.set_away.await_count == 1
        assert hass.states.get(entity.entity_id).state == "Off"
        await entity.async_select_option("Off")
        assert bridge.set_away.await_args.args == (False,)
        button_description = next(item for item in BUTTON_TYPES if item.key == "cancel_away")
        button = ComfoConnectButton(bridge, SimpleNamespace(), button_description)
        await button.async_press()
        assert bridge.set_away.await_count == 3
        assert bridge.set_away.await_args.args == (False,)

    asyncio.run(scenario())
