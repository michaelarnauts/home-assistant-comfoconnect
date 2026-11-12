"""Calculated moisture sensors use each stream's own bridge readings."""

import asyncio

import pytest
from aiocomfoconnect.const import ConnectionState
from aiocomfoconnect.sensors import (
    SENSOR_HUMIDITY_EXHAUST,
    SENSOR_HUMIDITY_EXTRACT,
    SENSOR_HUMIDITY_OUTDOOR,
    SENSOR_HUMIDITY_SUPPLY,
    SENSOR_TEMPERATURE_EXHAUST,
    SENSOR_TEMPERATURE_EXTRACT,
    SENSOR_TEMPERATURE_OUTDOOR,
    SENSOR_TEMPERATURE_SUPPLY,
    SENSORS,
)
from custom_components.comfoconnect import SIGNAL_COMFOCONNECT_UPDATE_RECEIVED, ComfoConnectBridge
from custom_components.comfoconnect.const import DOMAIN
from custom_components.comfoconnect.sensor import CALCULATED_SENSOR_TYPES, ComfoConnectCalculatedSensor
from homeassistant.const import STATE_UNAVAILABLE, Platform, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from pytest_homeassistant_custom_component.common import MockConfigEntry
from tests.conftest import BRIDGE_UUID, HOST, push_sensor, set_connection_state

STREAMS = [
    ("outside", SENSOR_TEMPERATURE_OUTDOOR, SENSOR_HUMIDITY_OUTDOOR),
    ("supply", SENSOR_TEMPERATURE_SUPPLY, SENSOR_HUMIDITY_SUPPLY),
    ("inside", SENSOR_TEMPERATURE_EXTRACT, SENSOR_HUMIDITY_EXTRACT),
    ("exhaust", SENSOR_TEMPERATURE_EXHAUST, SENSOR_HUMIDITY_EXHAUST),
]


@pytest.fixture
def platforms() -> list[Platform]:
    """Set up only sensors."""
    return [Platform.SENSOR]


@pytest.mark.parametrize(("stream", "temperature_id", "humidity_id"), STREAMS)
async def test_calculated_stream(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    init_integration: MockConfigEntry,
    stream: str,
    temperature_id: int,
    humidity_id: int,
) -> None:
    """Both readings update the right stream, with stable IDs and measurement metadata."""
    other_states = {name: hass.states.get(f"sensor.comfoairq_{name}_dew_point").state for name, _, _ in STREAMS if name != stream}
    push_sensor(init_integration, temperature_id, 20.0)
    push_sensor(init_integration, humidity_id, 50)
    await hass.async_block_till_done()

    for measurement, expected, unit, device_class in (
        ("dew_point", 9.26, "°C", "temperature"),
        ("absolute_humidity", 8.62, "g/m³", "absolute_humidity"),
    ):
        entity_id = f"sensor.comfoairq_{stream}_{measurement}"
        state = hass.states.get(entity_id)
        assert float(state.state) == pytest.approx(expected, abs=0.01)
        assert state.attributes["unit_of_measurement"] == unit
        assert state.attributes["device_class"] == device_class
        assert state.attributes["state_class"] == "measurement"
        entry = entity_registry.async_get(entity_id)
        assert entry.unique_id == f"{BRIDGE_UUID}-{stream}_{measurement}"
        assert entry.device_id == entity_registry.async_get("sensor.comfoairq_inside_temperature").device_id

    push_sensor(init_integration, humidity_id, 100)
    await hass.async_block_till_done()
    assert float(hass.states.get(f"sensor.comfoairq_{stream}_dew_point").state) == pytest.approx(20)
    push_sensor(init_integration, temperature_id, 0)
    await hass.async_block_till_done()
    assert float(hass.states.get(f"sensor.comfoairq_{stream}_dew_point").state) == pytest.approx(0)
    assert float(hass.states.get(f"sensor.comfoairq_{stream}_absolute_humidity").state) == pytest.approx(4.85, abs=0.01)
    push_sensor(init_integration, temperature_id, -10)
    await hass.async_block_till_done()
    assert float(hass.states.get(f"sensor.comfoairq_{stream}_dew_point").state) == pytest.approx(-10)
    for name, state in other_states.items():
        assert hass.states.get(f"sensor.comfoairq_{name}_dew_point").state == state


