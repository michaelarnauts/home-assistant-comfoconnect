"""Support to control a Zehnder ComfoAir Q350/450/600 ventilation unit."""
from __future__ import annotations

from datetime import timedelta
import logging

from aiocomfoconnect import ComfoConnect
from aiocomfoconnect.exceptions import (
    AioComfoConnectNotConnected,
    ComfoConnectError,
    ComfoConnectNotAllowed,
)
from aiocomfoconnect.properties import PROPERTY_FIRMWARE_VERSION, PROPERTY_MODEL
from aiocomfoconnect.sensors import Sensor
from aiocomfoconnect.util import version_decode

from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import CONF_HOST, EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import dispatcher_send
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.typing import ConfigType

from .const import CONF_LOCAL_UUID, CONF_UUID, DOMAIN

PLATFORMS: list[Platform] = [
    Platform.FAN,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SELECT,
    Platform.BUTTON,
]

_LOGGER = logging.getLogger(__name__)

SIGNAL_COMFOCONNECT_UPDATE_RECEIVED = "comfoconnect_update_received_{}"

KEEP_ALIVE_INTERVAL = timedelta(seconds=60)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up Zehnder ComfoConnect integration from yaml."""
    if DOMAIN in config:
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_IMPORT},
                data=config[DOMAIN],
            )
        )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Zehnder ComfoConnect from a config entry."""

    hass.data.setdefault(DOMAIN, {})
    bridge = ComfoConnectBridge(hass, entry)

    try:
        await bridge.connect(entry.data[CONF_LOCAL_UUID])

    except ComfoConnectNotAllowed:
        raise ConfigEntryAuthFailed("Access denied")

    except ComfoConnectError as err:
        raise ConfigEntryError from err

    hass.data[DOMAIN][entry.entry_id] = bridge

    # Get device information
    bridge_info = await bridge.cmd_version_request()
    unit_model = await bridge.get_property(PROPERTY_MODEL)
    unit_firmware = await bridge.get_property(PROPERTY_FIRMWARE_VERSION)

    device_registry = dr.async_get(hass)

    # Add Bridge to device registry
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, bridge_info.serialNumber)},
        manufacturer="Zehnder",
        name="ComfoConnect LAN C",
        default_model="ComfoConnect LAN C",
        sw_version=version_decode(bridge_info.gatewayVersion),
    )

    # Add Ventilation Unit to device registry
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, bridge.uuid)},
        manufacturer="Zehnder",
        name=unit_model,
        default_model=unit_model,
        sw_version=version_decode(unit_firmware),
        via_device=(DOMAIN, bridge_info.serialNumber),
    )

    hass.config_entries.async_setup_platforms(entry, PLATFORMS)

    @callback
    async def send_keepalive(now) -> None:
        """Send keepalive to the bridge."""
        _LOGGER.debug("Sending keepalive...")
        try:
            await bridge.cmd_keepalive()
        except AioComfoConnectNotConnected:
            # Reconnect when connection has been dropped
            await bridge.connect(entry.data[CONF_LOCAL_UUID])

    entry.async_on_unload(
        async_track_time_interval(hass, send_keepalive, KEEP_ALIVE_INTERVAL)
    )

    # Disconnect when shutting down
    async def disconnect_bridge(event):
        """Close connection to the bridge."""
        await bridge.disconnect()

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, disconnect_bridge)
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        bridge = hass.data[DOMAIN][entry.entry_id]
        await bridge.disconnect()
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


class ComfoConnectBridge(ComfoConnect):
    """Representation of a ComfoConnect bridge."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        """Initialize the ComfoConnect bridge."""
        super().__init__(
            entry.data[CONF_HOST],
            entry.data[CONF_UUID],
            hass.loop,
            self.sensor_callback,
            self.alarm_callback,
        )
        self.hass = hass

    @callback
    def sensor_callback(self, sensor: Sensor, value):
        """Notify listeners that we have received an update."""
        dispatcher_send(
            self.hass, SIGNAL_COMFOCONNECT_UPDATE_RECEIVED.format(sensor.id), value
        )

    @callback
    def alarm_callback(self, node_id, errors):
        """Print alarm updates."""
        message = f"Alarm received for Node {node_id}:\n"
        for error_id, error in errors.items():
            message += f"* {error_id}: {error}\n"
        _LOGGER.warning(message)
