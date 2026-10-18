"""Support to control a Zehnder ComfoAir Q350/450/600 ventilation unit."""

from __future__ import annotations

import logging
from datetime import timedelta

import voluptuous as vol
from aiocomfoconnect import ComfoConnect, discover_bridges
from aiocomfoconnect.const import ConnectionState, GatewayType
from aiocomfoconnect.exceptions import (
    AioComfoConnectError,
    AioComfoConnectNotReachable,
    AioComfoConnectTimeout,
    ComfoConnectNotAllowed,
)
from aiocomfoconnect.properties import (
    PROPERTY_FIRMWARE_VERSION,
    PROPERTY_MODEL,
    PROPERTY_NAME,
    PROPERTY_SERIAL_NUMBER,
)
from aiocomfoconnect.sensors import Sensor
from aiocomfoconnect.util import version_decode
from homeassistant.components import network
from homeassistant.components.fan import DOMAIN as FAN_DOMAIN
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import CONF_HOST, EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import service
from homeassistant.helpers.dispatcher import async_dispatcher_send, dispatcher_send
from homeassistant.helpers.typing import ConfigType

from .const import ATTR_DURATION, CONF_LOCAL_UUID, CONF_UUID, DOMAIN, SERVICE_START_BOOST

PLATFORMS: list[Platform] = [
    Platform.FAN,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SELECT,
    Platform.NUMBER,
    Platform.BUTTON,
]

_LOGGER = logging.getLogger(__name__)

SIGNAL_COMFOCONNECT_UPDATE_RECEIVED = "comfoconnect_update_{}_{}"
SIGNAL_COMFOCONNECT_ALARM_RECEIVED = "comfoconnect_alarm_{}"
SIGNAL_COMFOCONNECT_AVAILABILITY = "comfoconnect_availability_{}"

EVENT_COMFOCONNECT_ALARM = "comfoconnect_alarm"

