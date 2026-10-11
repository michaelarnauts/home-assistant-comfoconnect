"""Schedule countdowns do not expose protocol sentinels as multi-year durations."""

import asyncio
from types import SimpleNamespace

import pytest
from aiocomfoconnect.sensors import SENSOR_NEXT_CHANGE_BYPASS, SENSOR_NEXT_CHANGE_FAN, SENSOR_NEXT_CHANGE_FAN_EXHAUST, SENSOR_NEXT_CHANGE_FAN_SUPPLY
from custom_components.comfoconnect.sensor import SENSOR_TYPES, ComfoConnectSensor
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_setup as setup_loader


@pytest.mark.parametrize(
    "sensor_id", [SENSOR_NEXT_CHANGE_FAN, SENSOR_NEXT_CHANGE_BYPASS, SENSOR_NEXT_CHANGE_FAN_SUPPLY, SENSOR_NEXT_CHANGE_FAN_EXHAUST]
)
def test_countdown_seconds_and_no_change_sentinels(tmp_path, sensor_id):
    """Real HA states distinguish a countdown from no scheduled change."""

    async def scenario():
        hass = HomeAssistant(str(tmp_path))
        setup_loader(hass)
        bridge = SimpleNamespace(uuid="test", is_available=True)
        description = next(item for item in SENSOR_TYPES if item.key == sensor_id)
        entity = ComfoConnectSensor(bridge, SimpleNamespace(), description)
        entity.hass = hass
        entity.entity_id = f"sensor.countdown_{sensor_id}"
        entity._handle_update(120)
        assert hass.states.get(entity.entity_id).state == "120"
        assert hass.states.get(entity.entity_id).attributes["unit_of_measurement"] == "s"
        for value in (-1, 0xFFFFFFFF):
            entity._handle_update(value)
            assert hass.states.get(entity.entity_id).state == "unknown"

    asyncio.run(scenario())
