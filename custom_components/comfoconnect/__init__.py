"""Support to control a Zehnder ComfoAir Q350/450/600 ventilation unit."""

from __future__ import annotations

import logging
from datetime import timedelta

import voluptuous as vol
from aiocomfoconnect import ComfoConnect, discover_bridges
from aiocomfoconnect.bridge import Node
from aiocomfoconnect.comfoconnect import NodeInfo
from aiocomfoconnect.const import ConnectionState, ProductId
from aiocomfoconnect.exceptions import (
    AioComfoConnectError,
    AioComfoConnectNotReachable,
    AioComfoConnectTimeout,
    ComfoConnectNotAllowed,
)
from aiocomfoconnect.sensors import SENSOR_CO2_1, SENSOR_CO2_8, Sensor
from homeassistant.components import network
from homeassistant.components.fan import DOMAIN as FAN_DOMAIN
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import CONF_HOST, EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import service
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.typing import ConfigType

from .const import ATTR_DURATION, CONF_LOCAL_UUID, CONF_UUID, DOMAIN, PRODUCT_MODELS, SERVICE_START_BOOST

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

# The ComfoNet CO2 sensors in zone 1 report on SENSOR_CO2_1 to SENSOR_CO2_8, ordered by node id.
CO2_SENSOR_IDS = range(SENSOR_CO2_1, SENSOR_CO2_8 + 1)

type ComfoConnectConfigEntry = ConfigEntry[ComfoConnectBridge]

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


def find_co2_sensors(bridge: ComfoConnectBridge) -> list[tuple[int, int]]:
    """Return the node id and sensor id of each ComfoNet CO2 sensor in zone 1."""
    node_ids = []
    for node in sorted(bridge.nodes.values(), key=lambda node: node.node_id):
        if node.product_id != ProductId.CO2SENSOR:
            continue
        if node.zone_id != 1:
            _LOGGER.debug("Skipping CO2 sensor on node %s in zone %s, only zone 1 is supported", node.node_id, node.zone_id)
            continue
        node_ids.append(node.node_id)
    if len(node_ids) > len(CO2_SENSOR_IDS):
        _LOGGER.debug("Skipping CO2 sensors on nodes %s, only %d are supported", node_ids[len(CO2_SENSOR_IDS) :], len(CO2_SENSOR_IDS))
    return list(zip(node_ids, CO2_SENSOR_IDS, strict=False))


def node_device_info(node: Node, info: NodeInfo | None) -> dict[str, str | None] | None:
    """Return the device registry fields of a node, from its product id and what it tells about itself."""
    # None for a node we can't name: a product we don't know, that doesn't tell its name or model.
    info = info or NodeInfo(None, None, None, None, None, None, None)
    # Most nodes don't tell their model, then it's named after the product.
    model = info.model or PRODUCT_MODELS.get(node.product_id)
    # A name can end with spaces, e.g. "CO2 woonkamer ".
    name = (info.name or "").strip() or model
    if not name:
        return None
    return {
        "name": name,
        "model": model,
        "model_id": info.article_number,
        "serial_number": info.serial_number,
        "sw_version": info.firmware,
        "hw_version": None if info.hardware_version is None else str(info.hardware_version),
    }


async def async_setup_entry(hass: HomeAssistant, entry: ComfoConnectConfigEntry) -> bool:
    """Set up Zehnder ComfoConnect from a config entry."""

    try:
        bridge = ComfoConnectBridge(hass, entry, entry.data[CONF_HOST])
        await bridge.connect(entry.data[CONF_LOCAL_UUID])

    except ComfoConnectNotAllowed:
        raise ConfigEntryAuthFailed(translation_domain=DOMAIN, translation_key="access_denied")

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
        bridge = ComfoConnectBridge(hass, entry, discovered_bridge.host)
        try:
            await bridge.connect(entry.data[CONF_LOCAL_UUID])

            # Update the host in the config entry
            hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_HOST: discovered_bridge.host})

        except ComfoConnectNotAllowed:
            raise ConfigEntryAuthFailed(translation_domain=DOMAIN, translation_key="access_denied")

        except AioComfoConnectError as err:
            raise ConfigEntryNotReady from err

    except AioComfoConnectError as err:
        # E.g. no ventilation unit on the bus yet, or an old bridge whose only session is taken by the app.
        raise ConfigEntryNotReady from err

    # A failed read must not leave a reconnecting session behind the failed entry.
    try:
        unit_info = await bridge.get_node_info()
    except AioComfoConnectError as err:
        await bridge.disconnect()
        raise ConfigEntryNotReady(translation_domain=DOMAIN, translation_key="device_info_failed") from err
    except BaseException:
        # Cancellation or an unexpected read failure also releases the session.
        await bridge.disconnect()
        raise

    entry.runtime_data = bridge

    # Add a device for every node on the bus. The bridge announces some nodes, like itself, a little after we
    # connected; the node callback adds those.
    bridge.add_node_devices = True
    try:
        for node in list(bridge.nodes.values()):
            await bridge.async_add_node_device(node, unit_info if node.node_id == bridge.ventilation_node_id else None)
    except BaseException:
        await bridge.disconnect()
        raise

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Disconnect when shutting down
    async def disconnect_bridge(event):
        """Close connection to the bridge."""
        await bridge.disconnect()

    entry.async_on_unload(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, disconnect_bridge))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ComfoConnectConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.disconnect()

    return unload_ok