# The unit takes a timer duration in whole seconds, as a signed 32-bit number.
MAX_TIMER_DURATION = timedelta(seconds=2**31 - 1)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up Zehnder ComfoConnect integration from yaml."""
    service.async_register_platform_entity_service(
        hass,
        DOMAIN,
        SERVICE_START_BOOST,
        entity_domain=FAN_DOMAIN,
        schema={
            vol.Required(ATTR_DURATION): vol.All(
                cv.time_period,
                vol.Range(min=timedelta(seconds=1), max=MAX_TIMER_DURATION),
            ),
        },
        func="async_start_boost",
    )

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

    try:
        bridge = ComfoConnectBridge(hass, entry.data[CONF_HOST], entry.data[CONF_UUID])
        await bridge.connect(entry.data[CONF_LOCAL_UUID])

    except ComfoConnectNotAllowed:
        raise ConfigEntryAuthFailed("Access denied")

    except (AioComfoConnectTimeout, AioComfoConnectNotReachable) as err:
        # We can't reach the bridge, this can happen when the IP address of the bridge has changed.
        _LOGGER.warning(
            'Could not connect to bridge "%s", trying discovery again.',
            entry.data[CONF_HOST],
        )

        broadcast_addresses = await network.async_get_ipv4_broadcast_addresses(hass)
        bridges = await discover_bridges(broadcast_addresses=broadcast_addresses)
        discovered_bridge = next((b for b in bridges if b.uuid == entry.data[CONF_UUID]), None)
        if not discovered_bridge:
            _LOGGER.warning('Unable to discover bridge "%s". Retrying later.', entry.data[CONF_UUID])
            raise ConfigEntryNotReady from err

        # Try again, with the updated host this time
        bridge = ComfoConnectBridge(hass, discovered_bridge.host, entry.data[CONF_UUID])
        try:
            await bridge.connect(entry.data[CONF_LOCAL_UUID])

            # Update the host in the config entry
            hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_HOST: discovered_bridge.host})

        except ComfoConnectNotAllowed:
            raise ConfigEntryAuthFailed("Access denied")

        except AioComfoConnectError as err:
            raise ConfigEntryNotReady from err

    except AioComfoConnectError as err:
        # E.g. no ventilation unit on the bus yet, or an old bridge whose only session is taken by the app.
        raise ConfigEntryNotReady from err

    # A failed read must not leave a reconnecting session behind the failed entry.
    try:
        bridge_info = await bridge.cmd_version_request()
        unit_model = await bridge.get_property(PROPERTY_MODEL)
        unit_firmware = await bridge.get_property(PROPERTY_FIRMWARE_VERSION)
        unit_name = await bridge.get_property(PROPERTY_NAME)
        unit_serial_number = await bridge.get_property(PROPERTY_SERIAL_NUMBER)
    except AioComfoConnectError as err:
        await bridge.disconnect()
        raise ConfigEntryNotReady("The bridge did not return its device information") from err
    except BaseException:
        # Cancellation or an unexpected read failure also releases the session.
        await bridge.disconnect()
        raise

    hass.data[DOMAIN][entry.entry_id] = bridge
    bridge.entry = entry

    device_registry = dr.async_get(hass)

    # The bridge type is known once the session has started: a ComfoConnect Pro identifies itself then.
    bridge_model = "ComfoConnect Pro" if bridge.bridge_type == GatewayType.PRO else "ComfoConnect LAN C"

    # Add Bridge to device registry
    bridge_device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, bridge_info.serialNumber)},
        manufacturer="Zehnder",
        name=bridge_model,
        model=bridge_model,
        serial_number=bridge_info.serialNumber,
        sw_version=version_decode(bridge_info.gatewayVersion),
    )

    # Add Ventilation Unit to device registry, connected through the bridge. Passing `via_device` to
    # async_get_or_create is deprecated, and its replacement `via_device_id` only exists there since
    # Home Assistant 2026.8, so link the devices with async_update_device, which works on all versions.
    unit_device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, bridge.uuid)},
        manufacturer="Zehnder",
        name=unit_name,
        model=unit_model,
        serial_number=unit_serial_number,
        sw_version=unit_firmware,
    )
    device_registry.async_update_device(unit_device.id, via_device_id=bridge_device.id)
    bridge.device_id = unit_device.id

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Disconnect when shutting down
    async def disconnect_bridge(event):
        """Close connection to the bridge."""
        await bridge.disconnect()

    entry.async_on_unload(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, disconnect_bridge))

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

    def __init__(self, hass: HomeAssistant, host: str, uuid: str):
        """Initialize the ComfoConnect bridge."""
        super().__init__(
            host,
            uuid,
            sensor_callback=self.sensor_callback,
            alarm_callback=self.alarm_callback,
            connection_state_callback=self.connection_state_callback,
        )
        self.hass = hass
        # Latest alarms per node; a node is missing until it has reported.
        self.active_alarms: dict[int, dict[int, str]] = {}
        # The config entry and the ventilation unit's device, known once setup has registered them.
        self.entry: ConfigEntry | None = None
        self.device_id: str | None = None
        self.is_available = True

    @callback
    def connection_state_callback(self, state: str) -> None:
        """Follow the session the library keeps up, and ask to register again when the bridge refuses it."""
        self.set_available(state == ConnectionState.CONNECTED)
        if state == ConnectionState.NOT_ALLOWED and self.entry is not None:
            self.entry.async_start_reauth(self.hass)

    @callback
    def set_available(self, available: bool) -> None:
        """Update bridge availability and notify entities via dispatcher."""
        if self.is_available == available:
            return
        self.is_available = available
        _LOGGER.info("Bridge %s availability changed: %s", self.uuid, available)
        async_dispatcher_send(self.hass, SIGNAL_COMFOCONNECT_AVAILABILITY.format(self.uuid), available)

    @callback
    def sensor_callback(self, sensor: Sensor, value):
        """Notify listeners that we have received an update."""
        dispatcher_send(
            self.hass,
            SIGNAL_COMFOCONNECT_UPDATE_RECEIVED.format(self.uuid, sensor.id),
            value,
        )

    @callback
    def alarm_callback(self, node_id: int, errors: dict[int, str]) -> None:
        """Cache changed alarms and notify the diagnostic sensor."""
        previous = self.active_alarms.get(node_id)
        if previous == errors:
            return
        self.active_alarms[node_id] = dict(errors)
        dispatcher_send(self.hass, SIGNAL_COMFOCONNECT_ALARM_RECEIVED.format(self.uuid))

        # An initial empty report clears nothing; do not emit a clear on every start or reload.
        if previous is not None or errors:
            self.hass.bus.async_fire(
                EVENT_COMFOCONNECT_ALARM,
                {
                    "device_id": self.device_id,
                    "bridge_uuid": self.uuid,
                    "node_id": node_id,
                    "errors": [{"id": error_id, "message": error} for error_id, error in errors.items()],
                },
            )

        message = f"Alarm received for Node {node_id}:\n"
        for error_id, error in errors.items():
            message += f"* {error_id}: {error}\n"
        _LOGGER.warning(message)
