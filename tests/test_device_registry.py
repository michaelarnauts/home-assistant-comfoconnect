"""The ventilation unit is registered as a device connected through the bridge."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from aiocomfoconnect.const import GatewayType
from aiocomfoconnect.properties import PROPERTY_MODEL, PROPERTY_NAME, PROPERTY_SERIAL_NUMBER
from custom_components.comfoconnect import EVENT_COMFOCONNECT_ALARM
from custom_components.comfoconnect.const import CONF_LOCAL_UUID, CONF_UUID, DOMAIN
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr

# These tests set up the integration in a real Home Assistant instance. They need
# pytest-homeassistant-custom-component (and asyncio_mode = "auto"), which the dev
# dependencies don't include yet, so skip them where it isn't installed. Taken from
# importorskip's return value, since an import after it trips E402 on older ruff.
MockConfigEntry = pytest.importorskip("pytest_homeassistant_custom_component.common").MockConfigEntry

BRIDGE = "custom_components.comfoconnect.ComfoConnectBridge"
UNIT_UUID = "00" * 16
UNIT_PROPERTIES = {
    PROPERTY_NAME.property_id: "ComfoAirQ",
    PROPERTY_MODEL.property_id: "ComfoAir Q450",
    PROPERTY_SERIAL_NUMBER.property_id: "BEA0000000001",
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load the integration from custom_components."""
    return


async def test_unit_is_connected_through_the_bridge(hass: HomeAssistant) -> None:
    """Both devices exist and the unit points at the bridge, without the deprecated `via_device`."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="192.0.2.10",
        data={CONF_HOST: "192.0.2.10", CONF_UUID: UNIT_UUID, CONF_LOCAL_UUID: "11" * 16},
    )
    entry.add_to_hass(hass)

    with (
        patch(f"{BRIDGE}.connect", new_callable=AsyncMock),
        patch(f"{BRIDGE}.disconnect", new_callable=AsyncMock),
        patch(
            f"{BRIDGE}.cmd_version_request",
            new_callable=AsyncMock,
            return_value=SimpleNamespace(serialNumber="DEMO0001", gatewayVersion=0),
        ),
        patch(f"{BRIDGE}.get_property", new_callable=AsyncMock, side_effect=lambda prop: UNIT_PROPERTIES.get(prop.property_id, 0)),
        patch("custom_components.comfoconnect.version_decode", return_value="1.0.0"),
        patch(
            "homeassistant.config_entries.ConfigEntries.async_forward_entry_setups",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch.object(
            dr.DeviceRegistry,
            "async_get_or_create",
            autospec=True,
            side_effect=dr.DeviceRegistry.async_get_or_create,
        ) as get_or_create,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)

    # Deprecated since Home Assistant 2026.7, stops working in 2027.8.
    assert all("via_device" not in call.kwargs for call in get_or_create.call_args_list)

    registry = dr.async_get(hass)
    bridge_device = registry.async_get_device_by_identifier((DOMAIN, "DEMO0001"), entry.entry_id)
    unit_device = registry.async_get_device_by_identifier((DOMAIN, UNIT_UUID), entry.entry_id)
    assert bridge_device is not None
    assert unit_device is not None
    assert unit_device.via_device_id == bridge_device.id

    # The bridge is named after its model, and both devices show their serial number.
    assert (bridge_device.name, bridge_device.model, bridge_device.serial_number) == ("ComfoConnect LAN C", "ComfoConnect LAN C", "DEMO0001")
    assert (unit_device.name, unit_device.model, unit_device.serial_number) == ("ComfoAirQ", "ComfoAir Q450", "BEA0000000001")

    # Alarm automations must identify the registered unit, rather than the LAN bridge.
    events = []
    hass.bus.async_listen(EVENT_COMFOCONNECT_ALARM, callback(lambda event: events.append(event.data)))
    hass.data[DOMAIN][entry.entry_id].alarm_callback(1, {79: "Replace filters"})
    await hass.async_block_till_done()
    assert events[0]["device_id"] == unit_device.id


async def test_comfoconnect_pro_is_shown_as_pro(hass: HomeAssistant) -> None:
    """A Pro identifies itself when the session starts, so the bridge device is named and modelled after it."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="192.0.2.10",
        data={CONF_HOST: "192.0.2.10", CONF_UUID: UNIT_UUID, CONF_LOCAL_UUID: "11" * 16},
    )
    entry.add_to_hass(hass)

    async def connect_to_a_pro(bridge, uuid):
        bridge.bridge_type = GatewayType.PRO

    with (
        patch(f"{BRIDGE}.connect", autospec=True, side_effect=connect_to_a_pro),
        patch(f"{BRIDGE}.disconnect", new_callable=AsyncMock),
        patch(
            f"{BRIDGE}.cmd_version_request",
            new_callable=AsyncMock,
            return_value=SimpleNamespace(serialNumber="DEMO0002", gatewayVersion=0),
        ),
        patch(f"{BRIDGE}.get_property", new_callable=AsyncMock, side_effect=lambda prop: UNIT_PROPERTIES.get(prop.property_id, 0)),
        patch("custom_components.comfoconnect.version_decode", return_value="1.0.0"),
        patch(
            "homeassistant.config_entries.ConfigEntries.async_forward_entry_setups",
            new_callable=AsyncMock,
            return_value=True,
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)

    bridge_device = dr.async_get(hass).async_get_device_by_identifier((DOMAIN, "DEMO0002"), entry.entry_id)
    assert (bridge_device.name, bridge_device.model) == ("ComfoConnect Pro", "ComfoConnect Pro")
