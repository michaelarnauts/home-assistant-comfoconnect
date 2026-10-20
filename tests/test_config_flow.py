"""Test the config flow, through the flow manager like Home Assistant runs it."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, call

import pytest
from aiocomfoconnect.exceptions import AioComfoConnectTimeout, ComfoConnectNotAllowed, ComfoConnectOtherSession
from custom_components.comfoconnect.config_flow import COMFOCONNECT_MANUAL_BRIDGE_ID, DEFAULT_PIN
from custom_components.comfoconnect.const import CONF_LOCAL_UUID, CONF_UUID, DOMAIN
from homeassistant.config_entries import SOURCE_IMPORT, SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_PIN
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry
from tests.conftest import BRIDGE_UUID, HOST, LOCAL_UUID

# Errors of a bridge that can't be reached, or that another app is using.
CONNECTION_ERRORS = [AioComfoConnectTimeout("timeout"), ComfoConnectOtherSession("busy")]
MANUAL_OPTION = {COMFOCONNECT_MANUAL_BRIDGE_ID: "Manually add a ComfoConnect LAN C Bridge"}

pytestmark = pytest.mark.usefixtures("mock_setup_entry")


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load the integration from custom_components."""
    return


def assert_entry_created(result, local_uuid: str | None = None) -> None:
    """Assert that the flow created the entry for the bridge, with our own UUID if we know it up front."""
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == HOST
    assert result["data"] == {CONF_HOST: HOST, CONF_UUID: BRIDGE_UUID, CONF_LOCAL_UUID: local_uuid or result["data"][CONF_LOCAL_UUID]}
    assert len(result["data"][CONF_LOCAL_UUID]) == 32
    assert result["result"].unique_id == BRIDGE_UUID


async def start_user_flow(hass: HomeAssistant):
    """Start the flow from the integrations page."""
    return await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})


async def start_manual_flow(hass: HomeAssistant):
    """Start the flow and choose to enter the host of the bridge."""
    result = await start_user_flow(hass)
    return await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_UUID: COMFOCONNECT_MANUAL_BRIDGE_ID})


@pytest.mark.usefixtures("mock_discover_bridges")
async def test_user_flow(hass: HomeAssistant, mock_bridge: MagicMock) -> None:
    """Test that picking a discovered bridge registers on it with the default PIN."""
    result = await start_user_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_UUID: BRIDGE_UUID})

    assert_entry_created(result)
    mock_bridge.register.assert_awaited_once_with(result["data"][CONF_LOCAL_UUID], "Home Assistant (test home)", DEFAULT_PIN)
    mock_bridge.disconnect.assert_awaited_once()


@pytest.mark.usefixtures("mock_discover_bridges")
async def test_user_flow_lists_unconfigured_bridges(hass: HomeAssistant, mock_config_entry: MockConfigEntry) -> None:
    """Test that the form lists the bridges we don't have yet, and always offers to enter a host."""
    result = await start_user_flow(hass)
    (key,) = result["data_schema"].schema
    assert result["data_schema"].schema[key].container == {BRIDGE_UUID: HOST, **MANUAL_OPTION}

    mock_config_entry.add_to_hass(hass)
    result = await start_user_flow(hass)
    (key,) = result["data_schema"].schema
    assert result["data_schema"].schema[key].container == MANUAL_OPTION


@pytest.mark.usefixtures("mock_discover_bridges")
@pytest.mark.parametrize("error", CONNECTION_ERRORS)
async def test_user_flow_cannot_connect(hass: HomeAssistant, mock_bridge: MagicMock, error: Exception) -> None:
    """Test that a bridge that can't be reached shows the list again, and can be picked again."""
    result = await start_user_flow(hass)

    mock_bridge.register.side_effect = error
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_UUID: BRIDGE_UUID})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "cannot_connect"}
    mock_bridge.disconnect.assert_awaited_once()

    mock_bridge.register.side_effect = None
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_UUID: BRIDGE_UUID})
    assert_entry_created(result)


@pytest.mark.usefixtures("mock_discover_bridges")
async def test_user_flow_already_configured(hass: HomeAssistant, mock_bridge: MagicMock, mock_config_entry: MockConfigEntry) -> None:
    """Test that a bridge that was added while the form was open isn't added twice."""
    result = await start_user_flow(hass)
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_UUID: BRIDGE_UUID})

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    mock_bridge.register.assert_not_awaited()


async def test_manual_flow(hass: HomeAssistant, mock_discover_bridges: AsyncMock, mock_bridge: MagicMock) -> None:
    """Test that entering the host of a bridge finds it there and registers on it."""
    result = await start_manual_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "manual"
    assert result["errors"] == {}

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: HOST})

    assert_entry_created(result)
    assert mock_discover_bridges.await_args == call(HOST)
    mock_bridge.register.assert_awaited_once_with(result["data"][CONF_LOCAL_UUID], "Home Assistant (test home)", DEFAULT_PIN)


async def test_manual_flow_invalid_host(hass: HomeAssistant, mock_discover_bridges: AsyncMock, mock_bridge: MagicMock) -> None:
    """Test that a host without a bridge asks for the host again."""
    result = await start_manual_flow(hass)

    mock_discover_bridges.return_value = []
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: HOST})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "manual"
    assert result["errors"] == {"base": "invalid_host"}

    mock_discover_bridges.return_value = [mock_bridge]
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: HOST})
    assert_entry_created(result)


