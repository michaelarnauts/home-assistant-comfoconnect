"""Switch entities for the ComfoConnect integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from aiocomfoconnect.properties import PROPERTY_CLIME_HEATPUMP_STANDBY
from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DOMAIN, SIGNAL_COMFOCONNECT_AVAILABILITY, ComfoConnectBridge


@dataclass
class ComfoconnectSwitchDescriptionMixin:
    """Mixin for switch property accessors."""

    set_value_fn: Callable[[ComfoConnectBridge, bool], Awaitable[Any]]
    get_value_fn: Callable[[ComfoConnectBridge], Awaitable[bool]]


@dataclass
class ComfoconnectSwitchEntityDescription(SwitchEntityDescription, ComfoconnectSwitchDescriptionMixin):
    """Describe a ComfoConnect switch."""


async def _get_heatpump_on(ccb: ComfoConnectBridge) -> bool:
    """Return true when the ComfoClime heat pump is not in standby."""
    standby = await ccb.get_comfoclime_property(PROPERTY_CLIME_HEATPUMP_STANDBY)
    return not bool(standby)


async def _set_heatpump_on(ccb: ComfoConnectBridge, is_on: bool) -> None:
    """Set the ComfoClime standby property from the switch state."""
    await ccb.set_comfoclime_property(PROPERTY_CLIME_HEATPUMP_STANDBY, int(not is_on))


SWITCH_TYPES = (
    ComfoconnectSwitchEntityDescription(
        key="comfoclime_heatpump",
        name="Heat pump",
        icon="mdi:heat-pump",
        entity_category=EntityCategory.CONFIG,
        get_value_fn=_get_heatpump_on,
        set_value_fn=_set_heatpump_on,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ComfoConnect switches."""
    ccb = hass.data[DOMAIN][config_entry.entry_id]
    if not ccb.comfoclime_serial:
        return

    async_add_entities(
        [
            ComfoConnectSwitch(ccb, description, ccb.comfoclime_serial)
            for description in SWITCH_TYPES
        ],
        True,
    )


class ComfoConnectSwitch(SwitchEntity):
    """Representation of a ComfoClime switch."""

    _attr_has_entity_name = True
    entity_description: ComfoconnectSwitchEntityDescription

    def __init__(
        self,
        ccb: ComfoConnectBridge,
        description: ComfoconnectSwitchEntityDescription,
        device_id: str,
    ) -> None:
        """Initialize the switch."""
        self._ccb = ccb
        self.entity_description = description
        self._attr_unique_id = f"{ccb.uuid}-{description.key}"
        self._attr_available = ccb.is_available
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, device_id)})

    async def async_added_to_hass(self) -> None:
        """Register for bridge availability changes."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_COMFOCONNECT_AVAILABILITY.format(self._ccb.uuid),
                self._handle_availability_update,
            )
        )

    @callback
    def _handle_availability_update(self, available: bool) -> None:
        """Handle bridge availability changes."""
        self._attr_available = available
        self.async_write_ha_state()

    async def async_update(self) -> None:
        """Read the current standby state."""
        self._attr_is_on = await self.entity_description.get_value_fn(self._ccb)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Take the heat pump out of standby."""
        await self.entity_description.set_value_fn(self._ccb, True)
        await self.async_update()
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Put the heat pump in standby."""
        await self.entity_description.set_value_fn(self._ccb, False)
        await self.async_update()
        self.async_write_ha_state()
