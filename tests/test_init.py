"""Test setting up the integration."""

import asyncio
from collections.abc import Generator
from datetime import timedelta
from ipaddress import IPv4Address
from unittest.mock import MagicMock, patch

import pytest
from aiocomfoconnect import Bridge, ComfoConnect
from aiocomfoconnect.const import ConnectionState
from aiocomfoconnect.exceptions import (
    AioComfoConnectNotConnected,
    AioComfoConnectNotReachable,
    AioComfoConnectTimeout,
    ComfoConnectNotAllowed,
    ComfoConnectOtherSession,
    ComfoConnectRmiError,
    VentilationUnitNotFoundException,
)
from custom_components.comfoconnect.const import CONF_LOCAL_UUID, CONF_UUID, DOMAIN
from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import SOURCE_IMPORT, SOURCE_REAUTH, ConfigEntryState
from homeassistant.const import CONF_HOST, EVENT_HOMEASSISTANT_STOP, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed
from syrupy.assertion import SnapshotAssertion
from tests.conftest import BRIDGE_UUID, HOST, LOCAL_UUID, set_connection_state
from tests.nodes import LAN_C, UNIT, announcing

NEW_HOST = "192.0.2.20"


@pytest.fixture
def mock_rediscover() -> Generator[MagicMock]:
    """Find the bridge again at another address, when looking on the networks of Home Assistant."""
    with (
        patch("custom_components.comfoconnect.network.async_get_ipv4_broadcast_addresses", return_value={IPv4Address("192.0.2.255")}),
        patch("custom_components.comfoconnect.discover_bridges", return_value=[Bridge(NEW_HOST, BRIDGE_UUID)]) as discover_bridges,
    ):
        yield discover_bridges


