"""The preheater humidity measurement reaches Home Assistant without changing device settings."""

from types import SimpleNamespace

from aiocomfoconnect.sensors import SENSOR_HUMIDITY_AFTER_PREHEATER
from custom_components.comfoconnect.sensor import SENSOR_TYPES, ComfoConnectSensor
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory


async def test_preheater_humidity_measurement(hass: HomeAssistant) -> None:
    """Expose a percentage with the humidity class and opt-in diagnostic presentation."""
    description = next(item for item in SENSOR_TYPES if item.key == SENSOR_HUMIDITY_AFTER_PREHEATER)
    entity = ComfoConnectSensor(SimpleNamespace(uuid="test", is_available=True), SimpleNamespace(), description)
    entity.hass = hass
    entity.entity_id = "sensor.outside_humidity_after_preheater"
    entity._handle_update(50)

    state = hass.states.get(entity.entity_id)
    assert state.state == "50"
    assert state.attributes["device_class"] == SensorDeviceClass.HUMIDITY
    assert state.attributes["state_class"] == SensorStateClass.MEASUREMENT
    assert state.attributes["unit_of_measurement"] == "%"
    assert entity.name == "Outside humidity after preheater"
    assert entity.entity_category == EntityCategory.DIAGNOSTIC
    assert not entity.entity_registry_enabled_default
