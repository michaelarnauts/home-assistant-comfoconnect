"""Sensor ventilation selects read and write their library property."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiocomfoconnect.properties import (
    PROPERTY_SENSOR_VENTILATION_HUMIDITY_COMFORT,
    PROPERTY_SENSOR_VENTILATION_HUMIDITY_PROTECTION,
    PROPERTY_SENSOR_VENTILATION_TEMP_PASSIVE,
)
from custom_components.comfoconnect.select import SELECT_TYPES, ComfoConnectSelect
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_setup as setup_loader


@pytest.mark.parametrize(
    "mode,prop",
    [
        ("temperature_passive", PROPERTY_SENSOR_VENTILATION_TEMP_PASSIVE),
        ("humidity_comfort", PROPERTY_SENSOR_VENTILATION_HUMIDITY_COMFORT),
        ("humidity_protection", PROPERTY_SENSOR_VENTILATION_HUMIDITY_PROTECTION),
    ],
)
def test_sensor_ventilation_reads_and_writes_its_own_mode(tmp_path, mode, prop):
    """Each exposed select controls the matching library property."""

    async def scenario():
        hass = HomeAssistant(str(tmp_path))
        setup_loader(hass)
        bridge = SimpleNamespace(uuid="test", is_available=True, get_property=AsyncMock(return_value="auto"), set_property=AsyncMock())
        description = next(item for item in SELECT_TYPES if item.key == f"sensor_ventmode_{mode}")
        entity = ComfoConnectSelect(bridge, SimpleNamespace(), description)
        entity.hass = hass
        entity.entity_id = f"select.{mode}"
        await entity.async_update()
        assert entity.current_option == "auto"
        bridge.get_property.assert_awaited_once_with(prop)
        assert set(entity.options) == {"auto", "on", "off"}
        await entity.async_select_option("off")
        bridge.set_property.assert_awaited_once_with(prop, "off")
        assert hass.states.get(entity.entity_id).state == "off"

    asyncio.run(scenario())
