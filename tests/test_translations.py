"""Every entity is named through its translation key, in English and Dutch."""

from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from aiocomfoconnect.sensors import SENSOR_TEMPERATURE_EXTRACT
from custom_components.comfoconnect.binary_sensor import SENSOR_TYPES as BINARY_SENSOR_TYPES
from custom_components.comfoconnect.binary_sensor import ComfoConnectAlarmBinarySensor
from custom_components.comfoconnect.button import BUTTON_TYPES
from custom_components.comfoconnect.const import DOMAIN
from custom_components.comfoconnect.fan import PRESET_MODES, ComfoConnectFan
from custom_components.comfoconnect.number import NUMBER_TYPES
from custom_components.comfoconnect.select import SELECT_TYPES
from custom_components.comfoconnect.sensor import SENSOR_TYPES
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry
from tests.conftest import BRIDGE_UUID

COMPONENT = Path(__file__).parent.parent / "custom_components" / DOMAIN
# The translation keys hassfest accepts.
TRANSLATION_KEY = re.compile(r"^(?!.+[_-]{2})(?![_-])[a-z0-9-_]+(?<![_-])$")


def load(name: str) -> dict:
    """Return the entity translations of a translation file."""
    return json.loads((COMPONENT / name).read_text())["entity"]


@pytest.mark.parametrize("name", ["strings.json", "translations/en.json", "translations/nl.json"])
def test_every_entity_and_option_is_translated(name: str) -> None:
    """Each entity has a translated name, and each select option and enum state a translated state."""
    translations = load(name)
    bridge = SimpleNamespace(uuid="test", is_available=True, active_alarms={})
    descriptions = {
        "sensor": SENSOR_TYPES,
        "binary_sensor": BINARY_SENSOR_TYPES,
        "select": SELECT_TYPES,
        "number": NUMBER_TYPES,
        "button": BUTTON_TYPES,
    }
    for platform, items in descriptions.items():
        for description in items:
            assert translations[platform][description.translation_key]["name"]
            options = getattr(description, "options", None) or []
            assert all(TRANSLATION_KEY.match(option) for option in options)
            assert set(options) <= set(translations[platform][description.translation_key].get("state", {}))
    assert translations["binary_sensor"][ComfoConnectAlarmBinarySensor(bridge).translation_key]["name"]
    fan = translations["fan"][ComfoConnectFan(bridge, None).translation_key]
    assert set(fan["state_attributes"]["preset_mode"]["state"]) == set(PRESET_MODES)
    if name == "translations/en.json":
        assert translations == load("strings.json")


@pytest.fixture
def platforms() -> list[Platform]:
    """Set up only the sensor and button platforms."""
    return [Platform.SENSOR, Platform.BUTTON]


@pytest.fixture
def language(hass: HomeAssistant) -> str:
    """Run Home Assistant in English; a test overrides this for another language."""
    return "en"


@pytest.fixture
def in_language(hass: HomeAssistant, language: str) -> None:
    """Set the language of Home Assistant before the integration is set up."""
    hass.config.language = language


SENSOR_UNIQUE_ID = f"{BRIDGE_UUID}-{SENSOR_TEMPERATURE_EXTRACT}"
BUTTON_UNIQUE_ID = f"{BRIDGE_UUID}-cancel_boost"


async def test_english_names_give_the_same_entity_ids(
    hass: HomeAssistant, entity_registry: er.EntityRegistry, in_language: None, init_integration: MockConfigEntry
) -> None:
    """Test that the English names are the names the entities had before, so their entity ids don't change."""
    assert entity_registry.async_get_entity_id(Platform.SENSOR, DOMAIN, SENSOR_UNIQUE_ID) == "sensor.comfoairq_inside_temperature"
    assert entity_registry.async_get_entity_id(Platform.BUTTON, DOMAIN, BUTTON_UNIQUE_ID) == "button.comfoairq_cancel_boost"
    assert hass.states.get("button.comfoairq_cancel_boost").attributes["friendly_name"] == "ComfoAirQ Cancel boost"


@pytest.fixture
def registered_button(entity_registry: er.EntityRegistry) -> None:
    """Register the cancel boost button with the entity id it got in English."""
    entity_registry.async_get_or_create(Platform.BUTTON, DOMAIN, BUTTON_UNIQUE_ID, suggested_object_id="comfoairq_cancel_boost")


@pytest.mark.parametrize("language", ["nl"])
async def test_dutch_names_keep_registered_entity_ids(
    hass: HomeAssistant, entity_registry: er.EntityRegistry, in_language: None, registered_button: None, init_integration: MockConfigEntry
) -> None:
    """Test that the names are Dutch in Dutch, and that an entity that is already registered keeps its entity id."""
    assert hass.states.get("button.comfoairq_cancel_boost").attributes["friendly_name"] == "ComfoAirQ Boost annuleren"
    sensor = entity_registry.async_get_entity_id(Platform.SENSOR, DOMAIN, SENSOR_UNIQUE_ID)
    assert hass.states.get(sensor).attributes["friendly_name"] == "ComfoAirQ Binnentemperatuur"
