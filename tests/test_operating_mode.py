"""The operating mode sensor reports auto mode as 255 since aiocomfoconnect 0.3.0."""

from types import SimpleNamespace

import pytest
from aiocomfoconnect.const import VentilationMode
from custom_components.comfoconnect.fan import ComfoConnectFan
from custom_components.comfoconnect.select import SELECT_TYPES
from homeassistant.core import HomeAssistant


@pytest.mark.parametrize(("value", "expected"), [(255, VentilationMode.AUTO), (1, VentilationMode.MANUAL), (5, VentilationMode.MANUAL)])
async def test_fan_preset_follows_operating_mode(hass: HomeAssistant, value: int, expected: str) -> None:
    """The fan shows auto mode when the operating mode is all ones."""
    fan = ComfoConnectFan(SimpleNamespace(uuid="test", is_available=True), SimpleNamespace())
    fan.hass = hass
    fan.entity_id = "fan.comfoairq"

    fan._handle_mode_update(value)

    assert fan.preset_mode == expected


@pytest.mark.parametrize(("value", "expected"), [(255, VentilationMode.AUTO), (1, VentilationMode.MANUAL), (5, VentilationMode.MANUAL)])
def test_ventilation_mode_select_follows_operating_mode(value: int, expected: str) -> None:
    """The ventilation mode select shows auto mode when the operating mode is all ones, and manual otherwise."""
    description = next(item for item in SELECT_TYPES if item.key == "select_mode")

    assert description.sensor_value_fn(value) == expected
