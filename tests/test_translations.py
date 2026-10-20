"""Every entity is named through its translation key, in English and Dutch."""

from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from aiocomfoconnect.comfoconnect import NodeInfo
from aiocomfoconnect.sensors import SENSOR_TEMPERATURE_EXTRACT
from custom_components.comfoconnect.binary_sensor import SENSOR_TYPES as BINARY_SENSOR_TYPES
from custom_components.comfoconnect.binary_sensor import ComfoConnectAlarmBinarySensor
from custom_components.comfoconnect.button import BUTTON_TYPES
from custom_components.comfoconnect.const import CONF_LOCAL_UUID, CONF_UUID, DOMAIN
from custom_components.comfoconnect.fan import PRESET_MODES, ComfoConnectFan
from custom_components.comfoconnect.number import NUMBER_TYPES
from custom_components.comfoconnect.select import SELECT_TYPES
from custom_components.comfoconnect.sensor import SENSOR_TYPES
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from tests.nodes import UNIT, announcing

MockConfigEntry = pytest.importorskip("pytest_homeassistant_custom_component.common").MockConfigEntry

COMPONENT = Path(__file__).parent.parent / "custom_components" / DOMAIN
# The translation keys hassfest accepts.
TRANSLATION_KEY = re.compile(r"^(?!.+[_-]{2})(?![_-])[a-z0-9-_]+(?<![_-])$")
BRIDGE = "custom_components.comfoconnect.ComfoConnectBridge"
UNIT_UUID = "00" * 16


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


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load the integration from custom_components."""
    return


async def setup(hass: HomeAssistant, language: str) -> MockConfigEntry:
    """Set up the sensor and button platforms with Home Assistant in a language."""
    hass.config.language = language
    entry = MockConfigEntry(domain=DOMAIN, title="192.0.2.10", data={CONF_HOST: "192.0.2.10", CONF_UUID: UNIT_UUID, CONF_LOCAL_UUID: "11" * 16})
    entry.add_to_hass(hass)
    with (
        patch("custom_components.comfoconnect.PLATFORMS", [Platform.SENSOR, Platform.BUTTON]),
        patch(f"{BRIDGE}.connect", autospec=True, side_effect=announcing(UNIT)),
        patch(f"{BRIDGE}.disconnect", new_callable=AsyncMock),
        patch(f"{BRIDGE}.get_node_info", new_callable=AsyncMock, return_value=NodeInfo("ComfoAirQ", None, None, None, None, None, None)),
        patch(f"{BRIDGE}.register_sensor", new_callable=AsyncMock),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


SENSOR_UNIQUE_ID = f"{UNIT_UUID}-{SENSOR_TEMPERATURE_EXTRACT}"
BUTTON_UNIQUE_ID = f"{UNIT_UUID}-cancel_boost"


async def test_english_names_give_the_same_entity_ids(hass: HomeAssistant) -> None:
    """The English names are the names the entities had before, so their entity ids don't change."""
    await setup(hass, "en")
    registry = er.async_get(hass)
    assert registry.async_get_entity_id(Platform.SENSOR, DOMAIN, SENSOR_UNIQUE_ID) == "sensor.comfoairq_inside_temperature"
    assert registry.async_get_entity_id(Platform.BUTTON, DOMAIN, BUTTON_UNIQUE_ID) == "button.comfoairq_cancel_boost"
    assert hass.states.get("button.comfoairq_cancel_boost").attributes["friendly_name"] == "ComfoAirQ Cancel boost"


async def test_dutch_names_keep_registered_entity_ids(hass: HomeAssistant) -> None:
    """In Dutch the names are Dutch; an entity that is already registered keeps its entity id."""
    er.async_get(hass).async_get_or_create(Platform.BUTTON, DOMAIN, BUTTON_UNIQUE_ID, suggested_object_id="comfoairq_cancel_boost")
    await setup(hass, "nl")
    assert hass.states.get("button.comfoairq_cancel_boost").attributes["friendly_name"] == "ComfoAirQ Boost annuleren"
    sensor = er.async_get(hass).async_get_entity_id(Platform.SENSOR, DOMAIN, SENSOR_UNIQUE_ID)
    assert hass.states.get(sensor).attributes["friendly_name"] == "ComfoAirQ Binnentemperatuur"
