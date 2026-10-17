"""Bypass timers report valid status options and restore automatic control."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiocomfoconnect.const import VentilationSetting
from custom_components.comfoconnect.select import SELECT_TYPES, ComfoConnectSelect
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_setup as setup_loader


@pytest.mark.parametrize("minutes", [10, 20, 30, 40, 50, 60])
def test_bypass_duration_status_and_cancellation(tmp_path, minutes):
    """Durations force bypass on; Off restores auto and Active only reads state."""

    async def scenario():
        hass = HomeAssistant(str(tmp_path))
        setup_loader(hass)
        bridge = SimpleNamespace(uuid="test", is_available=True, set_bypass=AsyncMock(), get_bypass=AsyncMock(return_value=VentilationSetting.AUTO))
        description = next(item for item in SELECT_TYPES if item.key == "bypass_timeout")
        entity = ComfoConnectSelect(bridge, SimpleNamespace(), description)
        entity.hass = hass
        entity.entity_id = "select.bypass_timer"
        await entity.async_select_option("Active")
        bridge.set_bypass.assert_not_awaited()
        assert hass.states.get(entity.entity_id).state == "Off"
        await entity.async_select_option(f"{minutes} Minutes")
        bridge.set_bypass.assert_awaited_once_with(VentilationSetting.ON, minutes * 60)
        assert hass.states.get(entity.entity_id).state == "Active"
        for mode, expected in ((VentilationSetting.ON, "Active"), (VentilationSetting.AUTO, "Off"), (VentilationSetting.OFF, "Off")):
            bridge.get_bypass.return_value = mode
            await entity.async_update()
            assert entity.current_option == expected
            assert entity.current_option in entity.options
        bridge.get_bypass.return_value = VentilationSetting.ON
        await entity.async_select_option("Active")
        assert bridge.set_bypass.await_count == 1
        assert hass.states.get(entity.entity_id).state == "Active"
        await entity.async_select_option("Off")
        assert bridge.set_bypass.await_args.args == (VentilationSetting.AUTO,)
        assert hass.states.get(entity.entity_id).state == "Off"

    asyncio.run(scenario())
