"""Test the config flow, through the flow manager like Home Assistant runs it."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, call

import pytest
from aiocomfoconnect.exceptions import AioComfoConnectTimeout, ComfoConnectNotAllowed, ComfoConnectOtherSession
from custom_components.comfoconnect.config_flow import COMFOCONNECT_MANUAL_BRIDGE_ID, DEFAULT_PIN
from custom_components.comfoconnect.const import CONF_AIRFLOW_UNIT, CONF_LOCAL_UUID, CONF_UUID, DOMAIN
from homeassistant.config_entries import SOURCE_IMPORT, SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_PIN
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry
from tests.conftest import BRIDGE_UUID, HOST, LOCAL_UUID

# Errors of a bridge that can't be reached, or that another app is using, and an unexpected one, with the error they show.
ERRORS = [
    (AioComfoConnectTimeout("timeout"), "cannot_connect"),
    (ComfoConnectOtherSession("busy"), "cannot_connect"),
    (RuntimeError("unexpected"), "unknown"),
]
# What the user enters to pick the bridge, in the step that picks it.
BRIDGE_INPUT = {"user": {CONF_UUID: BRIDGE_UUID}, "manual": {CONF_HOST: HOST}}

pytestmark = pytest.mark.usefixtures("mock_setup_entry", "mock_discover_bridges")


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load the integration from custom_components."""
    return


def assert_entry_created(result, local_uuid: str | None = None) -> None:
    """Assert that the flow created the entry for the bridge, with our own UUID if we know it up front."""
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == HOST
    assert result["data"] == {
        CONF_HOST: HOST,
        CONF_UUID: BRIDGE_UUID,
        CONF_LOCAL_UUID: local_uuid or result["data"][CONF_LOCAL_UUID],
        CONF_AIRFLOW_UNIT: "m3ph",
    }
    assert len(result["data"][CONF_LOCAL_UUID]) == 32
    assert result["result"].unique_id == BRIDGE_UUID


async def start_flow(hass: HomeAssistant, step: str = "user"):
    """Start the flow from the integrations page, and choose to enter the host of the bridge for the manual step."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    if step == "manual":
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_UUID: COMFOCONNECT_MANUAL_BRIDGE_ID})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == step
    assert result["errors"] == {}
    return result


async def pick_bridge(hass: HomeAssistant, result, step: str = "user"):
    """Pick the bridge in the form of this step."""
    return await hass.config_entries.flow.async_configure(result["flow_id"], BRIDGE_INPUT[step])


@pytest.mark.parametrize("step", ["user", "manual"])
async def test_flow(hass: HomeAssistant, mock_bridge: MagicMock, step: str) -> None:
    """Test that picking a discovered bridge, or entering its host, registers on it with the default PIN."""
    result = await start_flow(hass, step)

    result = await pick_bridge(hass, result, step)

    assert_entry_created(result)
    mock_bridge.register.assert_awaited_once_with(result["data"][CONF_LOCAL_UUID], "Home Assistant (test home)", DEFAULT_PIN)
    mock_bridge.disconnect.assert_awaited_once()


async def test_detects_litres_per_second(hass: HomeAssistant, mock_bridge: MagicMock) -> None:
    """New Q450 setups record L/s when device PDO 224 reports that unit."""

    async def request_sensor(pdid: int, pdo_type: int) -> None:
        mock_bridge.set_sensor_callback.call_args.args[0](pdid, 2)

    mock_bridge.cmd_rpdo_request.side_effect = request_sensor
    result = await start_flow(hass)
    result = await pick_bridge(hass, result)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_AIRFLOW_UNIT] == "lps"
    mock_bridge.cmd_rpdo_request.assert_called_once()


async def test_unknown_unit_prompts_for_fallback(hass: HomeAssistant, mock_bridge: MagicMock) -> None:
    """When PDO 224 is unavailable, ask the user rather than silently guessing."""
    mock_bridge.cmd_rpdo_request.side_effect = AioComfoConnectTimeout("unit unavailable")
    result = await start_flow(hass)
    result = await pick_bridge(hass, result)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "airflow_unit"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_AIRFLOW_UNIT: "lps"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_AIRFLOW_UNIT] == "lps"


async def test_existing_entry_has_fallback_options(hass: HomeAssistant, mock_config_entry: MockConfigEntry) -> None:
    """Already configured devices can choose a fallback without re-adding the integration."""
    mock_config_entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(result["flow_id"], {CONF_AIRFLOW_UNIT: "lps"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert mock_config_entry.options[CONF_AIRFLOW_UNIT] == "lps"


@pytest.mark.parametrize("step", ["user", "manual"])
@pytest.mark.parametrize(("error", "reason"), ERRORS)
async def test_flow_errors(hass: HomeAssistant, mock_bridge: MagicMock, step: str, error: Exception, reason: str) -> None:
    """Test that a bridge that can't be reached, or fails unexpectedly, shows the form again, and can be picked again."""
    result = await start_flow(hass, step)

    mock_bridge.register.side_effect = error
    result = await pick_bridge(hass, result, step)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == step
    assert result["errors"] == {"base": reason}
    mock_bridge.disconnect.assert_awaited_once()

    mock_bridge.register.side_effect = None
    result = await pick_bridge(hass, result, step)
    assert_entry_created(result)