@pytest.mark.parametrize(
    ("sensor_id", "value"),
    [
        (SENSOR_HUMIDITY_EXTRACT, None),
        (SENSOR_HUMIDITY_EXTRACT, -1),
        (SENSOR_HUMIDITY_EXTRACT, 101),
        (SENSOR_HUMIDITY_EXTRACT, float("nan")),
        (SENSOR_HUMIDITY_EXTRACT, float("inf")),
        (SENSOR_TEMPERATURE_EXTRACT, None),
        (SENSOR_TEMPERATURE_EXTRACT, float("nan")),
        (SENSOR_TEMPERATURE_EXTRACT, float("inf")),
        (SENSOR_TEMPERATURE_EXTRACT, -46),
        (SENSOR_TEMPERATURE_EXTRACT, 61),
    ],
)
async def test_invalid_inputs(hass: HomeAssistant, init_integration: MockConfigEntry, sensor_id: int, value: float | None) -> None:
    """Invalid inputs clear the calculated value; a valid reading restores it."""
    push_sensor(init_integration, sensor_id, value)
    await hass.async_block_till_done()
    for measurement in ("dew_point", "absolute_humidity"):
        assert hass.states.get(f"sensor.comfoairq_inside_{measurement}").state == STATE_UNAVAILABLE
    push_sensor(init_integration, sensor_id, 50 if sensor_id == SENSOR_HUMIDITY_EXTRACT else 20)
    await hass.async_block_till_done()
    for measurement in ("dew_point", "absolute_humidity"):
        assert hass.states.get(f"sensor.comfoairq_inside_{measurement}").state != STATE_UNAVAILABLE


async def test_zero_humidity_and_session(hass: HomeAssistant, init_integration: MockConfigEntry) -> None:
    """Dry air has zero absolute humidity and no finite dew point; disconnects make both unavailable."""
    push_sensor(init_integration, SENSOR_HUMIDITY_EXTRACT, 0)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.comfoairq_inside_dew_point").state == STATE_UNAVAILABLE
    assert float(hass.states.get("sensor.comfoairq_inside_absolute_humidity").state) == 0
    push_sensor(init_integration, SENSOR_HUMIDITY_EXTRACT, 50)
    set_connection_state(init_integration, ConnectionState.DISCONNECTED)
    await hass.async_block_till_done()
    for measurement in ("dew_point", "absolute_humidity"):
        assert hass.states.get(f"sensor.comfoairq_inside_{measurement}").state == STATE_UNAVAILABLE
    set_connection_state(init_integration, ConnectionState.CONNECTED)
    await hass.async_block_till_done()
    for measurement in ("dew_point", "absolute_humidity"):
        assert hass.states.get(f"sensor.comfoairq_inside_{measurement}").state == STATE_UNAVAILABLE
    push_sensor(init_integration, SENSOR_TEMPERATURE_EXTRACT, 30)
    await hass.async_block_till_done()
    for measurement in ("dew_point", "absolute_humidity"):
        assert hass.states.get(f"sensor.comfoairq_inside_{measurement}").state == STATE_UNAVAILABLE
    push_sensor(init_integration, SENSOR_HUMIDITY_EXTRACT, 100)
    await hass.async_block_till_done()
    assert float(hass.states.get("sensor.comfoairq_inside_dew_point").state) == pytest.approx(30)
    assert float(hass.states.get("sensor.comfoairq_inside_absolute_humidity").state) == pytest.approx(30.26, abs=0.02)


async def test_waits_for_both_inputs(init_integration: MockConfigEntry) -> None:
    """A new calculated entity has no value until both inputs have arrived."""
    sensor = ComfoConnectCalculatedSensor(init_integration.runtime_data, CALCULATED_SENSOR_TYPES[0])
    assert not sensor.available
    assert sensor.native_value is None


