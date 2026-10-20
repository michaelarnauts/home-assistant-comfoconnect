"""The operating mode sensor reports auto mode as 255 since aiocomfoconnect 0.3.0."""

from types import SimpleNamespace

import pytest
from aiocomfoconnect.const import VentilationMode
from custom_components.comfoconnect.fan import ComfoConnectFan
from homeassistant.core import HomeAssistant


@pytest.mark.parametrize(("value", "expected"), [(255, VentilationMode.AUTO), (1, VentilationMode.MANUAL)])
async def test_fan_preset_follows_operating_mode(hass: HomeAssistant, value: int, expected: str) -> None:
    """The fan shows auto mode when the operating mode is all ones."""
    fan = ComfoConnectFan(SimpleNamespace(uuid="test", is_available=True), SimpleNamespace())
    fan.hass = hass
    fan.entity_id = "fan.comfoairq"

    fan._handle_mode_update(value)

    assert fan.preset_mode == expected
