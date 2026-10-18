"""A failing library call in an action is raised as a HomeAssistantError."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiocomfoconnect.exceptions import AioComfoConnectTimeout
from custom_components.comfoconnect.button import BUTTON_TYPES, ComfoConnectButton
from custom_components.comfoconnect.select import SELECT_TYPES, ComfoConnectSelect
from homeassistant.exceptions import HomeAssistantError


def test_failing_select_raises_and_keeps_its_option():
    """The option stays what the unit last reported."""

    async def scenario():
        bridge = SimpleNamespace(uuid="test", is_available=True, set_boost=AsyncMock(side_effect=AioComfoConnectTimeout("No answer")))
        description = next(item for item in SELECT_TYPES if item.key == "boost_timeout")
        entity = ComfoConnectSelect(bridge, SimpleNamespace(), description)
        entity._attr_current_option = "Off"
        with pytest.raises(HomeAssistantError, match="Failed to set Boost Mode: No answer"):
            await entity.async_select_option("10 Minutes")
        assert entity.current_option == "Off"

    asyncio.run(scenario())


def test_failing_button_raises():
    """A press that the bridge doesn't answer is reported to the user."""

    async def scenario():
        bridge = SimpleNamespace(uuid="test", is_available=True, set_boost=AsyncMock(side_effect=AioComfoConnectTimeout("No answer")))
        description = next(item for item in BUTTON_TYPES if item.key == "cancel_boost")
        entity = ComfoConnectButton(bridge, SimpleNamespace(), description)
        with pytest.raises(HomeAssistantError, match=f"Failed to press {description.name}: No answer"):
            await entity.async_press()

    asyncio.run(scenario())
