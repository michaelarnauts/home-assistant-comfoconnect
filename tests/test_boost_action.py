"""The start_boost action starts boost mode for any duration."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import voluptuous as vol
from aiocomfoconnect.comfoconnect import NodeInfo
from custom_components.comfoconnect.const import CONF_LOCAL_UUID, CONF_UUID, DOMAIN, SERVICE_START_BOOST
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

MockConfigEntry = pytest.importorskip("pytest_homeassistant_custom_component.common").MockConfigEntry

BRIDGE = "custom_components.comfoconnect.ComfoConnectBridge"
UNIT_UUID = "00" * 16


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load the integration from custom_components."""
    return


@pytest.fixture
async def fan_entity_id(hass: HomeAssistant):
    """Set up the integration with only the fan platform, and return the fan's entity id."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="192.0.2.10",
        data={CONF_HOST: "192.0.2.10", CONF_UUID: UNIT_UUID, CONF_LOCAL_UUID: "11" * 16},
    )
    entry.add_to_hass(hass)

    with (
        patch("custom_components.comfoconnect.PLATFORMS", [Platform.FAN]),
        patch(f"{BRIDGE}.connect", new_callable=AsyncMock),
        patch(f"{BRIDGE}.disconnect", new_callable=AsyncMock),
        patch(
            f"{BRIDGE}.cmd_version_request",
            new_callable=AsyncMock,
            return_value=SimpleNamespace(serialNumber="DEMO0001", gatewayVersion=0),
        ),
        patch(f"{BRIDGE}.get_node_info", new_callable=AsyncMock, return_value=NodeInfo("ComfoAirQ", "ComfoAir Q350", None, None, None, None)),
        patch(f"{BRIDGE}.register_sensor", new_callable=AsyncMock),
        patch(f"{BRIDGE}.get_mode", new_callable=AsyncMock, return_value="auto"),
        patch("custom_components.comfoconnect.version_decode", return_value="1.0.0"),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    return er.async_get(hass).async_get_entity_id(Platform.FAN, DOMAIN, UNIT_UUID)


@pytest.mark.parametrize(
    ("duration", "seconds"),
    [
        ({"hours": 2, "minutes": 30}, 9000),
        ("00:01:30", 90),
        ({"hours": 24}, 86400),
    ],
)
async def test_start_boost_for_any_duration(hass: HomeAssistant, fan_entity_id: str, duration, seconds: int) -> None:
    """The duration is passed on to the unit in seconds."""
    with patch(f"{BRIDGE}.set_boost", new_callable=AsyncMock) as set_boost:
        await hass.services.async_call(
            DOMAIN,
            SERVICE_START_BOOST,
            {"entity_id": fan_entity_id, "duration": duration},
            blocking=True,
        )

    set_boost.assert_awaited_once_with(True, seconds)


@pytest.mark.parametrize("duration", ["00:00:00", {"days": 30000}])
async def test_start_boost_rejects_durations_the_unit_cannot_take(hass: HomeAssistant, fan_entity_id: str, duration) -> None:
    """A zero duration, or one that doesn't fit the unit's 32-bit timer, is rejected."""
    with patch(f"{BRIDGE}.set_boost", new_callable=AsyncMock) as set_boost, pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_START_BOOST,
            {"entity_id": fan_entity_id, "duration": duration},
            blocking=True,
        )

    set_boost.assert_not_awaited()
