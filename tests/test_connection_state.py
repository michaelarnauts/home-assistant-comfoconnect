"""Availability and reauthentication follow the connection state the library reports."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiocomfoconnect.sensors import SENSOR_CO2_1, SENSOR_COMFOCOOL_STATE, SENSOR_TEMPERATURE_EXTRACT
from custom_components.comfoconnect import SIGNAL_COMFOCONNECT_AVAILABILITY
from custom_components.comfoconnect.binary_sensor import SENSOR_TYPES as BINARY_SENSOR_TYPES
from custom_components.comfoconnect.binary_sensor import ComfoConnectAlarmBinarySensor, ComfoConnectBinarySensor
from custom_components.comfoconnect.button import BUTTON_TYPES, ComfoConnectButton
from custom_components.comfoconnect.fan import ComfoConnectFan
from custom_components.comfoconnect.select import SELECT_TYPES, ComfoConnectSelect
from custom_components.comfoconnect.sensor import SENSOR_TYPES, ComfoConnectCO2Sensor, ComfoConnectSensor
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send


def _entities(bridge):
    """Return one entity of each platform, and the CO2 sensor that has its own device."""
    entry = SimpleNamespace()
    return [
        ComfoConnectSensor(bridge, entry, next(item for item in SENSOR_TYPES if item.key == SENSOR_TEMPERATURE_EXTRACT)),
        ComfoConnectCO2Sensor(bridge, entry, "DEMO0007", SENSOR_CO2_1),
        ComfoConnectBinarySensor(bridge, entry, next(item for item in BINARY_SENSOR_TYPES if item.key == SENSOR_COMFOCOOL_STATE)),
        ComfoConnectAlarmBinarySensor(bridge),
        ComfoConnectSelect(bridge, entry, next(item for item in SELECT_TYPES if item.key == "balance_mode")),
        ComfoConnectButton(bridge, entry, next(item for item in BUTTON_TYPES if item.key == "cancel_boost")),
        ComfoConnectFan(bridge, entry),
    ]


async def test_co2_sensor_follows_its_node(hass: HomeAssistant) -> None:
    """A CO2 sensor is unavailable while its node isn't on the bus, also when the bridge is."""
    on_bus = {"DEMO0007": True}
    bridge = SimpleNamespace(uuid="test", is_available=True, register_sensor=AsyncMock(), is_on_bus=on_bus.get)
    entity = ComfoConnectCO2Sensor(bridge, SimpleNamespace(), "DEMO0007", SENSOR_CO2_1)
    entity.hass = hass
    entity.entity_id = "sensor.co2"
    await entity.async_added_to_hass()

    on_bus["DEMO0007"] = False
    async_dispatcher_send(hass, SIGNAL_COMFOCONNECT_AVAILABILITY.format("test"), True)
    assert hass.states.get("sensor.co2").state == STATE_UNAVAILABLE

    on_bus["DEMO0007"] = True
    async_dispatcher_send(hass, SIGNAL_COMFOCONNECT_AVAILABILITY.format("test"), True)
    assert hass.states.get("sensor.co2").state != STATE_UNAVAILABLE


def test_entities_keep_their_unique_id_and_device() -> None:
    """The unit's entities stay on the unit's device, the CO2 sensor on its own."""
    bridge = SimpleNamespace(uuid="test", is_available=True, active_alarms={})
    unique_ids = [entity.unique_id for entity in _entities(bridge)]
    assert unique_ids == ["test-274", "DEMO0007-co2", "test-784", "test-active_alarms", "test-balance_mode", "test-cancel_boost", "test"]
    devices = [entity.device_info["identifiers"] for entity in _entities(bridge)]
    assert devices == [{("comfoconnect", "test")}] + [{("comfoconnect", "DEMO0007")}] + [{("comfoconnect", "test")}] * 5
