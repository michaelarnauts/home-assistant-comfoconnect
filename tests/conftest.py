"""Pytest configuration."""

import sys
from collections.abc import Generator
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, PropertyMock, create_autospec, patch

import pytest
from aiocomfoconnect import Bridge, ComfoConnect
from aiocomfoconnect.comfoconnect import NodeInfo
from aiocomfoconnect.properties import (
    PROPERTY_PROFILE_TEMPERATURE_COOL,
    PROPERTY_PROFILE_TEMPERATURE_NORMAL,
    PROPERTY_PROFILE_TEMPERATURE_WARM,
    PROPERTY_RMOT_COOLING_THRESHOLD,
    PROPERTY_RMOT_HEATING_THRESHOLD,
    PROPERTY_SENSOR_VENTILATION_HUMIDITY_COMFORT,
    PROPERTY_SENSOR_VENTILATION_HUMIDITY_PROTECTION,
    PROPERTY_SENSOR_VENTILATION_TEMP_PASSIVE,
    PROPERTY_TEMPERATURE_PROFILE_MODE,
    Property,
    PropertyConstraints,
)
from aiocomfoconnect.sensors import SENSORS, Sensor
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import PlatformData
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.syrupy import HomeAssistantSnapshotExtension
from syrupy.assertion import SnapshotAssertion

# Make custom_components importable, since it isn't installed as a package.
sys.path.insert(0, str(Path(__file__).parent.parent))

from custom_components.comfoconnect import PLATFORMS
from custom_components.comfoconnect.const import CONF_LOCAL_UUID, CONF_UUID, DOMAIN
from tests.nodes import LAN_C, UNIT, announcing

HOST = "192.0.2.10"
BRIDGE_UUID = "00" * 16
LOCAL_UUID = "11" * 16

# What a ComfoAir Q450 behind a LAN C reports, as read from a real unit, decoded by the library.
NODE_INFO = {
    None: NodeInfo("ComfoAirQ", "ComfoAir Q450", "DEMO-ART-Q", "BEA0000000001", "R1.4.0", 3, 2),
    LAN_C.node_id: NodeInfo("ComfoConnect LAN C", None, None, "DEMO0001", "R1.5.1", 1, 0),
}
SENSOR_VALUES = {
    56: 255,  # Operating mode: auto
    65: 1,  # Fan speed
    66: 0,  # Bypass activation
    67: 0,  # Temperature profile
    117: 38,
    118: 35,
    119: 109,
    120: 108,
    121: 1464,
    122: 1325,
    128: 19,
    129: 167,
    130: 1376,
    144: 0,
    145: 0,
    146: 0,
    192: 90,
    209: 13.3,
    210: True,
    211: False,
    212: 23.0,
    213: 426,
    214: 2040,
    215: 9503,
    216: 0,
    217: 86,
    218: 528,
    221: 20.3,
    225: 1,
    227: 0,
    230: ["Bypass"],
    274: 20.1,
    275: 14.4,
    276: 13.0,
    278: 20.3,
    290: 61,
    291: 86,
    292: 82,
    293: 82,
    294: 64,
    337: 0,  # No preset timers
    369: 0.0,
    370: 0.0,
    371: 0.0,
    372: 0.0,
    401: 0,
    402: False,
    416: -40.0,
    417: 10.0,
    418: 0,
    419: False,
    784: 0,
    802: 0.0,
}
PROPERTY_VALUES = [
    (PROPERTY_TEMPERATURE_PROFILE_MODE, "adaptive"),
    (PROPERTY_SENSOR_VENTILATION_TEMP_PASSIVE, "auto"),
    (PROPERTY_SENSOR_VENTILATION_HUMIDITY_COMFORT, "off"),
    (PROPERTY_SENSOR_VENTILATION_HUMIDITY_PROTECTION, "auto"),
]
PROPERTY_CONSTRAINTS = [
    (PROPERTY_RMOT_HEATING_THRESHOLD, PropertyConstraints(15.0, 0.0, 15.0, 1.0)),
    (PROPERTY_RMOT_COOLING_THRESHOLD, PropertyConstraints(16.0, 15.0, 40.0, 1.0)),
    (PROPERTY_PROFILE_TEMPERATURE_WARM, PropertyConstraints(23.0, 23.0, 28.9, 1.0)),
    (PROPERTY_PROFILE_TEMPERATURE_NORMAL, PropertyConstraints(21.0, 18.9, 23.3, 1.0)),
    (PROPERTY_PROFILE_TEMPERATURE_COOL, PropertyConstraints(19.0, 17.8, 19.0, 1.0)),
]


