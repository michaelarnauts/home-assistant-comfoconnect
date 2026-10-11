"""Unit diagnostics preserve the protocol library's decoded labels."""

from types import SimpleNamespace

import pytest
from aiocomfoconnect.sensors import SENSOR_UNIT_AIRFLOW, SENSOR_UNIT_TEMPERATURE, SENSORS
from custom_components.comfoconnect.sensor import SENSOR_TYPES, ComfoConnectSensor
from homeassistant.core import HomeAssistant


@pytest.mark.parametrize(
    "sensor_id,raw,expected",
    [
        (SENSOR_UNIT_TEMPERATURE, 0, "celsius"),
        (SENSOR_UNIT_TEMPERATURE, 1, "fahrenheit"),
        (SENSOR_UNIT_AIRFLOW, 1, "kgph"),
        (SENSOR_UNIT_AIRFLOW, 2, "lps"),
        (SENSOR_UNIT_AIRFLOW, 3, "m3ph"),
    ],
)
async def test_decoded_units_reach_ha(hass: HomeAssistant, sensor_id, raw, expected):
    """The library value reaches the disabled-by-default diagnostic state."""

    bridge = SimpleNamespace(uuid="test", is_available=True)
    description = next(item for item in SENSOR_TYPES if item.key == sensor_id)
    entity = ComfoConnectSensor(bridge, SimpleNamespace(), description)
    entity.hass = hass
    entity.entity_id = f"sensor.unit_{sensor_id}"
    entity._handle_update(SENSORS[sensor_id].value_fn(raw))
    assert hass.states.get(entity.entity_id).state == expected
    assert not entity.entity_registry_enabled_default
