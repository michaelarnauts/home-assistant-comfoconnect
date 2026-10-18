"""The temperature profile mode select reads and writes the library property."""

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiocomfoconnect.properties import PROPERTY_TEMPERATURE_PROFILE_MODE
from custom_components.comfoconnect.select import SELECT_TYPES, ComfoConnectSelect
from homeassistant.core import HomeAssistant


@pytest.mark.parametrize("option", ["adaptive", "fixed"])
async def test_temperature_profile_mode(hass: HomeAssistant, option: str) -> None:
    """The mode is read from the property and written back as the same option."""
    bridge = SimpleNamespace(uuid="test", is_available=True, get_property=AsyncMock(return_value=option), set_property=AsyncMock())
    description = next(item for item in SELECT_TYPES if item.key == "temperature_profile_mode")
    entity = ComfoConnectSelect(bridge, SimpleNamespace(), description)
    entity.hass = hass
    entity.entity_id = "select.temperature_profile_mode"

    await entity.async_update()
    assert entity.current_option == option
    bridge.get_property.assert_awaited_once_with(PROPERTY_TEMPERATURE_PROFILE_MODE)

    await entity.async_select_option(option)
    bridge.set_property.assert_awaited_once_with(PROPERTY_TEMPERATURE_PROFILE_MODE, option)


async def test_external_setpoint_is_not_offered(caplog: pytest.LogCaptureFixture) -> None:
    """The unit only accepts adaptive and fixed, and another mode is shown as unknown without an error."""
    description = next(item for item in SELECT_TYPES if item.key == "temperature_profile_mode")
    assert description.options == ["adaptive", "fixed"]

    bridge = SimpleNamespace(uuid="test", is_available=True, get_property=AsyncMock(side_effect=ValueError("Invalid value: 2")))
    entity = ComfoConnectSelect(bridge, SimpleNamespace(), description)
    await entity.async_update()
    assert entity.current_option is None
    assert not [record for record in caplog.records if record.levelno >= logging.ERROR]