async def test_temperature_unit_conversion(hass: HomeAssistant, entity_registry: er.EntityRegistry, init_integration: MockConfigEntry) -> None:
    """Home Assistant converts dew point to the user's selected temperature unit."""
    entity_registry.async_update_entity_options("sensor.comfoairq_inside_dew_point", "sensor", {"unit_of_measurement": UnitOfTemperature.FAHRENHEIT})
    push_sensor(init_integration, SENSOR_TEMPERATURE_EXTRACT, 20)
    push_sensor(init_integration, SENSOR_HUMIDITY_EXTRACT, 100)
    await hass.async_block_till_done()
    state = hass.states.get("sensor.comfoairq_inside_dew_point")
    assert state.attributes["unit_of_measurement"] == "°F"
    assert float(state.state) == pytest.approx(68)


class RecordingBridge(ComfoConnectBridge):
    """Use the real library registration with a local RPDO transport."""

    async def cmd_rpdo_request(self, pdid: int, pdo_type: int = 1, zone: int = 1, timeout=None):
        """Record the subscription and deliver a real raw temperature notification."""
        self.requests.append(pdid)
        self._sensor_callback(pdid, 200)


async def test_shared_subscription(hass: HomeAssistant, mock_config_entry: MockConfigEntry) -> None:
    """Concurrent and later listeners reuse the subscription and receive its cached value."""
    bridge = RecordingBridge(hass, mock_config_entry, HOST)
    bridge.requests = []
    readings = []

    @callback
    def record(value):
        readings.append(value)

    unsubscribe = async_dispatcher_connect(hass, SIGNAL_COMFOCONNECT_UPDATE_RECEIVED.format(BRIDGE_UUID, SENSOR_TEMPERATURE_EXTRACT), record)
    try:
        sensor = SENSORS[SENSOR_TEMPERATURE_EXTRACT]
        await asyncio.gather(*(bridge.async_register_sensor_once(sensor) for _ in range(3)))
        await hass.async_block_till_done()
        assert bridge.requests == [SENSOR_TEMPERATURE_EXTRACT]
        assert readings and set(readings) == {20.0}
        readings.clear()
        await bridge.async_register_sensor_once(sensor)
        await hass.async_block_till_done()
        assert readings == [20.0]
        assert bridge.requests == [SENSOR_TEMPERATURE_EXTRACT]

        bridge.set_available(False)
        bridge.set_available(True)
        readings.clear()
        await bridge.async_register_sensor_once(sensor)
        await hass.async_block_till_done()
        assert readings == []
        assert bridge.requests == [SENSOR_TEMPERATURE_EXTRACT]
    finally:
        unsubscribe()


@pytest.fixture
def disabled_input_entities(entity_registry: er.EntityRegistry) -> None:
    """Disable every standalone temperature and humidity input before setup."""
    for stream, temperature_id, humidity_id in STREAMS:
        for sensor_id, measurement in ((temperature_id, "temperature"), (humidity_id, "humidity")):
            entity_registry.async_get_or_create(
                Platform.SENSOR,
                DOMAIN,
                f"{BRIDGE_UUID}-{sensor_id}",
                suggested_object_id=f"comfoairq_{stream}_{measurement}",
                disabled_by=er.RegistryEntryDisabler.USER,
            )


async def test_disabled_inputs(hass: HomeAssistant, disabled_input_entities: None, init_integration: MockConfigEntry) -> None:
    """Calculated sensors subscribe to their inputs even when standalone entities are disabled."""
    for stream, temperature_id, humidity_id in STREAMS:
        assert hass.states.get(f"sensor.comfoairq_{stream}_temperature") is None
        assert hass.states.get(f"sensor.comfoairq_{stream}_humidity") is None
        assert hass.states.get(f"sensor.comfoairq_{stream}_dew_point").state != STATE_UNAVAILABLE
        assert hass.states.get(f"sensor.comfoairq_{stream}_absolute_humidity").state != STATE_UNAVAILABLE
        push_sensor(init_integration, temperature_id, 20)
        push_sensor(init_integration, humidity_id, 50)
    await hass.async_block_till_done()
    for stream, _, _ in STREAMS:
        assert float(hass.states.get(f"sensor.comfoairq_{stream}_dew_point").state) == pytest.approx(9.26, abs=0.01)
        assert float(hass.states.get(f"sensor.comfoairq_{stream}_absolute_humidity").state) == pytest.approx(8.62, abs=0.01)
