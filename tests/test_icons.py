"""The icons live in icons.json, keyed by the entities' translation keys."""

import json
from pathlib import Path
from types import SimpleNamespace

from custom_components.comfoconnect.binary_sensor import SENSOR_TYPES as BINARY_SENSOR_TYPES
from custom_components.comfoconnect.binary_sensor import ComfoConnectAlarmBinarySensor
from custom_components.comfoconnect.button import BUTTON_TYPES
from custom_components.comfoconnect.fan import ComfoConnectFan
from custom_components.comfoconnect.number import NUMBER_TYPES
from custom_components.comfoconnect.select import SELECT_TYPES
from custom_components.comfoconnect.sensor import SENSOR_TYPES

ICONS = json.loads((Path(__file__).parent.parent / "custom_components" / "comfoconnect" / "icons.json").read_text())


def test_icons_belong_to_entities_and_not_to_the_code() -> None:
    """Every icon has an entity with its translation key, and no entity sets an icon in code."""
    bridge = SimpleNamespace(uuid="test", is_available=True, active_alarms={})
    descriptions = {
        "sensor": SENSOR_TYPES,
        "binary_sensor": BINARY_SENSOR_TYPES,
        "select": SELECT_TYPES,
        "number": NUMBER_TYPES,
        "button": BUTTON_TYPES,
    }
    keys = {platform: {description.translation_key for description in items} for platform, items in descriptions.items()}
    keys["binary_sensor"].add(ComfoConnectAlarmBinarySensor(bridge).translation_key)
    keys["fan"] = {ComfoConnectFan(bridge, None).translation_key}

    for platform, icons in ICONS["entity"].items():
        assert set(icons) <= keys[platform]
    assert all(description.icon is None for items in descriptions.values() for description in items)
    assert ComfoConnectFan(bridge, None).icon is None
    assert ICONS["services"]["start_boost"]["service"]
