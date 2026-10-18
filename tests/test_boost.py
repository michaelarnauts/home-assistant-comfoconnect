"""Boost reports valid status options and can be cancelled through either control."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from custom_components.comfoconnect.button import BUTTON_TYPES, ComfoConnectButton
from custom_components.comfoconnect.select import SELECT_TYPES, ComfoConnectSelect
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_setup as setup_loader


def test_boost_status_duration_and_off(tmp_path):
    """A duration starts Boost; status selection reads it and Off cancels it."""

    async def scenario():
        hass = HomeAssistant(str(tmp_path))
        setup_loader(hass)
        bridge = SimpleNamespace(uuid="test", is_available=True, set_boost=AsyncMock(), get_boost=AsyncMock(return_value=False))
        description = next(item for item in SELECT_TYPES if item.key == "boost_timeout")
        entity = ComfoConnectSelect(bridge, SimpleNamespace(), description)
        entity.hass = hass
        entity.entity_id = "select.boost"
        await entity.async_select_option("active")
        bridge.set_boost.assert_not_awaited()
        assert hass.states.get(entity.entity_id).state == "off"
        await entity.async_select_option("10")
        bridge.set_boost.assert_awaited_once_with(True, 600)
        assert hass.states.get(entity.entity_id).state == "active"
        bridge.get_boost.return_value = True
        await entity.async_update()
        assert entity.current_option == "active"
        await entity.async_select_option("off")
        assert bridge.set_boost.await_args.args == (False,)
        assert hass.states.get(entity.entity_id).state == "off"

    asyncio.run(scenario())


def test_cancel_boost_button_uses_library_cancellation():
    """The separate cancellation button has the same device effect as Off."""

    async def scenario():
        bridge = SimpleNamespace(uuid="test", is_available=True, set_boost=AsyncMock())
        description = next(item for item in BUTTON_TYPES if item.key == "cancel_boost")
        entity = ComfoConnectButton(bridge, SimpleNamespace(), description)
        await entity.async_press()
        bridge.set_boost.assert_awaited_once_with(False)

    asyncio.run(scenario())
