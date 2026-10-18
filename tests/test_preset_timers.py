"""Boost and Away follow the pushed bit set of running preset timers instead of polling."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiocomfoconnect.sensors import SENSOR_PRESET_TIMERS
from custom_components.comfoconnect.select import SELECT_TYPES, ComfoConnectSelect
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_setup as setup_loader


@pytest.mark.parametrize(
    ("value", "boost", "away"),
    [(0, "Off", "Off"), (64, "Active", "Off"), (2048, "Off", "Active"), (2112, "Active", "Active")],
)
def test_boost_and_away_follow_the_pushed_timers(tmp_path, value: int, boost: str, away: str) -> None:
    """Bit 6 of PDO 337 is the boost timer and bit 11 the away timer."""

    async def scenario():
        hass = HomeAssistant(str(tmp_path))
        setup_loader(hass)
        bridge = SimpleNamespace(uuid="test", is_available=True, get_boost=AsyncMock(), get_away=AsyncMock())
        for key, expected in (("boost_timeout", boost), ("away_timeout", away)):
            description = next(item for item in SELECT_TYPES if item.key == key)
            entity = ComfoConnectSelect(bridge, SimpleNamespace(), description)
            entity.hass = hass
            entity.entity_id = f"select.{key}"

            assert entity.should_poll is False
            assert description.sensor.id == SENSOR_PRESET_TIMERS

            entity._handle_update(value)
            assert hass.states.get(entity.entity_id).state == expected

        bridge.get_boost.assert_not_awaited()
        bridge.get_away.assert_not_awaited()

    asyncio.run(scenario())