@pytest.mark.parametrize("step", ["user", "manual"])
async def test_flow_already_configured(hass: HomeAssistant, mock_bridge: MagicMock, mock_config_entry: MockConfigEntry, step: str) -> None:
    """Test that a bridge we already have, or that was added while the form was open, isn't added twice."""
    result = await start_flow(hass, step)
    mock_config_entry.add_to_hass(hass)

    result = await pick_bridge(hass, result, step)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    mock_bridge.register.assert_not_awaited()


async def test_manual_flow_invalid_host(hass: HomeAssistant, mock_discover_bridges: AsyncMock, mock_bridge: MagicMock) -> None:
    """Test that a host without a bridge asks for the host again."""
    result = await start_flow(hass, "manual")

    mock_discover_bridges.return_value = []
    result = await pick_bridge(hass, result, "manual")
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "manual"
    assert result["errors"] == {"base": "invalid_host"}

    mock_discover_bridges.return_value = [mock_bridge]
    result = await pick_bridge(hass, result, "manual")
    assert_entry_created(result)
    assert mock_discover_bridges.await_args == call(HOST)


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (ComfoConnectNotAllowed("refused"), "invalid_pin"),
        (AioComfoConnectTimeout("timeout"), "cannot_connect"),
        (RuntimeError("unexpected"), "unknown"),
    ],
)
async def test_pin_flow(hass: HomeAssistant, mock_bridge: MagicMock, error: Exception, reason: str) -> None:
    """Test that a bridge that refuses the default PIN asks for the PIN, and again after a wrong PIN or a lost bridge."""
    result = await start_flow(hass)

    mock_bridge.register.side_effect = [ComfoConnectNotAllowed("refused"), error, None]
    result = await pick_bridge(hass, result)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "enter_pin"
    assert result["errors"] == {}

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_PIN: "1234"})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "enter_pin"
    assert result["errors"] == {"base": reason}

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_PIN: "4321"})
    assert_entry_created(result)
    assert mock_bridge.register.await_args.args[2] == 4321


async def start_reauth_flow(hass: HomeAssistant, entry: MockConfigEntry):
    """Start a reauth of the entry, which asks to register again."""
    entry.add_to_hass(hass)
    result = await entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert result["description_placeholders"][CONF_HOST] == HOST
    return result


async def test_reauth_flow(hass: HomeAssistant, mock_bridge: MagicMock, mock_config_entry: MockConfigEntry, mock_setup_entry: AsyncMock) -> None:
    """Test that a reauth registers again with the UUID we already use once confirmed, and reloads the entry."""
    result = await start_reauth_flow(hass, mock_config_entry)
    mock_bridge.register.assert_not_awaited()

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    mock_bridge.register.assert_awaited_once_with(LOCAL_UUID, "Home Assistant (test home)", DEFAULT_PIN)
    mock_setup_entry.assert_awaited_once()


async def test_reauth_flow_pin(hass: HomeAssistant, mock_bridge: MagicMock, mock_config_entry: MockConfigEntry) -> None:
    """Test that a reauth on a bridge that refuses the default PIN asks for the PIN."""
    result = await start_reauth_flow(hass, mock_config_entry)

    mock_bridge.register.side_effect = [ComfoConnectNotAllowed("refused"), None]
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "enter_pin"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_PIN: "1234"})
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert mock_bridge.register.await_args == call(LOCAL_UUID, "Home Assistant (test home)", 1234)


@pytest.mark.parametrize(("error", "reason"), ERRORS)
async def test_reauth_flow_errors(
    hass: HomeAssistant, mock_bridge: MagicMock, mock_config_entry: MockConfigEntry, error: Exception, reason: str
) -> None:
    """Test that a reauth on a bridge that can't be reached asks again, and can be confirmed again."""
    result = await start_reauth_flow(hass, mock_config_entry)

    mock_bridge.register.side_effect = error
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert result["errors"] == {"base": reason}

    mock_bridge.register.side_effect = None
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"


async def test_import_flow(hass: HomeAssistant, mock_discover_bridges: AsyncMock, mock_bridge: MagicMock) -> None:
    """Test that a YAML import registers with the token of the core integration as our UUID."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_IMPORT}, data={CONF_HOST: HOST, "token": LOCAL_UUID})

    assert_entry_created(result, LOCAL_UUID)
    mock_discover_bridges.assert_awaited_once_with(HOST)
    mock_bridge.register.assert_awaited_once_with(LOCAL_UUID, "Home Assistant (test home)", DEFAULT_PIN)


@pytest.mark.parametrize(("error", "reason"), ERRORS)
async def test_import_flow_errors(hass: HomeAssistant, mock_bridge: MagicMock, error: Exception, reason: str) -> None:
    """Test that a YAML import of a bridge that can't be reached aborts, since it has no form to return to."""
    mock_bridge.register.side_effect = error

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_IMPORT}, data={CONF_HOST: HOST, "token": LOCAL_UUID})

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == reason


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
    result = await start_flow(hass)

    await pick_bridge(hass, result)

    assert mock_bridge.register.await_args.args[1] == device_name
