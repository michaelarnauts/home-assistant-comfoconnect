"""Library-decoded power and energy retain their values and native units in HA."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiocomfoconnect.bridge import Message
from aiocomfoconnect.protobuf import zehnder_pb2
from aiocomfoconnect.sensors import SENSOR_AVOIDED_COOLING, SENSOR_AVOIDED_HEATING, SENSOR_AVOIDED_HEATING_TOTAL, SENSOR_POWER_USAGE_TOTAL_YEAR
from custom_components.comfoconnect import ComfoConnectBridge
from custom_components.comfoconnect.sensor import SENSOR_TYPES, ComfoConnectSensor
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_setup as setup_loader


@pytest.mark.parametrize(
    "sensor_id,value,unit", [(SENSOR_AVOIDED_HEATING, 77, "W"), (SENSOR_AVOIDED_COOLING, 84, "W"), (SENSOR_POWER_USAGE_TOTAL_YEAR, 125, "kWh")]
)
def test_energy_measurements_preserve_library_units(tmp_path, sensor_id, value, unit):
    """In particular, already decoded watts must not be divided by 100 again."""

    async def scenario():
        hass = HomeAssistant(str(tmp_path))
        setup_loader(hass)
        bridge = SimpleNamespace(uuid="test", is_available=True)
        description = next(item for item in SENSOR_TYPES if item.key == sensor_id)
        entity = ComfoConnectSensor(bridge, SimpleNamespace(), description)
        entity.hass = hass
        entity.entity_id = f"sensor.energy_{sensor_id}"
        entity._handle_update(value)
        state = hass.states.get(entity.entity_id)
        assert state.state == str(value)
        assert state.attributes["unit_of_measurement"] == unit
        assert not entity.entity_registry_enabled_default

    asyncio.run(scenario())


def test_unsigned_energy_counter_reaches_ha_state(tmp_path):
    """A raw UINT16 counter above 32767 must remain positive in HA statistics."""

    async def scenario():
        hass = HomeAssistant(str(tmp_path))
        setup_loader(hass)
        uuid = "00000000000000000000000000000001"
        bridge = ComfoConnectBridge(hass, "127.0.0.1", uuid)
        bridge.sensor_delay = 0
        bridge._send = AsyncMock()
        description = next(item for item in SENSOR_TYPES if item.key == SENSOR_AVOIDED_HEATING_TOTAL)
        entity = ComfoConnectSensor(bridge, None, description)
        entity.hass = hass
        entity.entity_id = "sensor.unsigned_energy"
        await entity.async_added_to_hass()
        try:
            packet = Message(
                zehnder_pb2.GatewayOperation(type=zehnder_pb2.GatewayOperation.CnRpdoNotificationType),
                zehnder_pb2.CnRpdoNotification(pdid=SENSOR_AVOIDED_HEATING_TOTAL, data=b"\x00\x80"),
                uuid,
                uuid,
            ).encode()
            # Skip the length prefix, which the read loop strips.
            bridge._process_packet(packet[4:])
            await hass.async_block_till_done()
            state = hass.states.get(entity.entity_id)
            assert state.state == "32768"
            assert state.attributes["unit_of_measurement"] == "kWh"
            assert state.attributes["state_class"] == "total_increasing"
        finally:
            await entity.async_will_remove_from_hass()

    asyncio.run(scenario())
