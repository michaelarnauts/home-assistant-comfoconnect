"""The analog inputs are opt-in, since most installations don't use them."""

import pytest
from aiocomfoconnect.sensors import SENSOR_ANALOG_INPUT_1, SENSOR_ANALOG_INPUT_2, SENSOR_ANALOG_INPUT_3, SENSOR_ANALOG_INPUT_4
from custom_components.comfoconnect.sensor import SENSOR_TYPES


@pytest.mark.parametrize("key", [SENSOR_ANALOG_INPUT_1, SENSOR_ANALOG_INPUT_2, SENSOR_ANALOG_INPUT_3, SENSOR_ANALOG_INPUT_4])
def test_analog_inputs_are_disabled_by_default(key: int) -> None:
    """Each enabled sensor is a subscription on the bridge, so unused inputs stay off."""
    description = next(item for item in SENSOR_TYPES if item.key == key)
    assert description.entity_registry_enabled_default is False
