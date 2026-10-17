"""The comfort temperature the unit is aiming for is exposed as a diagnostic sensor."""

import asyncio
from types import SimpleNamespace

from aiocomfoconnect.sensors import SENSOR_TARGET_TEMPERATURE
from custom_components.comfoconnect.sensor import SENSOR_TYPES, ComfoConnectSensor
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_setup as setup_loader


def test_target_temperature_reports_the_decoded_value(tmp_path):
    """The library already decodes PDO 212 to °C, so HA must not rescale it."""

    async def scenario():
        hass = HomeAssistant(str(tmp_path))
        setup_loader(hass)
        bridge = SimpleNamespace(uuid="test", is_available=True)
        description = next(item for item in SENSOR_TYPES if item.key == SENSOR_TARGET_TEMPERATURE)
        entity = ComfoConnectSensor(bridge, SimpleNamespace(), description)
        entity.hass = hass
        entity.entity_id = "sensor.target_temperature"
        entity._handle_update(23.2)
        current = hass.states.get(entity.entity_id)
        assert current.state == "23.2"
        assert current.attributes["unit_of_measurement"] == "°C"
        assert description.entity_registry_enabled_default is False
        assert description.entity_category == EntityCategory.DIAGNOSTIC

    asyncio.run(scenario())