async def setup_entry(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Set up the config entry, whether that works or not."""
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_setup_and_unload(hass: HomeAssistant, mock_comfoconnect: dict[str, MagicMock], init_integration: MockConfigEntry) -> None:
    """Test that the entry is loaded with a session, and that unloading closes the session."""
    assert init_integration.state is ConfigEntryState.LOADED
    mock_comfoconnect["connect"].assert_awaited_once()
    assert mock_comfoconnect["connect"].await_args.args[1] == LOCAL_UUID

    assert await hass.config_entries.async_unload(init_integration.entry_id)
    await hass.async_block_till_done()

    assert init_integration.state is ConfigEntryState.NOT_LOADED
    mock_comfoconnect["disconnect"].assert_awaited_once()


async def test_stop_closes_the_session(hass: HomeAssistant, mock_comfoconnect: dict[str, MagicMock], init_integration: MockConfigEntry) -> None:
    """Test that stopping Home Assistant closes the session."""
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)
    await hass.async_block_till_done()

    mock_comfoconnect["disconnect"].assert_awaited_once()


@pytest.mark.parametrize(
    "error",
    [
        VentilationUnitNotFoundException("No ventilation unit"),
        AioComfoConnectNotConnected("Connection closed"),
        ComfoConnectOtherSession("The app has the session"),
    ],
)
async def test_setup_retry(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    mock_config_entry: MockConfigEntry,
    mock_comfoconnect: dict[str, MagicMock],
    error: Exception,
) -> None:
    """Test that a bridge without a unit yet, a dropped connection or a session the app has, is tried again later."""
    mock_comfoconnect["connect"].side_effect = error

    await setup_entry(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_setup_not_allowed(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    mock_config_entry: MockConfigEntry,
    mock_comfoconnect: dict[str, MagicMock],
    mock_bridge: MagicMock,
) -> None:
    """Test that a bridge that doesn't know us anymore asks to register again."""
    mock_comfoconnect["connect"].side_effect = ComfoConnectNotAllowed("Not registered")
    mock_bridge.register.side_effect = ComfoConnectNotAllowed("Wrong PIN")

    await setup_entry(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.SETUP_ERROR
    [flow] = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert flow["context"]["source"] == SOURCE_REAUTH
    assert flow["step_id"] == "enter_pin"


@pytest.mark.parametrize("error", [ComfoConnectRmiError("Busy"), AioComfoConnectTimeout("Timed out")])
async def test_setup_unit_info_failed(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    mock_config_entry: MockConfigEntry,
    mock_comfoconnect: dict[str, MagicMock],
    error: Exception,
) -> None:
    """Test that a unit that doesn't tell about itself is tried again later, without leaving its session open."""
    mock_comfoconnect["get_node_info"].side_effect = error

    await setup_entry(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY
    mock_comfoconnect["disconnect"].assert_awaited_once()


async def test_setup_cancelled(
    hass: HomeAssistant, enable_custom_integrations: None, mock_config_entry: MockConfigEntry, mock_comfoconnect: dict[str, MagicMock]
) -> None:
    """Test that a setup that's stopped while it reads the unit doesn't leave its session open."""
    mock_comfoconnect["get_node_info"].side_effect = asyncio.CancelledError

    await setup_entry(hass, mock_config_entry)

    assert mock_config_entry.state is not ConfigEntryState.LOADED
    mock_comfoconnect["disconnect"].assert_awaited_once()


async def test_setup_cancelled_while_adding_the_devices(
    hass: HomeAssistant, enable_custom_integrations: None, mock_config_entry: MockConfigEntry, mock_comfoconnect: dict[str, MagicMock]
) -> None:
    """Test that a setup that's stopped while it reads the other nodes doesn't leave its session open."""
    unit_info = mock_comfoconnect["get_node_info"].side_effect

    async def get_node_info(bridge: ComfoConnect, node_id: int | None = None):
        if node_id == LAN_C.node_id:
            raise asyncio.CancelledError
        return await unit_info(bridge, node_id)

    mock_comfoconnect["get_node_info"].side_effect = get_node_info

    await setup_entry(hass, mock_config_entry)

    assert mock_config_entry.state is not ConfigEntryState.LOADED
    mock_comfoconnect["disconnect"].assert_awaited_once()


@pytest.mark.parametrize("error", [AioComfoConnectTimeout("Timed out"), AioComfoConnectNotReachable("Unreachable")])
async def test_setup_finds_the_bridge_again(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    mock_config_entry: MockConfigEntry,
    mock_comfoconnect: dict[str, MagicMock],
    mock_rediscover: MagicMock,
    error: Exception,
) -> None:
    """Test that a bridge that can't be reached is looked for on the network, and that its new address is kept."""
    announce = announcing(UNIT, LAN_C)

    async def connect(bridge: ComfoConnect, uuid: str) -> None:
        if bridge.host == HOST:
            raise error
        await announce(bridge, uuid)

    mock_comfoconnect["connect"].side_effect = connect

    await setup_entry(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert mock_config_entry.data[CONF_HOST] == NEW_HOST
    mock_rediscover.assert_awaited_once_with(broadcast_addresses={IPv4Address("192.0.2.255")})


async def test_setup_bridge_not_found_again(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    mock_config_entry: MockConfigEntry,
    mock_comfoconnect: dict[str, MagicMock],
    mock_rediscover: MagicMock,
) -> None:
    """Test that a bridge that isn't on the network either is tried again later."""
    mock_comfoconnect["connect"].side_effect = AioComfoConnectTimeout("Timed out")
    mock_rediscover.return_value = [Bridge(NEW_HOST, "22" * 16)]

    await setup_entry(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY
    assert mock_config_entry.data[CONF_HOST] == HOST


@pytest.mark.parametrize(
    ("error", "state"),
    [(AioComfoConnectTimeout("Timed out"), ConfigEntryState.SETUP_RETRY), (ComfoConnectNotAllowed("Not registered"), ConfigEntryState.SETUP_ERROR)],
)
async def test_setup_found_bridge_failed(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    mock_config_entry: MockConfigEntry,
    mock_comfoconnect: dict[str, MagicMock],
    mock_rediscover: MagicMock,
    mock_bridge: MagicMock,
    error: Exception,
    state: ConfigEntryState,
) -> None:
    """Test that a bridge that fails at its new address too is tried again later, or asks to register again."""
    mock_bridge.register.side_effect = ComfoConnectNotAllowed("Wrong PIN")
    mock_comfoconnect["connect"].side_effect = [AioComfoConnectTimeout("Timed out"), error]

    await setup_entry(hass, mock_config_entry)

    assert mock_config_entry.state is state
    assert mock_config_entry.data[CONF_HOST] == HOST


async def test_entities_follow_the_session(
    hass: HomeAssistant, entity_registry: er.EntityRegistry, mock_comfoconnect: dict[str, MagicMock], init_integration: MockConfigEntry
) -> None:
    """Test that every entity is unavailable while the library reconnects, and available again once it has a session."""
    entity_ids = [entry.entity_id for entry in er.async_entries_for_config_entry(entity_registry, init_integration.entry_id) if not entry.disabled_by]
    assert len({entity_id.split(".")[0] for entity_id in entity_ids}) == 5

    set_connection_state(init_integration, ConnectionState.DISCONNECTED)
    await hass.async_block_till_done()
    assert {hass.states.get(entity_id).state for entity_id in entity_ids} == {STATE_UNAVAILABLE}

    set_connection_state(init_integration, ConnectionState.CONNECTED)
    set_connection_state(init_integration, ConnectionState.CONNECTED)
    await hass.async_block_till_done()
    assert STATE_UNAVAILABLE not in {hass.states.get(entity_id).state for entity_id in entity_ids}


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_polled_entities_wait_for_the_session(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, mock_comfoconnect: dict[str, MagicMock], init_integration: MockConfigEntry
) -> None:
    """Test that the polled entities send no requests while the library reconnects."""
    set_connection_state(init_integration, ConnectionState.DISCONNECTED)
    mock_comfoconnect["get_balance_mode"].reset_mock()
    mock_comfoconnect["get_property_constraints"].reset_mock()

    freezer.tick(timedelta(minutes=5))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    mock_comfoconnect["get_balance_mode"].assert_not_awaited()
    mock_comfoconnect["get_property_constraints"].assert_not_awaited()


async def test_session_not_allowed(hass: HomeAssistant, mock_bridge: MagicMock, init_integration: MockConfigEntry) -> None:
    """Test that a session the bridge refuses, because it doesn't know us anymore, asks to register again."""
    mock_bridge.register.side_effect = ComfoConnectNotAllowed("Wrong PIN")
    set_connection_state(init_integration, ConnectionState.NOT_ALLOWED)
    await hass.async_block_till_done()

    assert hass.states.get("fan.comfoairq").state == STATE_UNAVAILABLE
    [flow] = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert flow["context"]["source"] == SOURCE_REAUTH
    assert flow["step_id"] == "enter_pin"


@pytest.mark.usefixtures("mock_discover_bridges", "mock_setup_entry")
async def test_import_from_yaml(hass: HomeAssistant, enable_custom_integrations: None) -> None:
    """Test that a comfoconnect entry in configuration.yaml is imported, with its token as our UUID."""
    assert await async_setup_component(hass, DOMAIN, {DOMAIN: {CONF_HOST: HOST, "token": LOCAL_UUID}})
    await hass.async_block_till_done()

    [entry] = hass.config_entries.async_entries(DOMAIN)
    assert entry.source == SOURCE_IMPORT
    assert entry.data == {CONF_HOST: HOST, CONF_UUID: BRIDGE_UUID, CONF_LOCAL_UUID: LOCAL_UUID}


async def test_entities_disabled_by_default(
    hass: HomeAssistant, entity_registry: er.EntityRegistry, snapshot: SnapshotAssertion, init_integration: MockConfigEntry
) -> None:
    """Test which entities are disabled by default: every enabled sensor is a subscription on the bridge, so the less used ones stay off."""
    entries = er.async_entries_for_config_entry(entity_registry, init_integration.entry_id)

    assert sorted(entry.entity_id for entry in entries if entry.disabled_by) == snapshot