@pytest.fixture(autouse=True)
def entity_platform_data(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Let tests write the state of entities they create without a platform.

    An entity with a translation key needs platform data for its name. Entities that a platform adds get their own.
    """
    monkeypatch.setattr(Entity, "platform_data", PlatformData(None, domain="test", platform_name="comfoconnect"))


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return the config entry of a registered bridge."""
    return MockConfigEntry(
        domain=DOMAIN,
        title=HOST,
        unique_id=BRIDGE_UUID,
        data={CONF_HOST: HOST, CONF_UUID: BRIDGE_UUID, CONF_LOCAL_UUID: LOCAL_UUID},
    )


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Don't set up the config entry that a flow creates, nor unload it."""
    with (
        patch("custom_components.comfoconnect.async_setup_entry", return_value=True) as setup_entry,
        patch("custom_components.comfoconnect.async_unload_entry", return_value=True),
    ):
        yield setup_entry


@pytest.fixture
def mock_bridge() -> Generator[MagicMock]:
    """Return the bridge that the config flow finds on the network, or creates itself for a reauth."""
    bridge = create_autospec(Bridge, instance=True)
    bridge.host = HOST
    bridge.uuid = BRIDGE_UUID
    with patch("custom_components.comfoconnect.config_flow.Bridge", return_value=bridge):
        yield bridge


@pytest.fixture
def mock_discover_bridges(mock_bridge: MagicMock) -> Generator[AsyncMock]:
    """Let the config flow discover the bridge."""
    with patch("custom_components.comfoconnect.config_flow.aiocomfoconnect.discover_bridges", return_value=[mock_bridge]) as discover_bridges:
        yield discover_bridges


@pytest.fixture
def mock_comfoconnect() -> Generator[dict[str, MagicMock]]:
    """
    Patch the library's session with a ComfoAir Q450 behind a LAN C, and return its mocked methods by name.

    The unit reports no alarms, and pushes the value of a sensor as soon as it's registered.
    """

    announce = announcing(UNIT, LAN_C)

    async def connect(self: ComfoConnect, uuid: str) -> None:
        await announce(self, uuid)
        # The unit reports its alarms when the session starts, here none.
        self._alarm_callback_fn(UNIT.node_id, {})

    async def get_node_info(self: ComfoConnect, node_id: int | None = None) -> NodeInfo:
        return NODE_INFO[node_id]

    async def register_sensor(self: ComfoConnect, sensor: Sensor) -> None:
        self._sensor_callback_fn(sensor, SENSOR_VALUES[sensor.id])

    async def get_property(self: ComfoConnect, prop: Property, node_id: int | None = None):
        # A Property can't be a dict key.
        return next(value for known, value in PROPERTY_VALUES if known == prop)

    async def get_property_constraints(self: ComfoConnect, prop: Property, node_id: int | None = None) -> PropertyConstraints:
        return next(constraints for known, constraints in PROPERTY_CONSTRAINTS if known == prop)

    # The value a method returns, or a function it runs instead; the setters return nothing.
    methods = {
        "connect": connect,
        "disconnect": None,
        "get_node_info": get_node_info,
        "register_sensor": register_sensor,
        "get_property": get_property,
        "get_property_constraints": get_property_constraints,
        "set_property": None,
        "get_mode": "auto",
        "set_mode": None,
        "set_speed": None,
        "get_boost": False,
        "set_boost": None,
        "get_away": False,
        "set_away": None,
        "get_bypass": "auto",
        "set_bypass": None,
        "get_balance_mode": "balance",
        "set_balance_mode": None,
        "get_comfocool_mode": "auto",
        "set_comfocool_mode": None,
        "get_temperature_profile": "normal",
        "set_temperature_profile": None,
        "clear_errors": None,
    }
    with ExitStack() as stack:
        mocks = {}
        for name, value in methods.items():
            mocks[name] = stack.enter_context(patch.object(ComfoConnect, name, autospec=True))
            if callable(value):
                mocks[name].side_effect = value
            else:
                mocks[name].return_value = value
        yield mocks


def push_sensor(entry: MockConfigEntry, sensor_id: int, value) -> None:
    """Push a sensor value from the unit, like the library does when the bridge sends one."""
    entry.runtime_data._sensor_callback_fn(SENSORS[sensor_id], value)


def push_alarms(entry: MockConfigEntry, node_id: int, errors: dict[int, str]) -> None:
    """Push the alarms of a node, like the library does when the bridge reports them."""
    entry.runtime_data._alarm_callback_fn(node_id, errors)


@pytest.fixture
def platforms() -> list[Platform]:
    """Return the platforms to set up; a test module overrides this to set up only its own."""
    return PLATFORMS


@pytest.fixture
async def init_integration(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    mock_config_entry: MockConfigEntry,
    mock_comfoconnect: dict[str, MagicMock],
    platforms: list[Platform],
) -> MockConfigEntry:
    """Set up the integration with the unit and the bridge on the bus."""
    mock_config_entry.add_to_hass(hass)
    with patch("custom_components.comfoconnect.PLATFORMS", platforms):
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()
    return mock_config_entry


@pytest.fixture
def entity_registry_enabled_by_default() -> Generator[None]:
    """Enable the entities that are disabled by default."""
    with patch("homeassistant.helpers.entity.Entity.entity_registry_enabled_default", return_value=True, new_callable=PropertyMock):
        yield


@pytest.fixture
def snapshot(snapshot: SnapshotAssertion) -> SnapshotAssertion:
    """
    Serialize snapshots like Home Assistant does, without the ids and timestamps that change on every run.

    pytest-homeassistant-custom-component has this fixture too, but syrupy's own takes precedence over it.
    """
    return snapshot.use_extension(HomeAssistantSnapshotExtension)