async def async_remove_config_entry_device(hass: HomeAssistant, entry: ComfoConnectConfigEntry, device_entry: dr.DeviceEntry) -> bool:
    """Allow removing a device that isn't the device of a node on the bus, e.g. of a node that left it, or the unit."""
    bridge = entry.runtime_data
    # The nodes are only known while we are connected.
    node_device_ids = {device_id for _node, device_id, _serial in bridge.node_devices.values()}
    return bridge.is_available and device_entry.id != bridge.device_id and device_entry.id not in node_device_ids


class ComfoConnectBridge(ComfoConnect):
    """Representation of a ComfoConnect bridge."""

    def __init__(self, hass: HomeAssistant, entry: ComfoConnectConfigEntry, host: str):
        """Initialize the ComfoConnect bridge of a config entry."""
        super().__init__(
            host,
            entry.data[CONF_UUID],
            sensor_callback=self.sensor_callback,
            alarm_callback=self.alarm_callback,
            connection_state_callback=self.connection_state_callback,
            node_callback=self.node_callback,
        )
        self.hass = hass
        self.entry = entry
        # Latest alarms per node; a node is missing until it has reported.
        self.active_alarms: dict[int, dict[int, str]] = {}
        # The ventilation unit's device, known once setup has registered it.
        self.device_id: str | None = None
        # The node, device id and serial number of each node on the bus, once its device has been added; the serial
        # number is None for the unit. Setup turns on adding them.
        self.node_devices: dict[int, tuple[Node, str, str | None]] = {}
        self.add_node_devices = False
        self.is_available = True

    async def async_add_node_device(self, node: Node, info: NodeInfo | None = None) -> None:
        """Add the device of a node, with what it tells about itself, and link it to the bridge."""
        if info is None:
            try:
                info = await self.get_node_info(node.node_id)
            except AioComfoConnectError as err:
                _LOGGER.debug("Could not read the device info of node %s: %s", node.node_id, err)
        fields = node_device_info(node, info)
        if fields is None:
            _LOGGER.debug("Not adding a device for node %s with unknown product id %s", node.node_id, node.product_id)
            return

        # Node ids can change, e.g. after a firmware update, so a node is identified by its serial number. The unit
        # keeps the uuid of the bridge, for the unit behind it.
        if node.node_id == self.ventilation_node_id:
            identifier, serial = self.uuid, None
        elif fields["serial_number"]:
            identifier = serial = fields["serial_number"]
        else:
            # Without a serial number we can't tell it's the same device later; we try again when it's announced again.
            _LOGGER.debug("Not adding a device for node %s yet, its serial number is unknown", node.node_id)
            return
        device = dr.async_get(self.hass).async_get_or_create(
            config_entry_id=self.entry.entry_id,
            identifiers={(DOMAIN, identifier)},
            manufacturer="Zehnder",
            **fields,
        )
        self.node_devices[node.node_id] = (node, device.id, serial)
        if node.node_id == self.ventilation_node_id:
            self.device_id = device.id
        self._async_link_node_devices()
        # The entities of a node that's back on the bus are available again, now that we know its device.
        async_dispatcher_send(self.hass, SIGNAL_COMFOCONNECT_AVAILABILITY.format(self.uuid), self.is_available)

    @callback
    def _async_link_node_devices(self) -> None:
        """Link the devices of the nodes to the device of the bridge, through which we reach them."""
        bridge_node = self.bridge_node
        if bridge_node is None or bridge_node.node_id not in self.node_devices:
            return
        _bridge_node, bridge_device_id, _serial = self.node_devices[bridge_node.node_id]
        # Passing `via_device` to async_get_or_create is deprecated, and its replacement `via_device_id` only exists
        # there since Home Assistant 2026.8, so link the devices with async_update_device, which works on all versions.
        device_registry = dr.async_get(self.hass)
        for node, device_id, _serial in self.node_devices.values():
            if not node.is_bridge:
                device_registry.async_update_device(device_id, via_device_id=bridge_device_id)

    @callback
    def node_callback(self, node: Node) -> None:
        """Add the device of a node that the bridge announces once setup added the others, and forget one that left."""
        if not self.add_node_devices:
            return
        # The entities of a node are only available while it is on the bus.
        async_dispatcher_send(self.hass, SIGNAL_COMFOCONNECT_AVAILABILITY.format(self.uuid), self.is_available)
        if node.is_offline:
            self.node_devices.pop(node.node_id, None)
            return
        # The bridge announces every node again in a new session; the device of one we know stays as it is.
        known = self.node_devices.get(node.node_id)
        if known is None or known[0] != node:
            self.entry.async_create_background_task(self.hass, self.async_add_node_device(node), f"comfoconnect add node {node.node_id}")

    def is_on_bus(self, serial_number: str) -> bool:
        """Return whether the node with this serial number is on the bus in this session."""
        return any(serial == serial_number and node_id in self.nodes for node_id, (_node, _device_id, serial) in self.node_devices.items())

    @callback
    def connection_state_callback(self, state: str) -> None:
        """Follow the session the library keeps up, and ask to register again when the bridge refuses it."""
        self.set_available(state == ConnectionState.CONNECTED)
        if state == ConnectionState.NOT_ALLOWED:
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
        async_dispatcher_send(
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
        async_dispatcher_send(self.hass, SIGNAL_COMFOCONNECT_ALARM_RECEIVED.format(self.uuid))

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