@pytest.mark.usefixtures("mock_discover_bridges")
@pytest.mark.parametrize("error", CONNECTION_ERRORS)
async def test_manual_flow_cannot_connect(hass: HomeAssistant, mock_bridge: MagicMock, error: Exception) -> None:
    """Test that a bridge that can't be reached asks for the host again, with the host filled in."""
    result = await start_manual_flow(hass)

    mock_bridge.register.side_effect = error
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: HOST})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "manual"
    assert result["errors"] == {"base": "cannot_connect"}
    (key,) = result["data_schema"].schema
    assert key.description == {"suggested_value": HOST}

    mock_bridge.register.side_effect = None
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: HOST})
    assert_entry_created(result)


@pytest.mark.usefixtures("mock_discover_bridges")
async def test_manual_flow_already_configured(hass: HomeAssistant, mock_bridge: MagicMock, mock_config_entry: MockConfigEntry) -> None:
    """Test that the host of a bridge we already have isn't added twice."""
    mock_config_entry.add_to_hass(hass)
    result = await start_manual_flow(hass)

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: HOST})

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    mock_bridge.register.assert_not_awaited()


@pytest.mark.usefixtures("mock_discover_bridges")
async def test_pin_flow(hass: HomeAssistant, mock_bridge: MagicMock) -> None:
    """Test that a bridge that refuses the default PIN asks for the PIN, and registers with it."""
    result = await start_user_flow(hass)

    mock_bridge.register.side_effect = [ComfoConnectNotAllowed("refused"), None]
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_UUID: BRIDGE_UUID})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "enter_pin"
    assert result["errors"] == {}

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_PIN: "1234"})

    assert_entry_created(result)
    assert mock_bridge.register.await_args.args[2] == 1234


@pytest.mark.usefixtures("mock_discover_bridges")
@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (ComfoConnectNotAllowed("refused"), "invalid_pin"),
        (AioComfoConnectTimeout("timeout"), "cannot_connect"),
    ],
)
async def test_pin_flow_errors(hass: HomeAssistant, mock_bridge: MagicMock, error: Exception, reason: str) -> None:
    """Test that a wrong PIN or a lost bridge asks for the PIN again, and that it can be entered again."""
    result = await start_user_flow(hass)

    mock_bridge.register.side_effect = [ComfoConnectNotAllowed("refused"), error, None]
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_UUID: BRIDGE_UUID})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_PIN: "1234"})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "enter_pin"
    assert result["errors"] == {"base": reason}

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_PIN: "4321"})
    assert_entry_created(result)
    assert mock_bridge.register.await_args.args[2] == 4321


async def test_reauth_flow(hass: HomeAssistant, mock_bridge: MagicMock, mock_config_entry: MockConfigEntry, mock_setup_entry: AsyncMock) -> None:
    """Test that a reauth registers again with the UUID we already use, and reloads the entry."""
    mock_config_entry.add_to_hass(hass)

    result = await mock_config_entry.start_reauth_flow(hass)
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    mock_bridge.register.assert_awaited_once_with(LOCAL_UUID, "Home Assistant (test home)", DEFAULT_PIN)
    mock_setup_entry.assert_awaited_once()


async def test_reauth_flow_pin(hass: HomeAssistant, mock_bridge: MagicMock, mock_config_entry: MockConfigEntry) -> None:
    """Test that a reauth on a bridge that refuses the default PIN asks for the PIN."""
    mock_config_entry.add_to_hass(hass)

    mock_bridge.register.side_effect = [ComfoConnectNotAllowed("refused"), None]
    result = await mock_config_entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "enter_pin"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_PIN: "1234"})
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert mock_bridge.register.await_args == call(LOCAL_UUID, "Home Assistant (test home)", 1234)


async def test_reauth_flow_cannot_connect(hass: HomeAssistant, mock_bridge: MagicMock, mock_config_entry: MockConfigEntry) -> None:
    """Test that a reauth on a bridge that can't be reached aborts, since it has no form to return to."""
    mock_config_entry.add_to_hass(hass)

    mock_bridge.register.side_effect = AioComfoConnectTimeout("timeout")
    result = await mock_config_entry.start_reauth_flow(hass)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"


async def test_import_flow(hass: HomeAssistant, mock_discover_bridges: AsyncMock, mock_bridge: MagicMock) -> None:
    """Test that a YAML import registers with the token of the core integration as our UUID."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_IMPORT}, data={CONF_HOST: HOST, "token": LOCAL_UUID})

    assert_entry_created(result, LOCAL_UUID)
    mock_discover_bridges.assert_awaited_once_with(HOST)
    mock_bridge.register.assert_awaited_once_with(LOCAL_UUID, "Home Assistant (test home)", DEFAULT_PIN)


@pytest.mark.usefixtures("mock_discover_bridges")
async def test_import_flow_cannot_connect(hass: HomeAssistant, mock_bridge: MagicMock) -> None:
    """Test that a YAML import of a bridge that can't be reached aborts, since it has no form to return to."""
    mock_bridge.register.side_effect = AioComfoConnectTimeout("timeout")

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_IMPORT}, data={CONF_HOST: HOST, "token": LOCAL_UUID})

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"


@pytest.mark.usefixtures("mock_discover_bridges")
@pytest.mark.parametrize(
    ("location_name", "device_name"),
    [
        ("Home", "Home Assistant (Home)"),
        ("Chalet Bergblick", "Home Assistant (Chalet Bergblic"),
        ("ą" * 8, "Home Assistant (ąąąąąąą"),
        ("A" * 14 + "🏠", "Home Assistant (AAAAAAAAAAAAAA"),
    ],
)
async def test_registration_name_fits_bridge_buffer(hass: HomeAssistant, mock_bridge: MagicMock, location_name: str, device_name: str) -> None:
    """Test that a long or multibyte location name is cut to the 31 bytes the bridge has for the name, without breaking a character."""
    hass.config.location_name = location_name
    result = await start_user_flow(hass)

    await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_UUID: BRIDGE_UUID})

    assert mock_bridge.register.await_args.args[1] == device_name
