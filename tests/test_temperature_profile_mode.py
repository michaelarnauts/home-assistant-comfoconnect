"""The temperature profile mode select maps the unit's values to adaptive and fixed."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiocomfoconnect.properties import PROPERTY_TEMPERATURE_PROFILE_MODE
from custom_components.comfoconnect.select import SELECT_TYPES, ComfoConnectSelect
from homeassistant.core import HomeAssistant


@pytest.mark.parametrize(("raw", "option"), [(0, "adaptive"), (1, "fixed")])
async def test_temperature_profile_mode(hass: HomeAssistant, raw: int, option: str) -> None:
    """The mode is read from the property and written back with the same value."""
    bridge = SimpleNamespace(uuid="test", is_available=True, get_property=AsyncMock(return_value=raw), set_property_typed=AsyncMock())
    description = next(item for item in SELECT_TYPES if item.key == "temperature_profile_mode")
    entity = ComfoConnectSelect(bridge, SimpleNamespace(), description)
    entity.hass = hass
    entity.entity_id = "select.temperature_profile_mode"

    await entity.async_update()
    assert entity.current_option == option
    bridge.get_property.assert_awaited_once_with(PROPERTY_TEMPERATURE_PROFILE_MODE)

    await entity.async_select_option(option)
    prop = PROPERTY_TEMPERATURE_PROFILE_MODE
    bridge.set_property_typed.assert_awaited_once_with(prop.unit, prop.subunit, prop.property_id, raw, prop.property_type)


async def test_external_setpoint_is_not_offered(hass: HomeAssistant) -> None:
    """The unit only accepts 0-1, and an unknown value is shown as unknown."""
    description = next(item for item in SELECT_TYPES if item.key == "temperature_profile_mode")
    assert description.options == ["adaptive", "fixed"]

    bridge = SimpleNamespace(uuid="test", is_available=True, get_property=AsyncMock(return_value=2))
    entity = ComfoConnectSelect(bridge, SimpleNamespace(), description)
    await entity.async_update()
    assert entity.current_option is None
